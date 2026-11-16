"""Structured curation report for a dataset.

A DatasetReport holds dataset-level check findings plus per-file entries with
their own check results. Serializes to JSON - see docs/html/report-contract.html.
"""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from engine.checks.base import CheckResult


@dataclass
class FileEntry:
    path: str
    size_bytes: int
    mime_type: str
    checks: list[CheckResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "size_bytes": self.size_bytes,
            "mime_type": self.mime_type,
            "checks": [c.to_dict() for c in self.checks],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FileEntry":
        if not isinstance(data, dict):
            raise ValueError(f"FileEntry must be an object, got {type(data).__name__}")
        try:
            path = str(data["path"])
            size_bytes = int(data["size_bytes"])
        except KeyError as exc:
            raise ValueError(f"FileEntry missing required field {exc}") from exc
        except (TypeError, ValueError) as exc:
            raise ValueError(f"FileEntry has invalid field: {exc}") from exc
        mime_type = str(data.get("mime_type", "") or "")
        raw_checks = data.get("checks", [])
        if not isinstance(raw_checks, list):
            raise ValueError("FileEntry.checks must be a list")
        return cls(
            path=path,
            size_bytes=size_bytes,
            mime_type=mime_type,
            checks=[CheckResult.from_dict(c) for c in raw_checks],
        )


@dataclass
class DatasetReport:
    persistent_id: str
    label: str
    engine_version: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    dataset_checks: list[CheckResult] = field(default_factory=list)
    files: list[FileEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "persistent_id": self.persistent_id,
            "label": self.label,
            "engine_version": self.engine_version,
            "timestamp": self.timestamp,
            "dataset_checks": [c.to_dict() for c in self.dataset_checks],
            "files": [f.to_dict() for f in self.files],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DatasetReport":
        if not isinstance(data, dict):
            raise ValueError(f"DatasetReport must be an object, got {type(data).__name__}")
        try:
            persistent_id = str(data["persistent_id"])
            label = str(data["label"])
            engine_version = str(data["engine_version"])
        except KeyError as exc:
            raise ValueError(f"DatasetReport missing required field {exc}") from exc
        timestamp = str(data.get("timestamp", "") or "")
        raw_ds = data.get("dataset_checks", [])
        raw_files = data.get("files", [])
        if not isinstance(raw_ds, list) or not isinstance(raw_files, list):
            raise ValueError("DatasetReport dataset_checks/files must be lists")
        return cls(
            persistent_id=persistent_id,
            label=label,
            engine_version=engine_version,
            timestamp=timestamp,
            dataset_checks=[CheckResult.from_dict(c) for c in raw_ds],
            files=[FileEntry.from_dict(f) for f in raw_files],
        )

    def to_markdown(self) -> str:
        from engine.report_md import render_markdown

        return render_markdown(self)

    def save_markdown(self, path: Path) -> None:
        import os
        import tempfile

        from engine.report_md import render_markdown

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = render_markdown(self)
        fd, tmp_name = tempfile.mkstemp(
            dir=str(path.parent), prefix=path.name + ".", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(data)
                handle.flush()
                try:
                    os.fsync(handle.fileno())
                except OSError:
                    pass
            os.replace(tmp_name, path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    def save(self, path: Path) -> None:
        import os
        import tempfile

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(self.to_dict(), indent=2)
        fd, tmp_name = tempfile.mkstemp(
            dir=str(path.parent), prefix=path.name + ".", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(data)
                handle.flush()
                try:
                    os.fsync(handle.fileno())
                except OSError:
                    pass
            os.replace(tmp_name, path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    @classmethod
    def load(cls, path: Path) -> "DatasetReport":
        return cls.from_dict(
            json.loads(path.read_text(encoding="utf-8"))
        )
