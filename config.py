"""Application configuration: load/save and dataverse presets.

The curator chooses which Dataverse to work against in Settings (or via
CLI flags in headless mode). The selected base URL, API token and
collection alias are persisted to config.json next to the executable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict

PRESETS: Dict[str, str] = {
    "Borealis Demo — demo.borealisdata.ca": "https://demo.borealisdata.ca",
    "Custom…": "",
}

DEFAULT_CONFIG_PATH = Path("config.json")


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
    def load(cls, path: Path | None = None) -> "Config":
        cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
        if not cfg_path.exists():
            return cls()
        try:
            raw = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            return cls()
        dv = raw.get("dataverse", {})
        app_raw = raw.get("app", {})
        engine_raw = raw.get("engine", {}).get("optional_tools", {})
        collection = (
            dv.get("collection")
            if "collection" in dv
            else dv.get("collection_alias")
            if "collection_alias" in dv
            else dv.get("subtree", "")
        )
        return cls(
            dataverse=DataverseConfig(
                base_url=dv.get("base_url", "https://demo.borealisdata.ca"),
                api_token=dv.get("api_token", ""),
                collection=collection or "",
            ),
            app=AppConfig(
                workspace=Path(app_raw.get("workspace", str(default_workspace()))),
                tesseract=engine_raw.get("tesseract", app_raw.get("tesseract", "")),
                exiftool=engine_raw.get("exiftool", app_raw.get("exiftool", "")),
            ),
        )

    def save(self, path: Path | None = None) -> None:
        cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
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
        cfg_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def preset_label(self) -> str:
        for label, url in PRESETS.items():
            if url and url.rstrip("/") == self.dataverse.base_url.rstrip("/"):
                return label
        return "Custom…"
