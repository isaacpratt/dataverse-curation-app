"""Application configuration: load/save and dataverse presets.

The curator chooses which Dataverse to work against in Settings (or via
CLI flags in headless mode). The selected base URL, API token and
collection alias are persisted to config.json. Installed builds keep it
(and the requirement profiles) under the per-user app data folder, where
an update or reinstall cannot reach it; portable builds keep it beside
the exe; dev runs use the working directory. `resolve_user_file` is the
one policy every user-editable file follows.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

PRESETS: dict[str, str] = {
    "Borealis Demo — demo.borealisdata.ca": "https://demo.borealisdata.ca",
    "Custom…": "",
}

#: Folder under %APPDATA% / Application Support / XDG config for data that
#: has to outlive an update and a reinstall (the API token, curated rules).
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
    try:
        from velopack import UpdateManager  # type: ignore[import-not-found]

        portable = UpdateManager.get_is_portable()
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
    return Path.home() / "Documents" / "curation-workspace"


@dataclass
class DataverseConfig:
    base_url: str = "https://demo.borealisdata.ca"
    api_token: str = ""
    collection: str = ""
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
    def load(cls, path: Path | None = None) -> Config:
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
        engine_raw = engine_block.get("optional_tools", {}) if isinstance(engine_block.get("optional_tools", {}), dict) else {}
        collection = (
            dv.get("collection")
            if "collection" in dv
            else dv.get("collection_alias")
            if "collection_alias" in dv
            else dv.get("subtree", "")
        )
        cfg = cls(
            dataverse=DataverseConfig(
                base_url=str(dv.get("base_url", "https://demo.borealisdata.ca") or "https://demo.borealisdata.ca"),
                api_token=str(dv.get("api_token", "") or ""),
                collection=str(collection or ""),
            ),
            app=AppConfig(
                workspace=Path(str(app_raw.get("workspace", str(default_workspace())) or str(default_workspace()))),
                tesseract=str(engine_raw.get("tesseract", app_raw.get("tesseract", "")) or ""),
                exiftool=str(engine_raw.get("exiftool", app_raw.get("exiftool", "")) or ""),
            ),
        )
        # Env overrides apply on top of file.
        if env_url:
            cfg.dataverse.base_url = env_url.rstrip("/")
        if env_token:
            cfg.dataverse.api_token = env_token
        if env_collection:
            cfg.dataverse.collection = env_collection
        return cfg

    def save(self, path: Path | None = None) -> None:
        import tempfile

        cfg_path = resolve_config_path(path)
        payload = {
            "dataverse": {
                "base_url": self.dataverse.base_url,
                "api_token": self.dataverse.api_token,
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
