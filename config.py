"""Application configuration: load/save and dataverse presets.

The curator chooses which Dataverse to work against in Settings (or via
CLI flags in headless mode). The selected base URL, API token and
collection alias are persisted to config.json — resolved for frozen
builds by `resolve_config_path` (CWD, next to the exe, then the folder
holding the build), for dev runs in the working directory.

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
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:  # optional, hard-imported but never fatal to the app at runtime
    import keyring as _keyring
except Exception:  # pragma: no cover - keyring absent entirely
    _keyring = None

KEYRING_SERVICE = "Dataverse Docent"

PRESETS: dict[str, str] = {
    "Borealis Demo — demo.borealisdata.ca": "https://demo.borealisdata.ca",
    "Custom…": "",
}

DEFAULT_CONFIG_PATH = Path("config.json")


def resolve_config_path(path: Path | None = None) -> Path:
    """Choose which config.json this run reads and writes.

    Source runs are unchanged (CWD semantics) and explicit paths are
    honoured as-is. For the default path inside a frozen exe: CWD first
    (terminal launches have always resolved there), then beside the exe,
    then one level above the exe — the folder holding the build, where
    onefile-era launches kept the file — so the lite exe moving into its
    own onedir subfolder still finds an existing config. With no config
    anywhere, frozen runs default above the build folder so a fresh save
    survives rebuilds (PyInstaller wipes its output folder on rebuild).
    """
    primary = Path(path) if path else DEFAULT_CONFIG_PATH
    if primary != DEFAULT_CONFIG_PATH or not getattr(sys, "frozen", False):
        return primary
    exe_dir = Path(sys.executable).parent
    for candidate in (primary, exe_dir / primary.name, exe_dir.parent / primary.name):
        if candidate.exists():
            return candidate
    return exe_dir.parent / primary.name


def default_workspace() -> Path:
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
        env_token = os.environ.get("DATAVERSE_API_TOKEN", "")
        env_collection = os.environ.get("DATAVERSE_COLLECTION", "")
        if not cfg_path.exists():
            cfg = cls()
            if env_url:
                cfg.dataverse.base_url = env_url.rstrip("/")
            if env_token:
                cfg.dataverse.api_token = env_token
                cfg.dataverse.api_token_source = "env"
            if env_collection:
                cfg.dataverse.collection = env_collection
            return cfg
        try:
            raw = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception as exc:
            # Do not silently discard user config — surface it. Callers
            # (main window) can warn; headless can abort with exit code 2.
            raise ValueError(f"config unreadable ({cfg_path}): {exc}") from exc
        if not isinstance(raw, dict):
            raise ValueError(f"config unreadable ({cfg_path}): top-level JSON must be an object")
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
                base_url=str(
                    dv.get("base_url", "https://demo.borealisdata.ca")
                    or "https://demo.borealisdata.ca"
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
                    from applog import get_app_log

                    get_app_log().warn("keyring read failed; falling back to token in config.json")
                except Exception:
                    pass
            if kr:
                cfg.dataverse.api_token = kr
                cfg.dataverse.api_token_source = "keyring"
        # Env overrides apply on top of file.
        if env_url:
            cfg.dataverse.base_url = env_url.rstrip("/")
        if env_token:
            cfg.dataverse.api_token = env_token
            cfg.dataverse.api_token_source = "env"
        if env_collection:
            cfg.dataverse.collection = env_collection
        return cfg

    def save(self, path: Path | None = None) -> None:
        import tempfile

        cfg_path = resolve_config_path(path)
        # Credential-store persistence: the in-memory token never lands on
        # disk when the store can hold it (migration path for legacy
        # plaintext configs: they become keyring-backed on first save).
        token = self.dataverse.api_token
        persisted = token
        source = self.dataverse.api_token_source or "config"
        kr_key = self.dataverse.base_url.rstrip("/") or "token"
        if token and _keyring is not None:
            try:
                _keyring.set_password(KEYRING_SERVICE, kr_key, token)
                persisted = ""
                source = "keyring"
            except Exception:
                source = "config"
                try:
                    from applog import get_app_log

                    get_app_log().warn(
                        "keyring unavailable; API token remains in config.json (owner-only ACL)"
                    )
                except Exception:
                    pass
        elif not token and _keyring is not None:
            # Token cleared in Settings: drop the stale credential too.
            try:
                _keyring.delete_password(KEYRING_SERVICE, kr_key)
            except Exception:
                pass
        payload = {
            "dataverse": {
                "base_url": self.dataverse.base_url,
                "api_token": persisted,
                "api_token_source": source,
                "collection": self.dataverse.collection,
                "subtree": self.dataverse.collection,  # compat
                "collection_alias": self.dataverse.collection,  # explicit alias for user
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
        except OSError:
            pass
        # Windows: chmod is a no-op for ACLs — apply a user-only ACL so
        # other local accounts cannot read the API token.
        if os.name == "nt" and self.dataverse.api_token:
            try:
                import subprocess

                # Remove inheritance + grant only the current user.
                subprocess.run(
                    [
                        "icacls",
                        str(cfg_path),
                        "/inheritance:r",
                        "/grant:r",
                        f"{os.environ.get('USERNAME', 'Everyone')}:F",
                    ],
                    capture_output=True,
                    timeout=10,
                    check=False,
                )
            except Exception:
                pass

    def preset_label(self) -> str:
        for label, url in PRESETS.items():
            if url and url.rstrip("/") == self.dataverse.base_url.rstrip("/"):
                return label
        return "Custom…"
