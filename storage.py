"""SQLite-backed local state.

Tables (initial schema):
- datasets(persistent_id PK, title, state, in_review, quote_bytes, status,
  downloaded_at, local_path)
- files(dataset_id, file_id, path, size_bytes, checksum, checksum_type)
- check_results(dataset_id, check_id, level, passed, message, details_json)
- curation_actions(id PK, dataset_id, timestamp, action, actor, notes,
  details_json): append-only log of curator/system actions per dataset
  (downloaded, checks_run, decision, exported, metadata_loaded, ...).
  Displayed on the dataset page as "Curation history" and used for the
  dashboard's Downloaded date column and the Needs-Action metric (only
  curation_actions is read today; datasets/files/check_results are
  reserved for future use).

Stored under <workspace>/state.db. The API token never touches the database.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS datasets (
    persistent_id TEXT PRIMARY KEY,
    title TEXT,
    state TEXT,
    in_review INTEGER DEFAULT 0,
    status TEXT DEFAULT 'new',
    quote_bytes INTEGER,
    downloaded_at TEXT,
    local_path TEXT
);
CREATE TABLE IF NOT EXISTS files (
    dataset_id TEXT,
    file_id TEXT,
    path TEXT,
    size_bytes INTEGER,
    checksum TEXT,
    checksum_type TEXT,
    PRIMARY KEY (dataset_id, file_id)
);
CREATE TABLE IF NOT EXISTS check_results (
    dataset_id TEXT,
    check_id TEXT,
    level TEXT,
    passed INTEGER,
    message TEXT,
    details_json TEXT,
    PRIMARY KEY (dataset_id, check_id)
);
CREATE TABLE IF NOT EXISTS curation_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    action TEXT NOT NULL,
    actor TEXT DEFAULT 'curator',
    notes TEXT DEFAULT '',
    details_json TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_curation_actions_dataset
    ON curation_actions(dataset_id, timestamp DESC);
"""


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class AppState:
    def __init__(self, db_path: Path) -> None:
        db_path = Path(db_path)
        try:
            db_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        try:
            self._conn.commit()
        except Exception:
            pass
        self._conn.close()

    # -- curation action log -------------------------------------------

    def log_action(
        self,
        dataset_id: str,
        action: str,
        notes: str = "",
        actor: str = "curator",
        details: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str] = None,
    ) -> int:
        """Append one curation action. Returns the new row id."""
        ts = timestamp or _utcnow_iso()
        cur = self._conn.execute(
            "INSERT INTO curation_actions "
            "(dataset_id, timestamp, action, actor, notes, details_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                dataset_id,
                ts,
                action,
                actor,
                notes or "",
                json.dumps(details or {}, ensure_ascii=False),
            ),
        )
        self._conn.commit()
        return int(cur.lastrowid or 0)

    def list_actions(self, dataset_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Newest-first action log for one dataset."""
        cur = self._conn.execute(
            "SELECT timestamp, action, actor, notes, details_json "
            "FROM curation_actions WHERE dataset_id = ? "
            "ORDER BY timestamp DESC, id DESC LIMIT ?",
            (dataset_id, limit),
        )
        out: List[Dict[str, Any]] = []
        for row in cur.fetchall():
            try:
                details = json.loads(row["details_json"] or "{}")
            except Exception:
                details = {}
            out.append(
                {
                    "timestamp": row["timestamp"],
                    "action": row["action"],
                    "actor": row["actor"],
                    "notes": row["notes"],
                    "details": details,
                }
            )
        return out

    def last_action(self, dataset_id: str, action: str) -> Optional[Dict[str, Any]]:
        """Newest action of a given type, or None."""
        cur = self._conn.execute(
            "SELECT timestamp, action, actor, notes, details_json "
            "FROM curation_actions WHERE dataset_id = ? AND action = ? "
            "ORDER BY timestamp DESC, id DESC LIMIT 1",
            (dataset_id, action),
        )
        row = cur.fetchone()
        if row is None:
            return None
        try:
            details = json.loads(row["details_json"] or "{}")
        except Exception:
            details = {}
        return {
            "timestamp": row["timestamp"],
            "action": row["action"],
            "actor": row["actor"],
            "notes": row["notes"],
            "details": details,
        }


def open_state(workspace: Path) -> AppState:
    """Convenience: open <workspace>/state.db (creating dirs as needed)."""
    return AppState(Path(workspace) / "state.db")


_SIZE_CACHE_NAME = "dataset_sizes.json"
_TABLE_LAYOUT_NAME = "table_layout.json"


def read_size_cache(workspace: Path) -> Dict[str, Dict[str, Any]]:
    """{persistent_id: {"size": bytes, "files": n}} from the last metadata load.

    Never raises; returns {} when the cache is missing or corrupt.
    """
    try:
        raw = json.loads((Path(workspace) / _SIZE_CACHE_NAME).read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for pid, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        try:
            out[str(pid)] = {
                "size": int(entry.get("size", 0) or 0),
                "files": int(entry.get("files", 0) or 0),
            }
        except Exception:
            continue
    return out


def write_size_entry(workspace: Path, persistent_id: str, size_bytes: int, file_count: int) -> None:
    """Record a dataset's summed inventory size (best-effort, never raises)."""
    try:
        path = Path(workspace) / _SIZE_CACHE_NAME
        try:
            raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except Exception:
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        raw[persistent_id] = {"size": int(size_bytes or 0), "files": int(file_count or 0)}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    except Exception:
        pass


def _table_layout_path(workspace: Path) -> Path:
    return Path(workspace) / _TABLE_LAYOUT_NAME


def save_table_state(workspace: Path, name: str, header) -> None:
    """Persist a QHeaderView's section sizes (best-effort, never raises)."""
    try:
        path = _table_layout_path(workspace)
        try:
            raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except Exception:
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        widths = [header.sectionSize(i) for i in range(header.count())]
        raw[name] = {"widths": widths}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    except Exception:
        pass


def restore_table_state(workspace: Path, name: str, header) -> None:
    """Re-apply persisted section sizes (best-effort, never raises)."""
    try:
        path = _table_layout_path(workspace)
        if not path.exists():
            return
        raw = json.loads(path.read_text(encoding="utf-8"))
        widths = (raw.get(name) or {}).get("widths") if isinstance(raw, dict) else None
        if not isinstance(widths, list):
            return
        try:
            header.blockSignals(True)
            for i, width in enumerate(widths):
                if i >= header.count():
                    break
                try:
                    header.resizeSection(i, max(20, int(width)))
                except Exception:
                    continue
        finally:
            try:
                header.blockSignals(False)
            except Exception:
                pass
    except Exception:
        pass
