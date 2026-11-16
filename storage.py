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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
CREATE INDEX IF NOT EXISTS idx_curation_actions_action
    ON curation_actions(action, dataset_id);
"""


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _atomic_write_json(path: Path, payload: object) -> None:
    """Atomic JSON write via tmp+rename (crash-safe, never truncates)."""
    import os
    import tempfile

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, indent=2, ensure_ascii=False)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
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


class AppState:
    def __init__(self, db_path: Path, timeout: float = 30.0) -> None:
        import threading

        db_path = Path(db_path)
        try:
            db_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        # timeout avoids SQLITE_BUSY on concurrent dashboard/detail access;
        # WAL allows readers during writes; check_same_thread=False with a
        # write lock keeps Qt worker threads safe.
        self._conn = sqlite3.connect(str(db_path), timeout=timeout, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        try:
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA busy_timeout=30000;")
        except sqlite3.Error:
            pass
        self._conn.executescript(_SCHEMA)
        self._lock = threading.Lock()

    def close(self) -> None:
        try:
            with self._lock:
                try:
                    self._conn.commit()
                except Exception:
                    pass
                self._conn.close()
        except Exception:
            try:
                self._conn.close()
            except Exception:
                pass

    # -- curation action log -------------------------------------------

    def log_action(
        self,
        dataset_id: str,
        action: str,
        notes: str = "",
        actor: str = "curator",
        details: dict[str, Any] | None = None,
        timestamp: str | None = None,
    ) -> int:
        """Append one curation action. Returns the new row id."""
        ts = timestamp or _utcnow_iso()
        with self._lock:
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

    def list_actions(self, dataset_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """Newest-first action log for one dataset."""
        cur = self._conn.execute(
            "SELECT timestamp, action, actor, notes, details_json "
            "FROM curation_actions WHERE dataset_id = ? "
            "ORDER BY timestamp DESC, id DESC LIMIT ?",
            (dataset_id, limit),
        )
        out: list[dict[str, Any]] = []
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

    def last_action(self, dataset_id: str, action: str) -> dict[str, Any] | None:
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
    """Open <workspace>/state.db (creating dirs as needed)."""
    return AppState(Path(workspace) / "state.db")


_SIZE_CACHE_NAME = "dataset_sizes.json"
_TABLE_LAYOUT_NAME = "table_layout.json"


def read_size_cache(workspace: Path) -> dict[str, dict[str, Any]]:
    """{persistent_id: {"size": bytes, "files": n}} from the last metadata load.

    Never raises; returns {} when the cache is missing or corrupt.
    """
    try:
        raw = json.loads((Path(workspace) / _SIZE_CACHE_NAME).read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
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
        _atomic_write_json(path, raw)
    except Exception:
        pass


def _table_layout_path(workspace: Path) -> Path:
    return Path(workspace) / _TABLE_LAYOUT_NAME


def _enum_int(value) -> int:
    """Best-effort int from a PySide6 enum member OR a plain int.

    This PySide6 build raises TypeError on int(enum), so .value is the
    fallback; duck-typed headers (tests) may return plain ints.
    """
    try:
        return int(value)
    except Exception:
        pass
    v = getattr(value, "value", None)
    if isinstance(v, int):
        return v
    return 0


def _sort_order_value(raw: int):
    """Enum for real Qt headers when possible, plain int otherwise."""
    try:
        from PySide6.QtCore import Qt

        return Qt.SortOrder(int(raw))
    except Exception:
        return int(raw)


TABLE_LAYOUT_VERSION = 1
"""Schema version of one entry in ``table_layout.json``.

