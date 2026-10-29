"""Dashboard view: metrics + curation queue.

Table uses plain QTableWidgetItems only (no cell widgets) so text never
overlaps/garbles and Qt sorting moves whole rows. All columns are
user-resizable (Interactive) with the last visible column stretching to fill
leftover space, and toggleable via Columns… including the local Downloaded
date sourced from the workspace state.db + staged folders.
"""

from pathlib import Path

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from config import Config
from ui.ring import RingProgress
from ui.theme import (
    BACKGROUND,
    ERROR,
    ON_SURFACE,
    ON_SURFACE_VARIANT,
    OUTLINE_VARIANT,
    PRIMARY,
    SURFACE_CONTAINER,
    SURFACE_CONTAINER_LOWEST,
    TERTIARY,
    selectable_labels,
)
from ui.widgets import AppButton, AppTable, flush_table_style, make_combo, make_search_field
from ui.workers import CrawlWorker


class _BarLabel(QLabel):
    """QLabel that notifies on setText — QLabel ships no textChanged signal.

    Lets the status bar's dot track both halves (scope and message)
    without touching every setText call site.
    """

    changed = Signal(str)

    def setText(self, text: str) -> None:
        """Set the label text and notify watchers via :attr:`changed`."""
        super().setText(text)
        self.changed.emit(text)

# Full column model. `key` maps to dataset dict + enriched local dates.
# `default_visible=False` columns start hidden but can be enabled via Columns…
COLUMNS: list[tuple[str, str, bool]] = [
    ("title", "Dataset Title", True),
    ("persistent_id", "Persistent ID", False),
    ("contact", "Submitting Author", True),
    ("depositor", "Depositor", False),
    ("date_created", "Date Created", True),
    ("date_published", "Date Published", False),
    ("collection", "Collection", False),
    ("file_count", "Files", True),
    ("total_size_bytes", "Size", True),
    ("state", "Status", True),
    ("curation_label", "Curation Label", True),
    ("downloaded_at", "Downloaded", True),
]

_COLUMN_WIDTHS = {
    "title": 300,
    "persistent_id": 200,
    "contact": 160,
    "depositor": 140,
    "date_created": 110,
    "date_published": 110,
    "collection": 150,
    "file_count": 60,
    "total_size_bytes": 90,
    "state": 110,
    "curation_label": 150,
    "downloaded_at": 130,
}

# Metric-card value: the real count (22px bold) versus a named pre-crawl
# state (12px muted words, 2026-10-02 P2) — the number slot never shows a
# bare "—", so a visible "0" can only mean a completed check counted zero.
_METRIC_VALUE_STYLE = (
    f"font-size: 22px; font-weight: 700; color: {ON_SURFACE}; "
    "border: none; background: transparent;"
)
_METRIC_STATE_STYLE = (
    f"font-size: 12px; font-weight: 600; color: {ON_SURFACE_VARIANT}; "
    "letter-spacing: 0.5px; border: none; background: transparent;"
)


def _human_size(n: int) -> str:
    """Human-readable size with B/KB/MB/GB/TB (shared with detail)."""
    try:
        n = int(n)
    except Exception:
        return str(n)
    if n < 1024:
        return f"{n} B"
    for unit in ("KB", "MB", "GB", "TB"):
        n /= 1024.0
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}"
    return f"{n:.1f} TB"


def _sanitize(pid: str) -> str:
    s = (pid or "").replace(":", "_").replace("/", "_").replace("\\", "_")
    s = s.replace("..", "__").strip().lstrip(".")
    return (s or "_dataset")[:120]


def _parse_date_epoch(s: str) -> float:
    """Parse dashboard dates once (not per keystroke per cell).

    Handles YYYY-MM-DD, YYYY-MM-DD HH:MM, ISO-8601 with timezone, and
    year-only fallback. Returns 0.0 for empty/unparseable.
    """
    if not s:
        return 0.0
    text = str(s).strip()
    if not text:
        return 0.0
    try:
        from datetime import datetime, timezone

        # ISO-8601 first (handles TZ suffixes the old loop ignored).
        try:
            iso = text.replace("Z", "+00:00") if text.endswith("Z") else text
            dt = datetime.fromisoformat(iso)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except ValueError:
            pass
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(text[: len(fmt)], fmt)
                return dt.replace(tzinfo=timezone.utc).timestamp()
            except ValueError:
                continue
        # Year-only fallback preserves rough ordering.
        try:
            return float(text[:4] or 0)
        except ValueError:
            return 0.0
    except Exception:
        return 0.0


def _local_downloaded_batch(workspace: Path, pids: list[str]) -> dict[str, str]:
    """Return downloaded timestamps for many datasets with ONE sqlite connect.

    Same sources/semantics as _local_downloaded (state.db download actions,
    staged-dir mtime fallback); "" or "YYYY-MM-DD HH:MM" per pid.
    """
    out = dict.fromkeys(pids, "")
    try:
        ws = Path(workspace)
        db = ws / "state.db"
        if db.exists():
            import sqlite3

            conn = sqlite3.connect(str(db), timeout=30.0)
            try:
                cur = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name='curation_actions'"
                )
                if cur.fetchone():
                    rows = conn.execute(
                        "SELECT dataset_id, MAX(timestamp) FROM curation_actions "
                        "WHERE action IN ('downloaded','download') "
                        "GROUP BY dataset_id"
                    ).fetchall()
                    for pid, ts in rows:
                        if pid in out and ts:
                            out[pid] = str(ts)[:16].replace("T", " ")
            finally:
                conn.close()
        import datetime

        for pid in pids:
            if out[pid] or not pid:
                continue
            staged = ws / "downloads" / _sanitize(pid) / "files"
            try:
                if staged.exists():
                    out[pid] = datetime.datetime.fromtimestamp(
                        staged.stat().st_mtime
                    ).strftime("%Y-%m-%d %H:%M")
            except OSError:
                continue
    except Exception:
        pass
    return out


def _local_downloaded(workspace: Path, persistent_id: str) -> str:
    """Return the downloaded timestamp for one dataset from local system state.

    Sources (best-effort, never raises):
    - state.db curation_actions (downloaded/download)
    - staged files dir mtime as fallback
    Returns "" or "YYYY-MM-DD HH:MM".
    """
    try:
        return _local_downloaded_batch(workspace, [persistent_id]).get(persistent_id, "")
    except Exception:
        return ""


def _decided_ids(workspace: Path) -> set[str]:
    """Return persistent IDs with a logged decision/export (best-effort)."""
    try:
        db = Path(workspace) / "state.db"
        if not db.exists():
            return set()
        import sqlite3

        conn = sqlite3.connect(str(db), timeout=30.0)
        try:
            cur = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name='curation_actions'"
            )
            if not cur.fetchone():
                return set()
            rows = conn.execute(
                "SELECT DISTINCT dataset_id FROM curation_actions "
                "WHERE action IN ('decision','decided','exported','commit')"
            ).fetchall()
            return {str(r[0]) for r in rows}
        finally:
            conn.close()
    except Exception:
        return set()


class _SortItem(QTableWidgetItem):
    def __lt__(self, other):  # type: ignore[override]
        a = self.data(Qt.UserRole)
        b = other.data(Qt.UserRole) if isinstance(other, QTableWidgetItem) else None
        # Numeric/date sort when both sides carry a float epoch or number
        if isinstance(a, float) and isinstance(b, float):
            return a < b
        return self.text() < other.text()


def _display_state(state: str) -> str:
    s = (state or "").upper()
    if "REVIEW" in s:
        return "In Review"
    if s == "DRAFT":
        return "Draft"
    if s in ("RELEASED", "PUBLISHED"):
        return "Published"
    if s == "DEACCESSIONED":
        return "Deaccessioned"
    if not s:
        return "—"
    return s.title()


_DASHBOARD_CACHE_NAME = "dashboard_cache.json"


def dashboard_cache_key(base_url: str, collection: str) -> str:
    """Cache slot per instance + collection (both normalized, never raises)."""
    try:
        base = (base_url or "").rstrip("/").lower()
        coll = (collection or "").strip().lower() or "whole repository"
        return f"{base}|{coll}"
    except Exception:
        return "default"


