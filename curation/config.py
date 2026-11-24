"""Application configuration: load/save and dataverse presets.

The curator chooses which Dataverse to work against in Settings (or via
CLI flags in headless mode). The selected base URL, API token and
collection alias are persisted to config.json. Installed builds keep it
(and the requirement profiles) under the per-user app data folder, where
an update or reinstall cannot reach it; portable builds keep it beside
the exe; dev runs use the working directory. `resolve_user_file` is the
one policy every user-editable file follows.

Token at rest: by default the API token is stored in the OS credential
store (Windows Credential Manager) keyed by base URL, via `keyring`;
config.json keeps only an empty `api_token` plus `api_token_source`. If
the credential store is unavailable the save falls back to a plaintext
token with owner-only ACLs, as it always has. Load precedence is always
env (DATAVERSE_API_TOKEN) > keyring > config.json plaintext; plaintext
tokens found in older configs migrate into the store on next save.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

KEYRING_SERVICE = "Dataverse Docent"


CONFIG_SCHEMA_VERSION = 1


try:  # optional, hard-imported but never fatal to the app at runtime
    import keyring as _keyring
except Exception:  # pragma: no cover - keyring absent entirely
    _keyring = None  # type: ignore[assignment]


PRESETS: dict[str, str] = {
    "Borealis Demo — demo.borealisdata.ca": "https://demo.borealisdata.ca",
    "Custom…": "",
}


def _windows_owner_principal() -> str:
    r"""Resolve the current Windows account as a principal `icacls` accepts.

    Prefer ``DOMAIN\\USER`` from the environment; when only one half is
    present, ask the OS rather than guessing. A missing or unresolved
    principal raises instead of falling back to a wildcard: a config that
    may hold a plaintext token must never be granted to ``Everyone``.
    """
    import subprocess

    domain = os.environ.get("USERDOMAIN", "").strip()
    user = os.environ.get("USERNAME", "").strip()
    if domain and user:
        principal = f"{domain}\\{user}"
    else:
        try:
            result = subprocess.run(["whoami"], capture_output=True, timeout=10, check=False)
            principal = result.stdout.decode("utf-8", "replace").strip()
            if result.returncode != 0:
                principal = ""
        except Exception:
            principal = ""
    if not principal or principal.lower() in {"everyone", "users", "authenticated users", "*"}:
        raise RuntimeError("could not resolve the current Windows account")
    return principal


def _warn_acl_failure(reason: str) -> None:
    """Config was written without owner-only protection; say so (no secrets)."""
    try:
        from curation.applog import get_app_log

        get_app_log().warn(
            f"config.json could not be locked down ({reason}); the file is stored with "
            "best-effort permissions only"
        )
    except Exception:
        pass


def validate_raw(raw: object) -> dict[str, Any]:
    """Validate the decoded config.json payload shape.

    Tolerant of unknown keys; strict about the ones we know. Raises
    ValueError with the offending field path in the message.
    """
    if not isinstance(raw, dict):
        raise ValueError("top-level value must be an object")

    dv = _section(raw, "dataverse")
    for key in (
        "base_url",
        "api_token",
        "collection",
        "collection_alias",
        "subtree",
        "api_token_source",
    ):
        _check_str(dv, key, "dataverse")
    # The API token travels in a request header (X-Dataverse-key), so a
    # cleartext or otherwise unusable base URL is rejected wherever the
    # value came from - not only for the env override in Config.load.
    base_url = dv.get("base_url")
    if base_url:
        normalise_base_url(str(base_url))
    app = _section(raw, "app")
    for key in ("workspace", "tesseract", "exiftool"):
        _check_str(app, key, "app")
    _validate_engine(raw.get("engine"))
    return raw


def _section(raw: dict[str, Any], name: str) -> dict[str, Any]:
    value = raw.get(name, {})
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"section '{name}' must be an object")
    return value


def _check_str(section: dict[str, Any], key: str, where: str) -> None:
    value = section.get(key)
    if value is not None and not isinstance(value, str):
        raise ValueError(f"'{where}.{key}' must be a string")


def _validate_engine(engine: object) -> None:
    if engine is None:
        return
    if not isinstance(engine, dict):
        raise ValueError("section 'engine' must be an object")
    tools = engine.get("optional_tools", {})
    if tools is None:
        return
    if not isinstance(tools, dict):
        raise ValueError("section 'engine.optional_tools' must be an object")
    for key, value in tools.items():
        if not isinstance(value, str):
            raise ValueError(f"'engine.optional_tools.{key}' must be a string")


def normalise_base_url(raw: str, source: str = "DATAVERSE_BASE_URL") -> str:
    """Validate and normalise a Dataverse base URL (env, CLI, file or UI).

    Raises ValueError with a message naming the offending value on anything
    that cannot point at a Dataverse: non-http(s) schemes, plain http (the
    API token travels as X-Dataverse-key, so cleartext is refused), missing
    host, or empty string. `source` lets each caller name its own input.
    """
    url = raw.strip()
    if not url:
        raise ValueError(f"{source} is empty")
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    if scheme == "http":
        raise ValueError(
            f"{source} uses plain HTTP ({raw!r}); the API token is sent as "
            "X-Dataverse-key - use an https:// URL"
        )
    if scheme != "https":
        raise ValueError(f"{source} must start with https:// (scheme {scheme!r} in {raw!r})")
    if not parsed.netloc:
        raise ValueError(f"{source} has no host ({raw!r})")
    return url.rstrip("/")


def base_url_key(url: str) -> str:
    """Identity-normalise a base URL for cache keys and ruleset matching.

    Lowercase and strip the trailing slash only. Unlike `normalise_base_url`
    this deliberately does not validate the scheme: a malformed URL saved in
    an older ruleset or cache must still produce a stable key instead of
    breaking the lookup.
    """
    try:
        return (url or "").rstrip("/").lower()
    except Exception:
        return ""


def _env_workspace() -> Path | None:
    raw = os.environ.get("DATAVERSE_WORKSPACE", "").strip()
    if not raw:
        return None
    return Path(raw).expanduser()


APP_DIR_NAME = "Dataverse Docent"


CONFIG_FILE_NAME = "config.json"


DEFAULT_CONFIG_PATH = Path(CONFIG_FILE_NAME)


def user_data_dir() -> Path:
    """Per-user folder for files that must survive an update or reinstall.

    Windows uses %APPDATA% (roaming, so a token follows the user to another
    machine in the same domain); macOS and Linux follow their own convention
    so a dev run and the tests behave the same way everywhere. Velopack
    replaces the whole install folder on every update, so nothing a curator
    typed may live there.
    """
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_DIR_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    return Path(os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")) / APP_DIR_NAME


def _frozen_exe_dir() -> Path | None:
    """Folder holding the running exe, or None for a source run."""
    if not getattr(sys, "frozen", False):
        return None
    return Path(sys.executable).parent


def is_installed_build() -> bool:
    """Decide whether this frozen run lives inside an installed (Velopack) app.

    Velopack unpacks each version into `<root>/current/` next to its own
    `Update.exe` and swaps that folder on every update. Its runtime answers
    authoritatively when it is importable; the folder shape answers when it
    is not. A plain PyInstaller onedir has neither marker and keeps the
    beside-the-exe behaviour, and the portable zip - same `current/` shape as
    an install - is recognised by the `.portable` marker at its root.
    """
    exe_dir = _frozen_exe_dir()
    if exe_dir is None:
        return False
    # Authoritative answer first: the Velopack runtime knows its own
    # package (an installer registers an uninstall entry; the portable zip
    # carries a .portable marker). Only meaningful for an installed build;
    # any failure - including a source run - falls back to the layout.
    try:
        from velopack import GithubSource, UpdateManager

        from engine.feed import REPO_URL

        manager = UpdateManager(GithubSource(REPO_URL, None, False))
        portable = manager.get_is_portable()
        if isinstance(portable, bool):
            return not portable
    except Exception:
        pass
    # Layout fallback. An install and the portable zip share the shape
    # `<root>/current/<exe>` plus `<root>/Update.exe`, so the folder alone
    # cannot tell them apart: the portable package marks its root `.portable`
    # instead of registering an uninstall entry.
    root = exe_dir.parent if exe_dir.name == "current" else exe_dir
    if (root / ".portable").exists():
        return False
    return exe_dir.name == "current" or (root / "Update.exe").exists()


def _legacy_candidates(name: str, exe_dir: Path) -> list[Path]:
    """Where a user-editable file used to live, nearest first.

    CWD first (terminal launches have always resolved there), then beside
    the exe, then one and two levels above it — the folder holding the
    build, where onefile-era launches and portable zips kept the file.
    """
    return [
        Path(name),
        exe_dir / name,
        exe_dir.parent / name,
        exe_dir.parent.parent / name,
    ]


def _migrate(target: Path, candidates: list[Path]) -> bool:
    """Copy the first existing legacy file to `target`; never delete it."""
    for candidate in candidates:
        try:
            if not candidate.is_file():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(candidate, target)
            return True
        except OSError:
            continue
    return False


def resolve_user_file(name: str) -> Path:
    """Resolve a user-editable data file by policy, not by accident.

    Source runs keep CWD semantics (the repo root is the sandbox). Installed
    builds read and write under `user_data_dir()`, migrating an existing
    file from the old beside-the-exe locations on first run so an upgrade
    does not silently drop a token or a hand-built ruleset. Portable builds
    keep the old search untouched.
    """
    exe_dir = _frozen_exe_dir()
    if exe_dir is None:
        return Path(name)
    candidates = _legacy_candidates(name, exe_dir)
    if is_installed_build():
        target = user_data_dir() / name
        if not target.exists():
            _migrate(target, candidates)
        return target
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return exe_dir.parent / name


def resolve_config_path(path: Path | None = None) -> Path:
    """Choose which config.json this run reads and writes.

    An explicit path is honoured as-is (the `--config` flag, tests). The
    bare default - `None`, or the literal `config.json` that argparse
    supplies - is a request for the policy, not a location:
    `resolve_user_file` answers with per-user app data for an installed
    build, beside the exe for a portable one, the working directory for a
    source run.
    """
    if path is not None and Path(path) != DEFAULT_CONFIG_PATH:
        return Path(path)
    return resolve_user_file(CONFIG_FILE_NAME)


def default_workspace() -> Path:
    """Workspace folder for staged downloads and caches."""
    return Path.home() / "Documents" / "curation-workspace"


@dataclass
class DataverseConfig:
    base_url: str = "https://demo.borealisdata.ca"
    api_token: str = ""
    collection: str = ""
    # where the persisted token lives at rest: "keyring" | "config" | "env"
    # (absent in older configs - treated as "config")
    api_token_source: str = "config"

    # backward-compat alias for older configs / docs
    @property
    def subtree(self) -> str:
        return self.collection

    @subtree.setter
    def subtree(self, value: str) -> None:
        self.collection = value or ""


@dataclass
class AppConfig:
    workspace: Path = field(default_factory=default_workspace)
    tesseract: str = ""
    exiftool: str = ""


@dataclass
class Config:
    dataverse: DataverseConfig = field(default_factory=DataverseConfig)
    app: AppConfig = field(default_factory=AppConfig)

    @classmethod
    def load(cls, path: Path | None = None) -> Config:  # noqa: C901 - grandfathered; complexity burns down as config schema validation lands (dv-hcg.10)
        cfg_path = resolve_config_path(path)
        # Env overrides win over file (CI / headless secrets without
        # persisting tokens to disk).
        env_url = os.environ.get("DATAVERSE_BASE_URL", "").strip()
        env_token = os.environ.get("DATAVERSE_API_TOKEN", "").strip()
        env_collection = os.environ.get("DATAVERSE_COLLECTION", "").strip()
        if not cfg_path.exists():
            cfg = cls()
            if env_url:
                cfg.dataverse.base_url = normalise_base_url(env_url)
            if env_token:
                cfg.dataverse.api_token = env_token
                cfg.dataverse.api_token_source = "env"
            if env_collection:
                cfg.dataverse.collection = env_collection
            env_ws = _env_workspace()
            if env_ws is not None:
                cfg.app.workspace = env_ws
            return cfg
        try:
            raw = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception as exc:
            # Do not silently discard user config — surface it. Callers
            # (main window) can warn; headless can abort with exit code 2.
            raise ValueError(f"config unreadable ({cfg_path}): {exc}") from exc
        if not isinstance(raw, dict):
            raise ValueError(f"config unreadable ({cfg_path}): top-level JSON must be an object")
        try:
            validate_raw(raw)
        except ValueError as exc:
            raise ValueError(f"config unreadable ({cfg_path}): {exc}") from exc
        dv = raw.get("dataverse", {}) if isinstance(raw.get("dataverse", {}), dict) else {}
        app_raw = raw.get("app", {}) if isinstance(raw.get("app", {}), dict) else {}
        engine_block = raw.get("engine", {}) if isinstance(raw.get("engine", {}), dict) else {}
        engine_raw = (
            engine_block.get("optional_tools", {})
            if isinstance(engine_block.get("optional_tools", {}), dict)
            else {}
        )
        collection = (
            dv.get("collection")
            if "collection" in dv
            else dv.get("collection_alias")
            if "collection_alias" in dv
            else dv.get("subtree", "")
        )
        cfg = cls(
            dataverse=DataverseConfig(
                base_url=normalise_base_url(
                    str(
                        dv.get("base_url", "https://demo.borealisdata.ca")
                        or "https://demo.borealisdata.ca"
                    )
                ),
                api_token=str(dv.get("api_token", "") or ""),
                collection=str(collection or ""),
                api_token_source=str(dv.get("api_token_source", "config") or "config"),
            ),
            app=AppConfig(
                workspace=Path(
                    str(
                        app_raw.get("workspace", str(default_workspace()))
                        or str(default_workspace())
                    )
                ),
                tesseract=str(engine_raw.get("tesseract", app_raw.get("tesseract", "")) or ""),
                exiftool=str(engine_raw.get("exiftool", app_raw.get("exiftool", "")) or ""),
            ),
        )
        # Keyring holds the token when the config says so (or when a stale
        # source marker names it); a stored plaintext token wins whenever
        # the store is empty/unreadable (pre-migration or fallback case).
        if cfg.dataverse.api_token_source == "keyring" and _keyring is not None:
            try:
                kr = _keyring.get_password(
                    KEYRING_SERVICE, cfg.dataverse.base_url.rstrip("/") or "token"
                )
            except Exception:
                kr = None
                try:
                    from curation.applog import get_app_log

                    get_app_log().warn("keyring read failed; falling back to token in config.json")
                except Exception:
                    pass
            if kr:
                cfg.dataverse.api_token = kr
                cfg.dataverse.api_token_source = "keyring"
        # Env overrides apply on top of file.
        if env_url:
            cfg.dataverse.base_url = normalise_base_url(env_url)
        if env_token:
            cfg.dataverse.api_token = env_token
            cfg.dataverse.api_token_source = "env"
        if env_collection:
            cfg.dataverse.collection = env_collection
        env_ws = _env_workspace()
        if env_ws is not None:
            cfg.app.workspace = env_ws
        return cfg

    def _persist_token(self, kr_key: str) -> tuple[str, str]:
        """Write the in-memory token to the credential store when possible.

        Returns (persisted_value, source): ("", "keyring") when the token was
        stored, (token, "config") as fallback, or ("", source) when the token
        was cleared (a stale credential is deleted instead).
        """
        token = self.dataverse.api_token
        persisted = token
        source = self.dataverse.api_token_source or "config"
        if token and _keyring is not None:
            try:
                _keyring.set_password(KEYRING_SERVICE, kr_key, token)
                return "", "keyring"
            except Exception:
                try:
                    from curation.applog import get_app_log

                    get_app_log().warn(
                        "keyring unavailable; API token remains in config.json (owner-only ACL)"
                    )
                except Exception:
                    pass
                return token, "config"
        if not token and _keyring is not None:
            # Token cleared in Settings: drop the stale credential too.
            try:
                _keyring.delete_password(KEYRING_SERVICE, kr_key)
            except Exception:
                pass
        return persisted, source

    def save(self, path: Path | None = None) -> None:
        import tempfile

        cfg_path = resolve_config_path(path)
        # Resolve the ACL principal before writing anything: if it cannot be
        # found, abort instead of replacing a working config with one we
        # cannot protect (and instead of deleting the old file afterwards).
        acl_principal: str | None = None
        if os.name == "nt" and self.dataverse.api_token:
            acl_principal = _windows_owner_principal()
        # Credential-store persistence: the in-memory token never lands on
        # disk when the store can hold it (migration path for legacy
        # plaintext configs: they become keyring-backed on first save).
        kr_key = self.dataverse.base_url.rstrip("/") or "token"
        persisted, source = self._persist_token(kr_key)
        payload = {
            "version": CONFIG_SCHEMA_VERSION,
            "dataverse": {
                "base_url": self.dataverse.base_url,
                "api_token": persisted,
                "api_token_source": source,
                "collection": self.dataverse.collection,
            },
            "app": {"workspace": str(self.app.workspace)},
            "engine": {
                "optional_tools": {
                    "tesseract": self.app.tesseract,
                    "exiftool": self.app.exiftool,
                }
            },
        }
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(payload, indent=2)
        fd, tmp_name = tempfile.mkstemp(
            dir=str(cfg_path.parent), prefix=cfg_path.name + ".", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(data)
                handle.flush()
                try:
                    os.fsync(handle.fileno())
                except OSError:
                    pass
            os.replace(tmp_name, cfg_path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
        # Token at rest: restrict to owner where the OS supports it.
        try:
            os.chmod(cfg_path, 0o600)
        except OSError as exc:
            _warn_acl_failure(f"chmod(cfg_path, 0600) failed: {exc}")
        # Windows: chmod is a no-op for ACLs — apply a user-only ACL so
        # other local accounts cannot read the API token.
        if acl_principal is not None:
            try:
                import subprocess

                # Remove inheritance + grant only the current user.
                acl = subprocess.run(
                    [
                        "icacls",
                        str(cfg_path),
                        "/inheritance:r",
                        "/grant:r",
                        f"{acl_principal}:F",
                    ],
                    capture_output=True,
                    timeout=10,
                    check=False,
                )
                if acl.returncode != 0:
                    stderr = acl.stderr.decode("utf-8", "replace").strip() or "no stderr"
                    _warn_acl_failure(f"icacls exited {acl.returncode}: {stderr}")
            except Exception as exc:
                _warn_acl_failure(f"icacls could not be run: {exc}")

    def preset_label(self) -> str:
        for label, url in PRESETS.items():
            if url and url.rstrip("/") == self.dataverse.base_url.rstrip("/"):
                return label
        return "Custom…"
