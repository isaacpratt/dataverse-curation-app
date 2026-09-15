"""Structured curation report for a dataset.

A DatasetReport holds dataset-level check findings plus per-file entries with
their own check results. Serializes to JSON - see docs/report-contract.md.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from engine.checks.base import CheckResult


@dataclass
class FileEntry:
    path: str
    size_bytes: int
    mime_type: str
    checks: List[CheckResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "size_bytes": self.size_bytes,
            "mime_type": self.mime_type,
            "checks": [c.to_dict() for c in self.checks],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FileEntry":
        return cls(
            path=data["path"],
            size_bytes=data["size_bytes"],
            mime_type=data.get("mime_type", ""),
            checks=[CheckResult.from_dict(c) for c in data.get("checks", [])],
        )


@dataclass
class DatasetReport:
    persistent_id: str
    label: str
    engine_version: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    dataset_checks: List[CheckResult] = field(default_factory=list)
    files: List[FileEntry] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "persistent_id": self.persistent_id,
            "label": self.label,
            "engine_version": self.engine_version,
            "timestamp": self.timestamp,
            "dataset_checks": [c.to_dict() for c in self.dataset_checks],
            "files": [f.to_dict() for f in self.files],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DatasetReport":
        return cls(
            persistent_id=data["persistent_id"],
            label=data["label"],
            engine_version=data["engine_version"],
            timestamp=data.get("timestamp", ""),
            dataset_checks=[
                CheckResult.from_dict(c) for c in data.get("dataset_checks", [])
            ],
            files=[FileEntry.from_dict(f) for f in data.get("files", [])],
        )

    def save(self, path: Path) -> None:
        path.write_text(
            json.dumps(self.to_dict(), indent=2), encoding="utf-8"
        )

    @classmethod
    def load(cls, path: Path) -> "DatasetReport":
        return cls.from_dict(
            json.loads(path.read_text(encoding="utf-8"))
        )