def _dataset_fingerprint(ds: dict) -> tuple:
    """Server-meaningful identity of a row (local enrichment excluded).

    downloaded_at / total_size_bytes / size_from_cache are filled in from
    disk after the crawl, so they must NOT count as changes — otherwise
    every refresh would report every row as updated.
    """
    try:
        statuses = ds.get("publication_statuses") or []
        statuses = tuple(str(s or "") for s in statuses)
    except Exception:
        statuses = ()
    return (
        str(ds.get("title") or ""),
        str(ds.get("contact") or ""),
        str(ds.get("depositor") or ""),
        str(ds.get("date_created") or ""),
        str(ds.get("date_published") or ""),
        str(ds.get("collection") or ""),
        str(ds.get("state") or ""),
        bool(ds.get("has_draft")),
        statuses,
        str(ds.get("file_count") or ""),
        str(ds.get("curation_label") or ""),
        str(ds.get("curation_time") or ""),
        str(ds.get("curation_assigner") or ""),
    )


def diff_dashboard_datasets(old: list[dict], new: list[dict]) -> dict:
    """Diff two crawls by persistent_id → {added, removed, changed} pid lists.

    Never raises; corrupt rows are compared by fingerprint best-effort.
    """
    try:
        old_map = {str(d.get("persistent_id") or ""): d for d in (old or []) if isinstance(d, dict)}
        new_map = {str(d.get("persistent_id") or ""): d for d in (new or []) if isinstance(d, dict)}
        old_map.pop("", None)
        new_map.pop("", None)
        added = [pid for pid in new_map if pid not in old_map]
        removed = [pid for pid in old_map if pid not in new_map]
        changed = []
        for pid in old_map:
            if pid in new_map:
                try:
                    if _dataset_fingerprint(old_map[pid]) != _dataset_fingerprint(new_map[pid]):
                        changed.append(pid)
                except Exception:
                    continue
        return {"added": added, "removed": removed, "changed": changed}
    except Exception:
        return {"added": [], "removed": [], "changed": []}


def _merge_enriched_rows(existing: list[dict], batch: list[dict]) -> int:
    """Patch worker enrichment batches into painted rows, matched by pid.

    Copies scalars only (the worker keeps its live dicts for the final
    finished() payload). An "In Review" lock confirmation is never
    clobbered by an enrichment state, and a live enriched size wins over a
    stale disk-cache fill. Returns the merged count; never raises.
    """
    try:
        by_pid: dict[str, dict] = {}
        for d in existing or []:
            if not isinstance(d, dict):
                continue
            try:
                pid = str(d.get("persistent_id") or "")
            except Exception:
                continue
            if pid:
                by_pid[pid] = d
        merged = 0
        for src in batch or []:
            if not isinstance(src, dict):
                continue
            try:
                pid = str(src.get("persistent_id") or "")
            except Exception:
                continue
            dst = by_pid.get(pid) if pid else None
            if dst is None:
                continue
            try:
                for key in (
                    "total_size_bytes", "file_count", "depositor",
                    "state", "has_draft", "size_enriched",
                ):
                    if key not in src:
                        continue
                    if key == "state" and "REVIEW" in str(dst.get("state") or "").upper():
                        continue
                    dst[key] = src[key]
                if src.get("size_enriched"):
                    try:
                        dst.pop("size_from_cache", None)
                    except Exception:
                        pass
                merged += 1
            except Exception:
                continue
        return merged
    except Exception:
        return 0


def load_dashboard_cache(workspace: Path, key: str) -> dict | None:
    """Load cached {saved_at, datasets, labels} for one instance+collection slot.

    Returns None when missing/corrupt — never raises.
    """
    try:
        path = Path(workspace) / _DASHBOARD_CACHE_NAME
        if not path.exists():
            return None
        import json as _json

        raw = _json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return None
        entry = raw.get(key)
        if not isinstance(entry, dict):
            return None
        datasets = entry.get("datasets")
        labels = entry.get("labels", [])
        if not isinstance(datasets, list) or not isinstance(labels, list):
            return None
        return {
            "saved_at": str(entry.get("saved_at") or ""),
            "datasets": [d for d in datasets if isinstance(d, dict)],
            "labels": [str(lbl) for lbl in labels if str(lbl).strip()],
        }
    except Exception:
        return None