Bump when the meaning of a key changes. Entries without a version are
legacy (v0) and still readable; entries with a newer version are ignored
rather than half-applied.
"""


def table_layout_entry_valid(entry: Any, column_count: int) -> bool:
    """Check whether a saved layout entry fits a header with this many columns.

    A layout saved for a different table shape (an older build with more
    or fewer columns) must not be applied: the widths would land on the
    wrong columns and squeeze the table. Legacy entries (no "v" key) are
    accepted when their width list matches the column count.
    """
    if not isinstance(entry, dict) or not entry:
        return False
    version = entry.get("v")
    if version is not None:
        try:
            if int(version) > TABLE_LAYOUT_VERSION:
                return False
        except Exception:
            return False
    widths = entry.get("widths")
    if not isinstance(widths, list):
        return False
    return len(widths) == int(column_count)


def save_table_state(workspace: Path, name: str, header) -> None:
    """Persist a table's full view state (best-effort, never raises).

    Records column widths, the user's sort indicator, hidden columns, and
    the visual column order so the table reopens exactly as it was left.
    Extra keys are additive: older readers keep the "widths" contract.
    The entry carries the schema version (see TABLE_LAYOUT_VERSION), so a
    layout saved by a newer build is ignored instead of misapplied.
    """
    try:
        path = _table_layout_path(workspace)
        try:
            raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except Exception:
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        count = header.count()
        entry: dict = {
            "v": TABLE_LAYOUT_VERSION,
            "widths": [header.sectionSize(i) for i in range(count)],
        }
        try:
            if header.isSortIndicatorShown():
                entry["sort"] = [
                    int(header.sortIndicatorSection()),
                    _enum_int(header.sortIndicatorOrder()),
                ]
                entry["sort_shown"] = True
        except Exception:
            pass
        try:
            entry["hidden"] = [bool(header.isSectionHidden(i)) for i in range(count)]
        except Exception:
            pass
        try:
            entry["order"] = [int(header.visualIndex(i)) for i in range(count)]
        except Exception:
            pass
        raw[name] = entry
        _atomic_write_json(path, raw)
    except Exception:
        pass


def snapshot_table_view(header) -> dict:
    """Capture a header's current view state for later reset (never raises).

    Records widths, hidden columns, visual order, and the sort indicator —
    call right after construction (before restore) so reset reproduces the
    fresh-start view exactly.
    """
    snap: dict = {"widths": [], "hidden": [], "order": [], "sort": None, "sort_shown": False}
    try:
        count = header.count()
        snap["widths"] = [header.sectionSize(i) for i in range(count)]
        try:
            snap["hidden"] = [bool(header.isSectionHidden(i)) for i in range(count)]
        except Exception:
            pass
        try:
            snap["order"] = [int(header.visualIndex(i)) for i in range(count)]
        except Exception:
            pass
        try:
            if header.isSortIndicatorShown():
                snap["sort"] = [
                    int(header.sortIndicatorSection()),
                    _enum_int(header.sortIndicatorOrder()),
                ]
                snap["sort_shown"] = True
        except Exception:
            pass
    except Exception:
        pass
    return snap


def apply_table_view(header, snap) -> None:  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
    """Re-apply a view-state dict (snapshot or persisted entry). Never raises."""
    try:
        if not isinstance(snap, dict):
            return
        count = header.count()
        try:
            header.blockSignals(True)
            # -- widths ---------------------------------------------------
            widths = snap.get("widths")
            if isinstance(widths, list):
                for i, width in enumerate(widths):
                    if i >= count:
                        break
                    try:
                        header.resizeSection(i, max(20, int(width)))
                    except Exception:
                        continue
            # -- hidden columns -------------------------------------------
            hidden = snap.get("hidden")
            if isinstance(hidden, list):
                for i, flag in enumerate(hidden):
                    if i >= count:
                        break
                    try:
                        header.setSectionHidden(i, bool(flag))
                    except Exception:
                        continue
            # -- visual column order --------------------------------------
            order = snap.get("order")
            if isinstance(order, list) and len(order) == count:
                # order[logical] = visual index wanted; move into place one
                # target slot at a time (moveSection works in visual slots).
                for target in range(count):
                    logical = next((i for i in range(count) if order[i] == target), None)
                    if logical is None:
                        continue
                    try:
                        current = header.visualIndex(logical)
                        if current != target:
                            header.moveSection(current, target)
                    except Exception:
                        continue
        finally:
            try:
                header.blockSignals(False)
            except Exception:
                pass
        # -- sort indicator (after widths/order: fires one reorder) -------
        # Legacy entries carry neither key: leave the indicator alone.
        sort = snap.get("sort")
        if not isinstance(sort, list) and ("sort" in snap or "sort_shown" in snap):
            try:
                header.setSortIndicatorShown(False)
            except Exception:
                pass
        elif isinstance(sort, list) and len(sort) == 2:
            try:
                column = int(sort[0])
                if 0 <= column < count:
                    # Real Qt headers want the enum; duck-typed headers
                    # accept the plain int (first call falls back).
                    try:
                        header.setSortIndicator(column, _sort_order_value(sort[1]))
                    except Exception:
                        header.setSortIndicator(column, int(sort[1]))
                    if snap.get("sort_shown"):
                        try:
                            header.setSortIndicatorShown(True)
                        except Exception:
                            pass
                    else:
                        try:
                            header.setSortIndicatorShown(False)
                        except Exception:
                            pass
            except Exception:
                pass
    except Exception:
        pass


def clear_table_state(workspace: Path, name: str) -> None:
    """Drop one table's persisted entry so defaults survive restarts."""
    try:
        path = _table_layout_path(workspace)
        if not path.exists():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(raw, dict) or name not in raw:
            return
        try:
            del raw[name]
        except Exception:
            return
        _atomic_write_json(path, raw)
    except Exception:
        pass


def restore_table_state(workspace: Path, name: str, header) -> bool:
    """Re-apply a persisted view state (best-effort, never raises).

    Widths always come back; sort indicator, hidden columns, and visual
    order apply only when they were saved (newer saves only).
    An entry saved for a different column count (an older table shape) is
    ignored: it would squeeze the wrong columns.
    Returns True when a saved entry was applied (caller should skip
    content auto-fit so the user's layout wins).
    """
    try:
        path = _table_layout_path(workspace)
        if not path.exists():
            return False
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return False
        entry = raw.get(name)
        if not table_layout_entry_valid(entry, header.count()):
            return False
        apply_table_view(header, entry)
        return True
    except Exception:
        return False