def save_dashboard_cache(workspace: Path, key: str, datasets: list[dict], labels: list) -> None:
    """Persist one dashboard slot (best-effort, never raises).

    Strips per-row `_sort_*` caches and caps stored slots to avoid unbounded
    growth (up to 10 collections × their full row sets).
    """
    try:
        import datetime as _dt
        import json as _json
        import os
        import tempfile

        path = Path(workspace) / _DASHBOARD_CACHE_NAME
        try:
            raw = _json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except Exception:
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        clean_rows = []
        for d in (datasets or []):
            if not isinstance(d, dict):
                continue
            clean_rows.append({k: v for k, v in d.items() if not k.startswith("_sort_")})
        raw[key] = {
            "saved_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
            "datasets": clean_rows,
            "labels": [str(lbl) for lbl in (labels or []) if str(lbl).strip()],
        }
        # Prune oldest slots beyond 10 to bound file size.
        try:
            if len(raw) > 10:
                # Keep current key + 9 most recent by saved_at.
                items = sorted(
                    raw.items(), key=lambda kv: str((kv[1] or {}).get("saved_at") or ""), reverse=True
                )
                raw = dict(items[:10])
                if key not in raw:
                    raw[key] = {
                        "saved_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
                        "datasets": clean_rows,
                        "labels": [str(lbl) for lbl in (labels or []) if str(lbl).strip()],
                    }
        except Exception:
            pass
        path.parent.mkdir(parents=True, exist_ok=True)
        data = _json.dumps(raw, indent=2)
        fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(data)
            os.replace(tmp_name, path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
    except Exception:
        pass


class DashboardView(QWidget):
    """Lists datasets. Emits openRequested(pid, title) on double-click."""

    openRequested = Signal(str, str)
    # Empty-state CTA: "Open Settings" reaches the main window's pane switch.
    settingsRequested = Signal()

    # Painting window (W-11): the QTableWidget allocates one item per
    # cell, so painting 25k rows × 12 columns on every keystroke is
    # unusable. Filtering/sorting still cover the full set; only the
    # painted rows are capped, and the status line says how many are
    # hidden so the cap is never silent.
    _MAX_PAINTED_ROWS = 2000

    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config
        self._worker: CrawlWorker | None = None
        self._all_datasets: list[dict] = []
        self._datasets: list[dict] = []
        # Metrics state "Checking…"/"Not fetched" until real data exists
        # (first crawl / cache paint); a visible 0 then always means a
        # completed check counted zero — zeros before that would claim
        # knowledge we don't have.
        self._crawled = False
        self._col_index = {key: i for i, (key, _h, _v) in enumerate(COLUMNS)}
        # Curation labels for the connected Dataverse, remembered with each
        # pull (refreshed on every reload; cached per instance on disk).
        self._curation_labels: list[str] = []
        self._curation_labels_cached: bool = False
        # Decision set cache: refreshed per crawl / on return from detail so
        # per-keystroke filtering never touches sqlite (_update_metrics).
        self._decided_cache: set[str] | None = None
        # Debounced search: rebuild the 12-col table 200 ms after the last
        # keystroke instead of on every keystroke.
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(200)
        self._filter_timer.timeout.connect(self._apply_filter)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(20)
        # Scoped to self: a bare `background` rule acts subtree-wide and
        # would override app-level backgrounds (e.g. the queue table face).
        self.setObjectName("DashboardView")
        self.setStyleSheet(f"QWidget#DashboardView {{ background: {BACKGROUND}; }}")

        # ---- Metrics cards (values always from real data; 0 when empty) ----
        self._metrics_row = QHBoxLayout()
        self._metrics_row.setSpacing(16)
        self._metric_cards: list[QFrame] = []
        self._metric_subs: list[str] = []
        # When the numbers below were last measured ("never" pre-crawl) —
        # carried in every card's tooltip so a 0 is never a mystery.
        self._last_refresh = "never"
        for accent, label, sub_text in [
            ("tertiary", "Pending Datasets", "drafts in queue"),
            ("primary", "In Review", "locked for review"),
            ("error", "Needs Action", "awaiting decision"),
        ]:
            card = self._make_metric_card(accent, label, sub_text)
            self._metrics_row.addWidget(card, 1)
            self._metric_cards.append(card)
            self._metric_subs.append(sub_text)
        outer.addLayout(self._metrics_row)

        # ---- Curation Queue card ----
        queue_card = QFrame()
        queue_card.setObjectName("Card")
        queue_card.setStyleSheet(
            f"QFrame#Card {{ background: {SURFACE_CONTAINER_LOWEST}; "
            f"border: 1px solid {OUTLINE_VARIANT}; border-radius: 8px; }}"
        )
        queue_layout = QVBoxLayout(queue_card)
        queue_layout.setContentsMargins(0, 0, 0, 0)
        queue_layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("QueueHeaderBar")
        header.setStyleSheet(
            f"QFrame#QueueHeaderBar {{ background: {SURFACE_CONTAINER}; border-bottom: 1px solid {OUTLINE_VARIANT}; "
            "border-top-left-radius: 8px; border-top-right-radius: 8px; }}"
        )
        header.setFixedHeight(64)
        hdr_layout = QHBoxLayout(header)
        hdr_layout.setContentsMargins(16, 12, 16, 12)
        hdr_layout.setSpacing(12)

        hdr_title = QLabel("Curation Queue")
        hdr_title.setStyleSheet(
            f"font-size: 16px; font-weight: 600; color: {ON_SURFACE}; "
            "background: transparent; border: none;"
        )
        hdr_layout.addWidget(hdr_title)

        search_wrap = QWidget()
        search_wrap.setObjectName("QueueSearchWrap")
        search_wrap.setStyleSheet("QWidget#QueueSearchWrap { background: transparent; }")
        search_layout = QHBoxLayout(search_wrap)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(0)
        self._filter_edit = make_search_field("Search datasets, authors...")
        self._filter_edit.textChanged.connect(lambda _t: self._filter_timer.start())
        search_layout.addWidget(self._filter_edit, 1)
        hdr_layout.addWidget(search_wrap, 1)

        self._state_filter = make_combo(
            [
                ("All Datasets", "All"),
                ("Draft unsubmitted", "DRAFT"),
                ("Published", "PUBLISHED"),
                ("In Review", "IN REVIEW"),
                ("Deaccessioned", "DEACCESSIONED"),
            ],
            min_width=130,
        )
        self._state_filter.currentTextChanged.connect(self._apply_filter)
        hdr_layout.addWidget(self._state_filter)

        self._label_filter = make_combo(
            [("All Curation Labels", ""), ("No label", "No label")],
            min_width=150,
            tip="Filter by the Dataverse curation label "
            "(per-instance set, pulled fresh on every refresh)",
        )
        self._label_filter.currentTextChanged.connect(self._apply_filter)
        hdr_layout.addWidget(self._label_filter)

        self._collection_filter = make_combo(
            [("All collections", "")],
            min_width=150,
            tip="Filter by subcollection (populated from the pulled datasets)",
        )
        self._collection_filter.currentTextChanged.connect(self._apply_filter)
        hdr_layout.addWidget(self._collection_filter)

        self._columns_btn = AppButton("Columns…", kind="chip")
        self._columns_btn.clicked.connect(self._show_columns_menu)
        hdr_layout.addWidget(self._columns_btn)

        refresh = AppButton("Refresh", kind="secondary")
        refresh.clicked.connect(self.reload)
        self._refresh_btn = refresh
        hdr_layout.addWidget(refresh)

        queue_layout.addWidget(header)

        # Queue table — standard behaviors (movable/resizable/sortable/copy).
        self._table = AppTable(
            [h for _k, h, _v in COLUMNS],
            widths={i: _COLUMN_WIDTHS.get(key, 120) for i, (key, _h, _v) in enumerate(COLUMNS)},
            row_height=40,
        )
        # No horizontal scrollbar on the dashboard: the queue reads at
        # window width (the stretch column absorbs any slack).
        self._table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # Flush under the banner header (last child: square top meets the
        # banner, 8px bottom meets the card border — see flush_table_style).
        self._table.setStyleSheet(flush_table_style())
        self._table.cellDoubleClicked.connect(self._on_double_click)
        # Keyboard parity for the queue: Enter/Return opens the focused row
        # (double-click alone locks out keyboard-only users), F5 refreshes,
        # Escape clears the search. See _on_table_key.
        self._table.installEventFilter(self)
        # Split header: the table's own header is hidden so its vertical
        # scrollbar spans rows only (starting underneath the header row).
        # This display header shares the table model and renders the
        # full-width header bar edge to edge above it.
        self._syncing_header = False
        self._table.horizontalHeader().setVisible(False)
        self._queue_header = QHeaderView(Qt.Horizontal)
        self._queue_header.setModel(self._table.model())
        self._queue_header.setSectionsMovable(True)
        self._queue_header.setSectionsClickable(True)
        self._queue_header.setStretchLastSection(True)
        self._queue_header.setFocusPolicy(Qt.NoFocus)
        self._queue_header.setFixedHeight(
            self._table.horizontalHeader().sizeHint().height()
        )
        # Same flush section rules as the table's own header had.
        self._queue_header.setStyleSheet(flush_table_style())
        self._sync_header_from_table()
        self._queue_header.sectionResized.connect(self._on_display_header_resized)
        self._table.horizontalHeader().sectionResized.connect(self._on_table_header_resized)
        self._queue_header.sectionMoved.connect(self._on_display_header_moved)
        self._table.horizontalHeader().sectionMoved.connect(self._on_table_header_moved)
        self._queue_header.sectionClicked.connect(self._on_header_clicked)
        # Content fit runs on the table header; mirror sizes to the display
        # header (sync flag keeps the mirror from persisting as a user drag).
        self._table.columns_fitted.connect(self._sync_header_from_table)
        queue_layout.addWidget(self._queue_header)
        # Table + first-run overlay occupy the same grid cell so the card
        # floats over the (empty) table without any layout surgery when
        # datasets arrive.
        queue_stack = QWidget()
        queue_stack.setObjectName("QueueStack")
        queue_stack.setStyleSheet("QWidget#QueueStack { background: transparent; }")
        stack_lay = QGridLayout(queue_stack)
        stack_lay.setContentsMargins(0, 0, 0, 0)
        stack_lay.setSpacing(0)
        stack_lay.addWidget(self._table, 0, 0)
        self._empty_overlay = self._build_empty_overlay()
        stack_lay.addWidget(self._empty_overlay, 0, 0)
        self._empty_overlay.hide()
        queue_layout.addWidget(queue_stack, 1)
        # Status renders as plain text like every other column.

        outer.addWidget(queue_card, 1)

        # One status pill (2026-10-07): the scope + filtered count and the
        # contextual message share the pill that previously existed — one
        # row only, ending just before the app mark at the bottom-right
        # (replaces the separate pill row + status bar).
        pill = QFrame()
        pill.setObjectName("StatusPill")
        pill.setStyleSheet(
            f"QFrame#StatusPill {{ background: {SURFACE_CONTAINER_LOWEST}; "
            f"border: 1px solid {OUTLINE_VARIANT}; border-radius: 8px; }}"
        )
        pill_lay = QHBoxLayout(pill)
        pill_lay.setContentsMargins(14, 6, 14, 6)
        pill_lay.setSpacing(8)
        self._status_lbl = _BarLabel("")
        self._status_lbl.setStyleSheet(
            f"font-size: 11px; color: {ON_SURFACE_VARIANT}; "
            "background: transparent; border: none;"
        )
        pill_lay.addWidget(self._status_lbl)
        pill_lay.setAlignment(self._status_lbl, Qt.AlignVCenter)
        self._status_sep = QLabel("·")
        self._status_sep.setStyleSheet(
            f"font-size: 11px; color: {ON_SURFACE_VARIANT}; "
            "background: transparent; border: none;"
        )
        self._status_sep.hide()
        pill_lay.addWidget(self._status_sep)
        pill_lay.setAlignment(self._status_sep, Qt.AlignVCenter)
        self._progress = _BarLabel("")
        self._progress.setStyleSheet(
            f"font-size: 11px; color: {ON_SURFACE_VARIANT}; "
            "background: transparent; border: none;"
        )
        # Circular progress ring, alongside the status text (the text
        # stays the accessible source of truth; the ring shows pace).
        self._ring = RingProgress(diameter=18)
        self._ring.hide()
        pill_lay.addWidget(self._ring)
        pill_lay.setAlignment(self._ring, Qt.AlignVCenter)
        pill_lay.addWidget(self._progress, 1)
        pill_lay.setAlignment(self._progress, Qt.AlignVCenter)

        def _sync_sep() -> None:
            # The dot joins scope and message only when both sides exist;
            # the tooltip carries the full message when it clips.
            msg = self._progress.text()
            self._status_sep.setVisible(bool(self._status_lbl.text()) and bool(msg))
            self._progress.setToolTip(msg or "")

        self._status_lbl.changed.connect(_sync_sep)
        self._progress.changed.connect(_sync_sep)

        foot = QHBoxLayout()
        foot.setSpacing(12)
        foot.addWidget(pill, 1)
        mark = QLabel()
        mark.setObjectName("DocentMark")
        try:
            from PySide6.QtGui import QPixmap as _QPixmap

            from ui.theme import mark_icon_path

            _pix = _QPixmap(mark_icon_path())
            if not _pix.isNull():
                # Native 16x16 — never upscale the pixel mark.
                mark.setPixmap(
                    _pix.scaledToHeight(16, Qt.SmoothTransformation)
                )
                mark.setToolTip("Dataverse Docent")
        except Exception:
            pass
        mark.setStyleSheet("border: none; background: transparent;")
        foot.addWidget(mark, 0, Qt.AlignVCenter)

        outer.addLayout(foot)
        _sync_sep()
        self._sync_status_bar()

        self._apply_default_column_visibility()
        # Snapshot the construction view for the Columns-menu reset, then
        # restore the user's saved queue view (widths/sort/hidden/order)
        # after defaults and mirror it onto the display header.
        try:
            from storage import restore_table_state, snapshot_table_view

            self._queue_snap = snapshot_table_view(self._table.horizontalHeader())
            if restore_table_state(
                self._config.app.workspace, "dashboard_queue",
                self._table.horizontalHeader(),
            ):
                self._table.disable_auto_fit()
            self._sync_header_from_table()
        except Exception:
            pass
        self._load_labels_cache()
        selectable_labels(self)
        # Cache-first paint: last crawl renders instantly so reopening the
        # app never starts from an empty table; reload() then checks for
        # changes/new datasets in the background and diffs into this view.
        self._shown_cache_key = ""
        self._cache_loaded = self._show_cached_dashboard()
        # First paint: named pre-crawl metric states + first-run card until
        # a crawl lands.
        self._update_metrics()

        if not (self._config.dataverse.api_token or "").strip():
            if not self._cache_loaded:
                self._progress.setText("Enter an API key in Settings (top nav) to load datasets.")
            else:
                self._progress.setText(
                    self._progress.text()
                    + " — enter an API key in Settings to check for updates."
                )
        else:
            self.reload()

    # -- curation labels (per-instance set, remembered with each pull) -----

    def _current_collection(self) -> str:
        """Return the configured collection alias ("" = whole repository)."""
        try:
            return (
                getattr(self._config.dataverse, "collection", "")
                or getattr(self._config.dataverse, "subtree", "")
                or ""
            ).strip()
        except Exception:
            return ""

    def _sync_status_bar(self) -> None:
        """Status bar reads `<base>[/<alias>]: <shown>/<total> datasets shown`.

        The scope (URL + collection alias) used to live in the page header;
        it moved to the bottom status bar on 2026-10-06, beside the filtered
        count. "shown" honours active search/label/state filters.
        """
        try:
            base = (self._config.dataverse.base_url or "").rstrip("/")
            alias = self._current_collection().strip("/")
            scope = f"{base}/{alias}" if alias else base
            shown_ds = getattr(self, "_datasets", None)
            if shown_ds is None:
                shown_ds = getattr(self, "_all_datasets", [])
            total = len(getattr(self, "_all_datasets", []) or [])
            lbl = getattr(self, "_status_lbl", None)
            if lbl is not None:
                lbl.setText(f"{scope}: {len(shown_ds)}/{total} datasets shown")
                lbl.setToolTip(
                    f"Active Dataverse: {base}\n"
                    f"Collection: {alias or 'whole repository'}"
                )
        except Exception:
            pass

    def _seed_labels_from_cache(self) -> None:
        """Labels for the current top-level collection from disk (no network).

        Seeds the filter AND the shared memory cache, so the dropdown shows
        the full allowed list — including labels no pulled dataset carries —
        before any crawl runs. Unknown top-levels reset to [] (stale labels
        from another collection must not linger); the crawl refills them.
        """
        try:
            from dataverse_client import read_allowed_labels_cache

            ws = Path(getattr(getattr(self._config, "app", None), "workspace", Path.home()))
            labels = read_allowed_labels_cache(
                Path(ws), self._config.dataverse.base_url, self._current_collection()
            )
            # read_* warms memory on hit; on miss the crawl fetches once.
            self._curation_labels = list(labels) if labels is not None else []
            self._curation_labels_cached = labels is not None
            self._rebuild_label_filter()
        except Exception:
            pass

    def _load_labels_cache(self) -> None:
        """Seed the label filter from the last pull (startup path)."""
        self._seed_labels_from_cache()

    # -- dashboard table cache (instant paint + change-only refresh) --------

    def _dashboard_cache_key(self) -> str:
        try:
            collection = (
                getattr(self._config.dataverse, "collection", "")
                or getattr(self._config.dataverse, "subtree", "")
                or ""
            )
            return dashboard_cache_key(self._config.dataverse.base_url, collection)
        except Exception:
            return "default"

    def _show_cached_dashboard(self) -> bool:
        """Paint the last crawl instantly (no network). True when shown."""
        try:
            ws = Path(getattr(getattr(self._config, "app", None), "workspace", Path.home()))
            entry = load_dashboard_cache(ws, self._dashboard_cache_key())
            if not entry or not entry.get("datasets"):
                return False
            cached_labels = entry.get("labels") or []
            # Union (not fill-if-empty): the disk seed is now probe-pure,
            # so the last session's in-use union must merge back in rather
            # than being dropped whenever the seed is non-empty.
            merged = list(self._curation_labels)
            for lab in cached_labels:
                if lab and lab not in merged:
                    merged.append(lab)
            if merged != self._curation_labels:
                self._curation_labels = merged
                self._curation_labels_cached = True
                try:
                    self._rebuild_label_filter()
                except Exception:
                    pass
            self._all_datasets = list(entry["datasets"])
            # Local enrichment only (downloaded dates, sizes, decisions).
            try:
                stamps = _local_downloaded_batch(
                    Path(ws), [ds.get("persistent_id", "") for ds in self._all_datasets]
                )
                for ds in self._all_datasets:
                    try:
                        ds["downloaded_at"] = stamps.get(ds.get("persistent_id", ""), "")
                    except Exception:
                        pass
                self._decided_cache = _decided_ids(Path(ws))
            except Exception:
                pass
            self._apply_size_cache(self._all_datasets)
            self._merge_row_labels()
            self._rebuild_collection_filter()
            self._crawled = True
            self._apply_filter()
            try:
                self._shown_cache_key = self._dashboard_cache_key()
            except Exception:
                pass
            saved = (entry.get("saved_at") or "")[:16].replace("T", " ")
            self._last_refresh = saved or "earlier session"
            self._sync_status_bar()
            self._progress.setText(
                f"Showing {len(self._all_datasets)} cached datasets"
                f"{(' from ' + saved) if saved else ''} — checking for changes…"
            )
            return True
        except Exception:
            return False

    def _rebuild_collection_filter(self) -> None:
        """Populate the subcollection combo from pulled data, keeping selection."""
        try:
            current = self._collection_filter.currentData()
        except Exception:
            current = ""
        try:
            self._collection_filter.blockSignals(True)
            self._collection_filter.clear()
            self._collection_filter.addItem("All collections", "")
            for coll in sorted({str(ds.get("collection") or "") for ds in self._all_datasets} - {""}):
                self._collection_filter.addItem(coll, coll)
            idx = self._collection_filter.findData(current)
            self._collection_filter.setCurrentIndex(idx if idx >= 0 else 0)
        finally:
            try:
                self._collection_filter.blockSignals(False)
            except Exception:
                pass

    def _rebuild_label_filter(self) -> None:
        """Rebuild the label combo, preserving the current selection."""
        try:
            current = self._label_filter.currentData()
            if current is None:
                current = self._label_filter.currentText()
        except Exception:
            current = ""
        try:
            self._label_filter.blockSignals(True)
            self._label_filter.clear()
            self._label_filter.addItem("All Curation Labels", "")
            for label in self._curation_labels:
                self._label_filter.addItem(label, label)
            self._label_filter.addItem("No label", "No label")
            idx = self._label_filter.findData(current)
            self._label_filter.setCurrentIndex(idx if idx >= 0 else 0)
        finally:
            try:
                self._label_filter.blockSignals(False)
            except Exception:
                pass

    def _on_labels_discovered(self, labels: list) -> None:
        clean = [str(lbl).strip() for lbl in (labels or []) if str(lbl).strip()]
        # Preserve first-appearance order, drop dupes
        seen: list[str] = []
        for label in clean:
            if label not in seen:
                seen.append(label)
        # Union with any labels seen on rows (a dataset can carry a label
        # outside the sampled allowed set, e.g. legacy values)
        for ds in self._all_datasets:
            lab = str(ds.get("curation_label") or "").strip()
            if lab and lab not in seen:
                seen.append(lab)
        self._curation_labels = seen
        self._curation_labels_cached = False
        self._rebuild_label_filter()
        # NOTE: the union is NOT written to curation_labels.json here — that
        # slot holds pure probe results only (see _on_allowed_probed). The
        # union persists via the dashboard cache at crawl end.
        try:
            from applog import get_app_log

            get_app_log().info(
                "Curation label filter options: "
                + (", ".join(f"'{lbl}'" for lbl in seen) if seen else "(none)")
            )
        except Exception:
            pass

    def _on_allowed_probed(self, payload: dict) -> None:
        """Stamp the disk slot — but only for a REAL probe round.

        The worker reports {"labels", "probed", "collection"} where probed
        is True only when it actually hit the network AND got a server
        answer (200, labels or confirmed-empty). Cache hits, empty pid
        lists, and transport/server-error rounds report probed=False and
        change nothing, so neither a stale union nor an outage can freeze
        a wrong [] into permanence.
        """
        try:
            if not isinstance(payload, dict) or payload.get("probed") is not True:
                return
            labels = payload.get("labels") or []
            collection = payload.get("collection", self._current_collection())
            from dataverse_client import write_allowed_labels_cache

            ws = Path(getattr(getattr(self._config, "app", None), "workspace", Path.home()))
            write_allowed_labels_cache(
                Path(ws),
                self._config.dataverse.base_url,
                collection,
                list(labels),
            )
        except Exception:
            pass

    # -- header helpers --------------------------------------------------

    def _build_empty_overlay(self) -> QWidget:
        """First-run card shown over the empty queue.

        Answers the only question a new user has — "where's my data?" — and
        routes them to Settings (API key lives there) with one primary click.
        """
        from ui.icons import icon_label as _empty_icon

        wrap = QWidget()
        wrap.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(24, 32, 24, 32)
        lay.setSpacing(0)

        card = QFrame()
        card.setObjectName("EmptyStateCard")
        card.setStyleSheet(
            f"QFrame#EmptyStateCard {{ background: {SURFACE_CONTAINER_LOWEST}; "
            f"border: 1px dashed {OUTLINE_VARIANT}; border-radius: 8px; }}"
        )
        inner = QVBoxLayout(card)
        inner.setContentsMargins(32, 32, 32, 28)
        inner.setSpacing(8)

        icon = _empty_icon("database", size=28, color=PRIMARY)
        head_wrap = QHBoxLayout()
        head_wrap.setSpacing(10)
        head_wrap.addWidget(icon, 0, Qt.AlignVCenter)
        self._empty_head = QLabel("No datasets loaded yet")
        self._empty_head.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {ON_SURFACE}; "
            "background: transparent; border: none;"
        )
        head_wrap.addWidget(self._empty_head, 1, Qt.AlignVCenter)
        inner.addLayout(head_wrap)

        self._empty_body = QLabel(
            "Add a Dataverse API key in Settings, then refresh to pull "
            "drafts and in-review datasets into the curation queue."
        )
        self._empty_body.setWordWrap(True)
        self._empty_body.setStyleSheet(
            f"font-size: 12px; color: {ON_SURFACE_VARIANT}; "
            "background: transparent; border: none;"
        )
        inner.addWidget(self._empty_body)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch(1)
        settings_btn = AppButton("Open Settings", kind="primary", size="md")
        settings_btn.clicked.connect(self.settingsRequested)
        btn_row.addWidget(settings_btn)
        inner.addLayout(btn_row)
        inner.addStretch(1)

        lay.addStretch(1)
        lay.addWidget(card)
        lay.addStretch(1)
        return wrap

    def _update_empty_state(self) -> None:
        """Show the first-run card whenever the queue itself is empty.

        Covers both the never-configured first run (no token) and a crawl
        that legitimately returned zero rows — never a filtered-out view
        (then _all_datasets is non-empty and the status line explains it).
        """
        try:
            has_token = bool((self._config.dataverse.api_token or "").strip())
        except Exception:
            has_token = False
        loading = self._worker is not None and self._worker.isRunning()
        show = not self._all_datasets and not loading
        try:
            if show:
                if has_token:
                    self._empty_head.setText("No datasets in this collection")
                    self._empty_body.setText(
                        "The connected collection returned no datasets. "
                        "Check the collection alias in Settings, or refresh "
                        "once more."
                    )
                else:
                    self._empty_head.setText("No datasets loaded yet")
                    self._empty_body.setText(
                        "Add a Dataverse API key in Settings, then refresh to "
                        "pull drafts and in-review datasets into the curation "
                        "queue."
                    )
            self._empty_overlay.setVisible(show)
        except Exception:
            pass

    def _make_metric_card(self, accent: str, label: str, sub: str) -> QFrame:
        """Slim single-line metric: icon + label on the left, value on the right."""
        card = QFrame()
        card.setObjectName("MetricCard")
        card.setProperty("accent", accent)
        border_color = {"tertiary": TERTIARY, "primary": PRIMARY, "error": ERROR}[accent]
        card.setStyleSheet(
            f"QFrame#MetricCard {{ background: {SURFACE_CONTAINER_LOWEST}; border: 1px solid {OUTLINE_VARIANT}; "
            "border-radius: 8px; }}"
        )
        card.setMinimumHeight(52)
        card.setToolTip(sub)
        lay = QHBoxLayout(card)
        lay.setContentsMargins(14, 8, 14, 8)
        lay.setSpacing(8)
        from ui.icons import icon_label as _metric_icon

        icon_map = {"tertiary": "clock", "primary": "eye", "error": "octagon-alert"}
        lay.addWidget(
            _metric_icon(icon_map.get(accent, "circle"), size=18, color=border_color), 0
        )
        lbl = QLabel(f"{label.upper()}  ·  {sub}")
        lbl.setStyleSheet(
            f"font-size: 11px; font-weight: 600; color: {ON_SURFACE_VARIANT}; "
            "letter-spacing: 0.5px; border: none; background: transparent;"
        )
        lay.addWidget(lbl, 1)
        v = QLabel("0")
        v.setObjectName("metricValue")
        v.setStyleSheet(_METRIC_VALUE_STYLE)
        v.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(v, 0)
        return card

    # -- column visibility -------------------------------------------------

    def _sync_header_from_table(self) -> None:
        """Copy sizes/hidden state from the table header to the display header."""
        try:
            table_hdr = self._table.horizontalHeader()
            self._syncing_header = True
            count = self._table.columnCount()
            for i in range(count):
                self._queue_header.resizeSection(i, table_hdr.sectionSize(i))
                self._queue_header.setSectionHidden(i, table_hdr.isSectionHidden(i))
            # Visual order too (restore/moves must reflect on both headers).
            for target in range(count):
                logical = next(
                    (i for i in range(count)
                     if table_hdr.visualIndex(i) == target),
                    None,
                )
                if logical is None:
                    continue
                try:
                    current = self._queue_header.visualIndex(logical)
                    if current != target:
                        self._queue_header.moveSection(current, target)
                except Exception:
                    continue
        finally:
            self._syncing_header = False

    def _save_queue_layout(self) -> None:
        """Persist the queue table's view (widths/sort/hidden/order)."""
        try:
            from storage import save_table_state

            save_table_state(
                self._config.app.workspace, "dashboard_queue",
                self._table.horizontalHeader(),
            )
        except Exception:
            pass

    def _on_display_header_resized(self, logical: int, _old: int, new: int) -> None:
        if self._syncing_header:
            return
        self._syncing_header = True
        try:
            self._table.horizontalHeader().resizeSection(logical, new)
        finally:
            self._syncing_header = False
        self._save_queue_layout()

    def _on_table_header_resized(self, logical: int, _old: int, new: int) -> None:
        if self._syncing_header:
            return
        self._syncing_header = True
        try:
            self._queue_header.resizeSection(logical, new)
        finally:
            self._syncing_header = False

    def _on_display_header_moved(self, logical: int, old_visual: int, new_visual: int) -> None:
        if self._syncing_header:
            return
        self._syncing_header = True
        try:
            self._table.horizontalHeader().moveSection(old_visual, new_visual)
        finally:
            self._syncing_header = False
        self._save_queue_layout()

    def _on_table_header_moved(self, logical: int, old_visual: int, new_visual: int) -> None:
        if self._syncing_header:
            return
        self._syncing_header = True
        try:
            self._queue_header.moveSection(old_visual, new_visual)
        finally:
            self._syncing_header = False

    def _on_header_clicked(self, logical: int) -> None:
        """Sort the table like its own header click would (toggle on repeat)."""
        table_hdr = self._table.horizontalHeader()
        if table_hdr.sortIndicatorSection() == logical and table_hdr.isSortIndicatorShown():
            order = Qt.DescendingOrder if table_hdr.sortIndicatorOrder() == Qt.AscendingOrder else Qt.AscendingOrder
        else:
            order = Qt.AscendingOrder
        self._table.sortItems(logical, order)
        table_hdr.setSortIndicator(logical, order)
        self._queue_header.setSortIndicator(logical, order)
        self._queue_header.setSortIndicatorShown(True)
        self._save_queue_layout()

    def _set_column_visible(self, idx: int, visible: bool) -> None:
        """Hide/show a column on the table and the display header together.

        No save here on purpose: __init__ calls this for defaults, and a
        save during defaults would clobber the persisted view before
        restore_table_state reads it. The Columns… menu (the only user
        surface) saves after toggling.
        """
        self._table.setColumnHidden(idx, not visible)
        try:
            self._queue_header.setSectionHidden(idx, not visible)
        except Exception:
            pass

    def _apply_default_column_visibility(self) -> None:
        for i, (_key, _h, visible) in enumerate(COLUMNS):
            self._set_column_visible(i, visible)

    def _show_columns_menu(self) -> None:
        self._show_columns_menu_at(
            self._columns_btn.mapToGlobal(self._columns_btn.rect().bottomLeft())
        )

    def _show_columns_menu_at(self, pos) -> None:  # type: ignore[no-untyped-def]
        menu = QMenu(self)
        for idx, (_key, header, _v) in enumerate(COLUMNS):
            action = QAction(header, menu)
            action.setCheckable(True)
            action.setChecked(not self._table.isColumnHidden(idx))
            action.toggled.connect(
                lambda checked, i=idx: (
                    self._set_column_visible(i, checked),
                    self._save_queue_layout(),
                )
            )
            menu.addAction(action)
        menu.addSeparator()
        try:
            from ui.icons import icon as _menu_icon

            reset_action = QAction(
                _menu_icon("rotate-ccw"), "Reset columns && sorting", menu
            )
        except Exception:
            reset_action = QAction("Reset columns && sorting", menu)
        reset_action.setToolTip("Restore default widths, order, visibility and sort")
        reset_action.triggered.connect(self._reset_queue_layout)
        menu.addAction(reset_action)
        menu.exec(pos)

    def _reset_queue_layout(self) -> None:
        """Reset the queue table to its construction view, then repaint."""
        try:
            from storage import apply_table_view, clear_table_state

            snap = getattr(self, "_queue_snap", None)
            clear_table_state(self._config.app.workspace, "dashboard_queue")
            self._table.enable_auto_fit()
            if isinstance(snap, dict):
                apply_table_view(self._table.horizontalHeader(), snap)
            self._sync_header_from_table()
            # Mirror the sort indicator onto the display header, then
            # repaint rows (repopulation re-sorts exactly like a fresh
            # table, so reset reproduces startup order precisely).
            try:
                table_hdr = self._table.horizontalHeader()
                self._queue_header.setSortIndicator(
                    table_hdr.sortIndicatorSection(),
                    table_hdr.sortIndicatorOrder(),
                )
                self._queue_header.setSortIndicatorShown(
                    table_hdr.isSortIndicatorShown()
                )
            except Exception:
                pass
            self._apply_filter()
        except Exception:
            pass

    # -- data --------------------------------------------------------------

    def stop(self) -> None:
        """Cooperatively stop a running crawl (used on app shutdown)."""
        try:
            worker = getattr(self, "_worker", None)
            if worker is not None and worker.isRunning():
                worker.requestInterruption()
                worker.quit()
                worker.wait(3000)
        except Exception:
            pass

    def reload(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._progress.setText("Already loading — please wait…")
            return
        # The collection may have changed in Settings: reseed the label
        # filter for the new top-level collection from disk (no network).
        # A new top-level with no cache resets the combo; the crawl refills
        # it with one shared call. Sub-collections reuse the cached list.
        self._seed_labels_from_cache()
        self._sync_status_bar()
        # Cache-first: keep the painted rows on screen while the background
        # crawl checks for changes — never wipe to an empty table on open.
        # Exception: the instance/collection switched (different cache slot),
        # so the old rows belong to another query and must go.
        try:
            current_key = self._dashboard_cache_key()
        except Exception:
            current_key = ""
        if (
            getattr(self, "_shown_cache_key", "")
            and current_key
            and self._shown_cache_key != current_key
        ):
            self._all_datasets = []
            self._datasets = []
            self._shown_cache_key = ""
            try:
                self._table.setSortingEnabled(False)
                self._table.setRowCount(0)
                self._table.setSortingEnabled(True)
            except Exception:
                pass
        had_rows = bool(getattr(self, "_all_datasets", None))

        if not (self._config.dataverse.api_token or "").strip():
            self._refresh_btn.setEnabled(True)
            if not had_rows:
                self._progress.setText("Enter an API key in Settings (top nav) to load datasets.")
            self._update_metrics()
            return

        self._refresh_btn.setEnabled(False)
        # Fresh crawl: reset the ring (it stays hidden until the first
        # fraction arrives, so an idle dashboard shows no spinner).
        try:
            self._ring.reset()
            self._ring.hide()
        except Exception:
            pass
        if had_rows:
            self._progress.setText(
                f"Checking for changes… (showing {len(self._all_datasets)} cached datasets)"
            )
        else:
            self._progress.setText("Contacting Dataverse…")

        collection = (
            getattr(self._config.dataverse, "collection", "")
            or getattr(self._config.dataverse, "subtree", "")
            or ""
        ).strip()
        self._worker = CrawlWorker(
            self._config.dataverse.base_url,
            self._config.dataverse.api_token,
            collection,
            self,
        )
        self._worker.progress.connect(lambda msg: self._progress.setText(msg))
        self._worker.progressFraction.connect(self._on_progress_fraction)
        self._worker.labelsDiscovered.connect(self._on_labels_discovered)
        self._worker.allowedProbed.connect(self._on_allowed_probed)
        self._worker.enriched.connect(self._on_enrichment_batch)
        self._worker.finished.connect(self._on_crawl_finished)
        self._worker.error.connect(self._on_crawl_error)
        self._worker.finished.connect(lambda: setattr(self, "_worker", None))
        self._worker.error.connect(lambda: setattr(self, "_worker", None))
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.error.connect(self._worker.deleteLater)
        self._worker.start()
        # Pre-crawl cards now read "Checking…" instead of staying idle.
        self._update_metrics()

    def _apply_size_cache(self, datasets: list[dict]) -> None:
        """Fill unknown Size cells from the downloaded-metadata cache.

        Search records carry no byte totals; once a dataset's metadata has
        been loaded in the detail view, its summed inventory size is cached
        on disk and shown here instead of "—".
        """
        try:
            from storage import read_size_cache

            ws = getattr(getattr(self._config, "app", None), "workspace", Path.home())
            cache = read_size_cache(Path(ws))
        except Exception:
            return
        for ds in datasets:
            if ds.get("total_size_bytes") is None:
                entry = cache.get(ds.get("persistent_id", ""))
                if entry:
                    ds["total_size_bytes"] = entry.get("size", 0)
                    ds["size_from_cache"] = True

    def refresh_local_columns(self) -> None:
        """Re-read disk state (sizes, downloaded dates) and repaint — no network."""
        try:
            ws = getattr(getattr(self._config, "app", None), "workspace", Path.home())
            stamps = _local_downloaded_batch(
                Path(ws), [ds.get("persistent_id", "") for ds in self._all_datasets]
            )
            for ds in self._all_datasets:
                try:
                    ds["downloaded_at"] = stamps.get(ds.get("persistent_id", ""), "")
                except Exception:
                    pass
            self._decided_cache = _decided_ids(Path(ws))
            self._apply_size_cache(self._all_datasets)
            self._apply_filter()
        except Exception:
            pass

    def _merge_row_labels(self) -> None:
        """Union row-carried labels into the filter set (fresh pull, not stale).

        `labelsDiscovered` fires before `finished`, so its union loop only sees
        the previous pull. This runs after `_all_datasets` is replaced, so
        per-dataset statuses from a working token always reach the combo even
        when the allowed-set call is forbidden.
        """
        seen = list(self._curation_labels)
        for ds in self._all_datasets:
            lab = str(ds.get("curation_label") or "").strip()
            if lab and lab not in seen:
                seen.append(lab)
        if seen != self._curation_labels:
            self._curation_labels = seen
            self._rebuild_label_filter()
            # Union only; the probe-pure slot is stamped by
            # _on_allowed_probed, and the union persists via
            # save_dashboard_cache at crawl end.

    def _on_progress_fraction(self, fraction: float) -> None:
        """Drive the progress ring from the worker's overall fraction."""
        try:
            self._ring.show()
            self._ring.setFraction(fraction)
            self._ring.setAccessibleDescription(self._ring.accessibleDescription())
        except Exception:
            pass

    def _hide_ring(self) -> None:
        """Hide the progress ring once its work is done."""
        try:
            self._ring.hide()
        except Exception:
            pass

    def _on_enrichment_batch(self, batch: list[dict]) -> None:
        """Merge one worker enrichment batch into the painted table.

        Batches arrive while the crawl runs (progressive paint); the final
        finished() payload replaces the rows wholesale, so a missed batch
        only costs liveness, never correctness.
        """
        try:
            if not batch:
                return
            if _merge_enriched_rows(getattr(self, "_all_datasets", []), batch):
                self._apply_filter()
        except Exception:
            pass

    def _on_crawl_finished(self, datasets: list[dict]) -> None:
        try:
            self._worker = None
            # Crawl done: show the completed state briefly, then clear the
            # ring — a permanent check mark would read as "still working".
            try:
                self._ring.setFraction(1.0)
                QTimer.singleShot(1200, self._hide_ring)
            except Exception:
                pass
            # Diff against what is on screen (the cache) BEFORE replacing it,
            # so reopening the app reports only changes/new datasets.
            try:
                previous = list(getattr(self, "_all_datasets", []) or [])
            except Exception:
                previous = []
            had_previous = bool(previous)
            try:
                summary = diff_dashboard_datasets(previous, datasets or [])
            except Exception:
                summary = {"added": [], "removed": [], "changed": []}
            # Enrich with the local Downloaded date once per crawl (batched:
            # one sqlite connect, not one per dataset) + refresh decisions.
            ws = getattr(getattr(self._config, "app", None), "workspace", Path.home())
            stamps = _local_downloaded_batch(
                Path(ws), [ds.get("persistent_id", "") for ds in datasets]
            )
            for ds in datasets:
                try:
                    ds["downloaded_at"] = stamps.get(ds.get("persistent_id", ""), "")
                except Exception:
                    pass
            try:
                self._decided_cache = _decided_ids(Path(ws))
            except Exception:
                self._decided_cache = set()
            self._apply_size_cache(datasets)
            self._all_datasets = datasets
            self._crawled = True
            try:
                import datetime as _dt_now

                self._last_refresh = _dt_now.datetime.now().strftime(
                    "%Y-%m-%d %H:%M"
                )
            except Exception:
                self._last_refresh = "just now"
            self._merge_row_labels()
            self._rebuild_collection_filter()
            # Persist this crawl so the next app open paints instantly.
            try:
                save_dashboard_cache(ws, self._dashboard_cache_key(), datasets, self._curation_labels)
                self._shown_cache_key = self._dashboard_cache_key()
            except Exception:
                pass
            self._refresh_btn.setEnabled(True)
            self._apply_filter()
            # Change-only summary (replaces the old "Received N" line).
            try:
                n_new = len(summary.get("added", []))
                n_chg = len(summary.get("changed", []))
                n_del = len(summary.get("removed", []))
                total = len(datasets)
                if not had_previous:
                    self._progress.setText(
                        f"{total} datasets shown — double-click a row to open"
                    )
                elif not (n_new or n_chg or n_del):
                    self._progress.setText(
                        f"No changes — {total} datasets up to date. Double-click a row to open"
                    )
                else:
                    parts = []
                    if n_new:
                        parts.append(f"{n_new} new")
                    if n_chg:
                        parts.append(f"{n_chg} updated")
                    if n_del:
                        parts.append(f"{n_del} removed")
                    self._progress.setText(
                        f"{', '.join(parts)} — {total} datasets shown. Double-click a row to open"
                    )
            except Exception:
                pass
        except Exception as exc:
            import traceback
            self._refresh_btn.setEnabled(True)
            self._progress.setText("Error rendering results — details in dialog")
            from ui.dialogs import show_warning
            show_warning(
                self, "Dashboard",
                "Couldn't display the dataset list.",
                details=f"{exc}\n\n{traceback.format_exc()}",
            )

    def _update_metrics(self) -> None:
        """All three cards from REAL data; named states before the first crawl.

        - Pending Datasets: versionState DRAFT (plain drafts awaiting triage)
        - In Review: locked for review (confirmed via the locks endpoint)
        - Needs Action: drafts + in-review items with no logged decision yet

        Before the first crawl finishes each card states its condition in
        words ("Checking…" while the crawl runs, "Not fetched" when idle)
        instead of a bare "—", so a visible 0 can only ever mean a completed
        check counted zero; every card's tooltip carries the last-refresh
        time ("never" until something has been measured).
        """
        loading = self._worker is not None and self._worker.isRunning()
        if not self._crawled:
            state = "Checking…" if loading else "Not fetched"
            note = (
                "Crawl in progress — counts land when it finishes."
                if loading
                else
                "No crawl has completed yet — add an API key in Settings, "
                "then press Refresh."
            )
            for card, sub in zip(self._metric_cards, self._metric_subs, strict=False):
                v_lbl = card.findChild(QLabel, "metricValue")
                if v_lbl:
                    v_lbl.setText(state)
                    v_lbl.setStyleSheet(_METRIC_STATE_STYLE)
                card.setToolTip(
                    f"{sub}\n{note}\nLast refresh: {self._last_refresh}"
                )
            self._update_empty_state()
            return
        in_review = sum(
            1 for d in self._all_datasets if "REVIEW" in (d.get("state") or "").upper()
        )
        pending = sum(
            1 for d in self._all_datasets if (d.get("state") or "").upper() == "DRAFT"
        )
        try:
            ws = getattr(getattr(self._config, "app", None), "workspace", Path.home())
            decided = self._decided_cache
            if decided is None:
                # No crawl yet (or cache cleared): one live query, then keep it.
                decided = _decided_ids(Path(ws))
                self._decided_cache = decided
        except Exception:
            decided = set()
        needs_action = 0
        if self._all_datasets:
            for d in self._all_datasets:
                st = (d.get("state") or "").upper()
                if (st == "DRAFT" or "REVIEW" in st) and d.get("persistent_id") not in decided:
                    needs_action += 1
        vals = [pending, in_review, needs_action]
        for card, sub, val in zip(
            self._metric_cards, self._metric_subs, vals, strict=False
        ):
            v_lbl = card.findChild(QLabel, "metricValue")
            if v_lbl:
                v_lbl.setText(str(val))
                v_lbl.setStyleSheet(_METRIC_VALUE_STYLE)
            card.setToolTip(f"{sub}\nLast refresh: {self._last_refresh}")
        self._update_empty_state()

    def _cell_text(self, ds: dict, key: str) -> str:
        if key == "total_size_bytes":
            raw = ds.get(key)
            if raw is None or raw == "":
                return "—"
            return _human_size(raw)
        if key == "state":
            return _display_state(ds.get("state") or "")
        v = ds.get(key, "")
        return "" if v is None else str(v)

    def _cell_sort_key(self, ds: dict, key: str) -> float | str:
        # Fast path: precomputed epoch cached at ingest (avoids 12k
        # strptime calls per keystroke on 1000-row tables).
        if key in ("date_created", "date_published", "downloaded_at"):
            cached = ds.get(f"_sort_{key}")
            if isinstance(cached, (int, float)):
                return float(cached)
            raw = ds.get(key, "")
            if raw is None or raw == "":
                return 0.0
            epoch = _parse_date_epoch(str(raw))
            try:
                ds[f"_sort_{key}"] = epoch
            except Exception:
                pass
            return epoch
        raw = ds.get(key, "")
        if key in ("file_count", "total_size_bytes"):
            if raw is None or raw == "":
                # Unknown size (None/"—") sorts below real sizes.
                return -1.0
            try:
                return float(raw or 0)
            except Exception:
                return -1.0
        return str(raw or "").lower()

    def _apply_filter(self) -> None:
        try:
            text = (self._filter_edit.text() or "").strip().lower()
            try:
                state_key = self._state_filter.currentData() or "All"
            except Exception:
                state_key = "All"
            try:
                wanted_label = self._label_filter.currentData()
            except Exception:
                wanted_label = ""
            if wanted_label is None:
                wanted_label = ""
            try:
                wanted_collection = self._collection_filter.currentData() or ""
            except Exception:
                wanted_collection = ""
            filtered = []
            for ds in self._all_datasets:
                ds_state = (ds.get("state") or "").upper()
                if state_key != "All":
                    wanted = str(state_key).upper()
                    if wanted == "PUBLISHED" and ds_state not in ("RELEASED", "PUBLISHED"):
                        continue
                    elif wanted == "DRAFT" and ds_state != "DRAFT":
                        continue
                    elif wanted == "IN REVIEW" and "REVIEW" not in ds_state:
                        continue
                    elif wanted == "DEACCESSIONED" and "DEACCESSIONED" not in ds_state:
                        continue
                    elif wanted not in ("PUBLISHED", "DRAFT", "IN REVIEW", "DEACCESSIONED") and wanted != ds_state:
                        continue
                if wanted_label == "No label":
                    if str(ds.get("curation_label") or "").strip():
                        continue
                elif wanted_label:
                    ds_label = str(ds.get("curation_label") or "").strip().lower()
                    if ds_label != wanted_label.strip().lower():
                        continue
                if wanted_collection:
                    if str(ds.get("collection") or "") != wanted_collection:
                        continue
                if text:
                    haystack = " ".join(
                        str(ds.get(k, "")) for k in (
                            "title", "persistent_id", "contact", "depositor",
                            "collection", "state", "curation_label",
                        )
                    ).lower()
                    if text not in haystack:
                        continue
                filtered.append(ds)
            self._datasets = filtered
            self._update_metrics()
            self._sync_status_bar()
            if not self._all_datasets:
                self._progress.setText(
                    "No datasets found in this collection. Check the collection alias "
                    "or add an API token for drafts."
                )
            elif not filtered:
                self._progress.setText(
                    f"No datasets match filter — {len(self._all_datasets)} total. "
                    "Clear the filter to see all."
                )
            else:
                # Counts + scope live in the status bar now — the pill keeps
                # the standing hint instead of repeating them.
                self._progress.setText("Double-click a row to open it")

            # Painting window: the table is a QTableWidget (one heap
            # item per cell), so 25k rows × 12 columns is 300k items
            # rebuilt on every filter keystroke. Filter and sort still
            # run over the FULL set; only the painted rows are capped.
            paint_rows = filtered[: DashboardView._MAX_PAINTED_ROWS]
            if len(paint_rows) < len(filtered):
                self._progress.setText(
                    f"Showing {len(paint_rows):,} of {len(filtered):,} matching "
                    f"({len(self._all_datasets):,} total) — narrow the filter to see more"
                )

            self._table.setSortingEnabled(False)
            self._table.setRowCount(len(paint_rows))
            mono = QFont("JetBrains Mono")
            for row, ds in enumerate(paint_rows):
                for col, (key, _h, _v) in enumerate(COLUMNS):
                    text_val = self._cell_text(ds, key)
                    item = _SortItem(text_val)
                    item.setToolTip(text_val)
                    if key == "total_size_bytes":
                        if text_val == "—":
                            if ds.get("size_pending"):
                                item.setToolTip("Beyond the enrichment cap — open the dataset to load its file inventory")
                            else:
                                item.setToolTip("Size unknown — open the dataset to load its file inventory")
                        elif ds.get("size_enriched"):
                            item.setToolTip(f"{text_val} — summed from live file inventory")
                        elif ds.get("size_from_cache"):
                            item.setToolTip(f"{text_val} — summed from downloaded metadata")
                    sort_key = self._cell_sort_key(ds, key)
                    item.setData(Qt.UserRole, sort_key)
                    if key in ("date_created", "date_published", "downloaded_at",
                               "persistent_id"):
                        item.setFont(mono)
                    if key == "title":
                        f = item.font()
                        f.setBold(True)
                        item.setFont(f)
                    self._table.setItem(row, col, item)
            self._table.setSortingEnabled(True)
            # Content-width columns first (no-op once fitted/locked); the
            # columns_fitted signal mirrors sizes onto the display header.
            self._table.fit_columns_to_content()
            self._table.viewport().update()
        except Exception as exc:
            import traceback
            self._refresh_btn.setEnabled(True)
            self._progress.setText("Error rendering results — details in dialog")
            from ui.dialogs import show_warning
            show_warning(
                self, "Dashboard",
                "Couldn't display the dataset list.",
                details=f"{exc}\n\n{traceback.format_exc()}",
            )

    def _on_crawl_error(self, msg: str) -> None:
        from ui.dialogs import describe_error, show_warning
        self._worker = None
        self._refresh_btn.setEnabled(True)
        self._progress.setText("Error — details in dialog (Retry available)")
        # Red ring: the failure is visible without opening the dialog.
        try:
            self._ring.show()
            self._ring.setError()
        except Exception:
            pass
        headline, details = describe_error(msg)
        show_warning(
            self,
            "Can't load datasets",
            headline,
            details=details,
            retry=self.reload,
        )
        self._update_empty_state()

    def eventFilter(self, obj, event):
        """Keyboard parity for the queue table (P0).

        Enter/Return opens the focused row (double-click alone locks out
        keyboard-only users), F5 refreshes, Escape clears the search box.
        """
        if obj is self._table and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                row = self._table.currentRow()
                if row >= 0 and self._table.rowCount():
                    self._on_double_click(row, 0)
                return True
            if key == Qt.Key.Key_F5:
                self.reload()
                return True
            if key == Qt.Key.Key_Escape:
                if self._filter_edit.text():
                    self._filter_edit.clear()
                    return True
        return super().eventFilter(obj, event)

    def _on_double_click(self, row: int, _col: int) -> None:
        # Visual row == filtered row order only when sorting is off; with
        # sorting on, items travel with their rows, so read the PID cell
        # of the CLICKED visual row directly.
        try:
            pid_col = self._col_index.get("persistent_id", 1)
            title_col = self._col_index.get("title", 0)
            pid_item = self._table.item(row, pid_col)
            title_item = self._table.item(row, title_col)
            pid = pid_item.text().strip() if pid_item else ""
            title = title_item.text().strip() if title_item else ""
            if not pid:
                # Fallback: match by title (titles are unique enough here)
                match = next(
                    (d for d in self._datasets if d.get("title") == title), None
                )
                if match:
                    pid = match.get("persistent_id", "")
                    title = match.get("title", title)
            if pid:
                self.openRequested.emit(pid, title or pid)
        except Exception:
            pass
