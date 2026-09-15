"""Dashboard view: metrics + curation queue.

Table uses plain QTableWidgetItems only (no cell widgets) so text never
overlaps/garbles and Qt sorting moves whole rows. All columns are
user-resizable (Interactive) with the last visible column stretching to fill
leftover space, and toggleable via Columns… including the local Downloaded
date sourced from the workspace state.db + staged folders.
"""

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from config import Config
from ui.theme import ERROR, OUTLINE_VARIANT, PRIMARY, SURFACE_CONTAINER_LOWEST, TERTIARY, enable_table_copy, selectable_labels
from ui.widgets import AppButton, AppTable, make_combo, make_search_field
from ui.workers import CrawlWorker

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


def _human_size(n: int) -> str:
    try:
        n = int(n)
    except Exception:
        return str(n)
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024  # type: ignore[assignment]
    return f"{n:.1f} GB"


def _sanitize(pid: str) -> str:
    return (pid or "").replace(":", "_").replace("/", "_").replace("\\", "_")


def _local_downloaded_batch(workspace: Path, pids: list[str]) -> dict[str, str]:
    """Downloaded timestamps for many datasets with ONE sqlite connect.

    Same sources/semantics as _local_downloaded (state.db download actions,
    staged-dir mtime fallback); "" or "YYYY-MM-DD HH:MM" per pid.
    """
    out = {p: "" for p in pids}
    try:
        ws = Path(workspace)
        db = ws / "state.db"
        if db.exists():
            import sqlite3

            conn = sqlite3.connect(str(db))
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
            if staged.exists():
                out[pid] = datetime.datetime.fromtimestamp(
                    staged.stat().st_mtime
                ).strftime("%Y-%m-%d %H:%M")
    except Exception:
        pass
    return out


def _local_downloaded(workspace: Path, persistent_id: str) -> str:
    """Downloaded timestamp for one dataset from local system state.

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
    """Persistent IDs with a logged decision/export (best-effort)."""
    try:
        db = Path(workspace) / "state.db"
        if not db.exists():
            return set()
        import sqlite3

        conn = sqlite3.connect(str(db))
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


def load_dashboard_cache(workspace: Path, key: str) -> dict | None:
    """Cached {saved_at, datasets, labels} for one instance+collection slot.

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
            "labels": [str(l) for l in labels if str(l).strip()],
        }
    except Exception:
        return None


def save_dashboard_cache(workspace: Path, key: str, datasets: list[dict], labels: list) -> None:
    """Persist one dashboard slot (best-effort, never raises)."""
    try:
        import datetime as _dt
        import json as _json

        path = Path(workspace) / _DASHBOARD_CACHE_NAME
        try:
            raw = _json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except Exception:
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        raw[key] = {
            "saved_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
            "datasets": [d for d in (datasets or []) if isinstance(d, dict)],
            "labels": [str(l) for l in (labels or []) if str(l).strip()],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_json.dumps(raw, indent=2), encoding="utf-8")
    except Exception:
        pass


class DashboardView(QWidget):
    """Lists datasets. Emits openRequested(pid, title) on double-click."""

    openRequested = Signal(str, str)

    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config
        self._worker: CrawlWorker | None = None
        self._all_datasets: list[dict] = []
        self._datasets: list[dict] = []
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
        self.setStyleSheet("background: #faf8ff;")

        # ---- Title row ----
        h = QLabel("Dashboard Overview")
        h.setStyleSheet("font-size: 22px; font-weight: 700; color: #131b2e;")
        outer.addWidget(h)

        # ---- Metrics cards (values always from real data; 0 when empty) ----
        self._metrics_row = QHBoxLayout()
        self._metrics_row.setSpacing(16)
        self._metric_cards: list[QFrame] = []
        for accent, label, sub_text in [
            ("tertiary", "Pending Datasets", "drafts in queue"),
            ("primary", "In Review", "locked for review"),
            ("error", "Needs Action", "awaiting decision"),
        ]:
            card = self._make_metric_card(accent, label, sub_text)
            self._metrics_row.addWidget(card, 1)
            self._metric_cards.append(card)
        outer.addLayout(self._metrics_row)

        # ---- Curation Queue card ----
        queue_card = QFrame()
        queue_card.setObjectName("Card")
        queue_card.setStyleSheet(
            f"QFrame#Card {{ background: {SURFACE_CONTAINER_LOWEST}; "
            f"border: 1px solid {OUTLINE_VARIANT}; border-radius: 12px; }}"
        )
        queue_layout = QVBoxLayout(queue_card)
        queue_layout.setContentsMargins(0, 0, 0, 0)
        queue_layout.setSpacing(0)

        header = QFrame()
        header.setStyleSheet(
            f"QFrame {{ background: #eaedff; border-bottom: 1px solid {OUTLINE_VARIANT}; "
            "border-top-left-radius: 12px; border-top-right-radius: 12px; }}"
        )
        header.setFixedHeight(64)
        hdr_layout = QHBoxLayout(header)
        hdr_layout.setContentsMargins(16, 12, 16, 12)
        hdr_layout.setSpacing(12)

        hdr_title = QLabel("Curation Queue")
        hdr_title.setStyleSheet(
            "font-size: 16px; font-weight: 600; color: #131b2e; "
            "background: transparent; border: none;"
        )
        hdr_layout.addWidget(hdr_title)

        search_wrap = QWidget()
        search_wrap.setStyleSheet("background: transparent;")
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
        self._table.cellDoubleClicked.connect(self._on_double_click)
        queue_layout.addWidget(self._table, 1)
        # Status renders as plain text like every other column.

        outer.addWidget(queue_card, 1)

        self._subtitle = QLabel("")
        self._subtitle.setStyleSheet("font-size: 11px; color: #424656;")
        outer.addWidget(self._subtitle)

        self._progress = QLabel("")
        self._progress.setStyleSheet(
            "font-size: 11px; color: #424656; background: #ffffff; "
            "border: 1px solid #c3c6d8; border-radius: 8px; padding: 8px 12px;"
        )
        self._progress.setWordWrap(True)
        outer.addWidget(self._progress)

        self._apply_default_column_visibility()
        self._load_labels_cache()
        selectable_labels(self)
        # Cache-first paint: last crawl renders instantly so reopening the
        # app never starts from an empty table; reload() then checks for
        # changes/new datasets in the background and diffs into this view.
        self._shown_cache_key = ""
        self._cache_loaded = self._show_cached_dashboard()

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

    def _labels_cache_path(self) -> Path:
        try:
            ws = Path(getattr(getattr(self._config, "app", None), "workspace", Path.home()))
        except Exception:
            ws = Path.home()
        return ws / "curation_labels.json"

    def _labels_cache_key(self) -> str:
        return (self._config.dataverse.base_url or "").rstrip("/").lower()

    def _load_labels_cache(self) -> None:
        """Seed the label filter from the last pull for this instance."""
        try:
            import json

            path = self._labels_cache_path()
            if not path.exists():
                return
            data = json.loads(path.read_text(encoding="utf-8"))
            labels = data.get(self._labels_cache_key(), {}).get("labels", [])
            if isinstance(labels, list) and labels:
                self._curation_labels = [str(l) for l in labels if str(l).strip()]
                self._curation_labels_cached = True
                self._rebuild_label_filter()
        except Exception:
            pass

    def _save_labels_cache(self) -> None:
        try:
            import json

            path = self._labels_cache_path()
            try:
                data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            except Exception:
                data = {}
            if not isinstance(data, dict):
                data = {}
            data[self._labels_cache_key()] = {
                "labels": self._curation_labels,
                "collection": (
                    getattr(self._config.dataverse, "collection", "")
                    or getattr(self._config.dataverse, "subtree", "")
                    or ""
                ),
            }
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

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
            if cached_labels and not self._curation_labels:
                self._curation_labels = list(cached_labels)
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
            self._apply_filter()
            try:
                self._shown_cache_key = self._dashboard_cache_key()
            except Exception:
                pass
            saved = (entry.get("saved_at") or "")[:16].replace("T", " ")
            self._subtitle.setText(
                f"{self._config.dataverse.base_url}  ·  "
                f"{(getattr(self._config.dataverse, 'collection', '') or getattr(self._config.dataverse, 'subtree', '') or '').strip() or 'whole repository'}"
            )
            self._progress.setText(
                f"Showing {len(self._all_datasets)} cached dataset(s)"
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
        clean = [str(l).strip() for l in (labels or []) if str(l).strip()]
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
        self._save_labels_cache()

    # -- header helpers --------------------------------------------------

    def _make_metric_card(self, accent: str, label: str, sub: str) -> QFrame:
        """Slim single-line metric: icon + label on the left, value on the right."""
        card = QFrame()
        card.setObjectName("MetricCard")
        card.setProperty("accent", accent)
        border_color = {"tertiary": TERTIARY, "primary": PRIMARY, "error": ERROR}[accent]
        card.setStyleSheet(
            f"QFrame#MetricCard {{ background: #ffffff; border: 1px solid {OUTLINE_VARIANT}; "
            "border-radius: 12px; }}"
        )
        card.setMinimumHeight(52)
        card.setToolTip(sub)
        lay = QHBoxLayout(card)
        lay.setContentsMargins(14, 8, 14, 8)
        lay.setSpacing(8)
        icon_map = {"tertiary": "◧", "primary": "◎", "error": "⚠"}
        icon = QLabel(icon_map.get(accent, "•"))
        icon.setStyleSheet(
            f"font-size: 16px; color: {border_color}; border: none; background: transparent;"
        )
        lay.addWidget(icon, 0)
        lbl = QLabel(f"{label.upper()}  ·  {sub}")
        lbl.setStyleSheet(
            "font-size: 11px; font-weight: 600; color: #424656; "
            "letter-spacing: 0.5px; border: none; background: transparent;"
        )
        lay.addWidget(lbl, 1)
        v = QLabel("0")
        v.setObjectName("metricValue")
        v.setStyleSheet(
            "font-size: 22px; font-weight: 700; color: #131b2e; "
            "border: none; background: transparent;"
        )
        v.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(v, 0)
        return card

    # -- column visibility -------------------------------------------------

    def _apply_default_column_visibility(self) -> None:
        for i, (_key, _h, visible) in enumerate(COLUMNS):
            self._table.setColumnHidden(i, not visible)

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
                lambda checked, i=idx: self._table.setColumnHidden(i, not checked)
            )
            menu.addAction(action)
        menu.exec(pos)

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
        alias = (
            getattr(self._config.dataverse, "collection", "")
            or getattr(self._config.dataverse, "subtree", "")
            or ""
        ).strip() or "whole repository"
        self._subtitle.setText(
            f"{self._config.dataverse.base_url}  ·  {alias}"
        )
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
        if had_rows:
            self._progress.setText(
                f"Checking for changes… (showing {len(self._all_datasets)} cached dataset(s))"
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
        self._worker.labelsDiscovered.connect(self._on_labels_discovered)
        self._worker.finished.connect(self._on_crawl_finished)
        self._worker.error.connect(self._on_crawl_error)
        self._worker.finished.connect(lambda: setattr(self, "_worker", None))
        self._worker.error.connect(lambda: setattr(self, "_worker", None))
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.error.connect(self._worker.deleteLater)
        self._worker.start()

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
            self._save_labels_cache()

    def _on_crawl_finished(self, datasets: list[dict]) -> None:
        try:
            self._worker = None
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
                        f"{total} dataset(s) shown — double-click a row to open"
                    )
                elif not (n_new or n_chg or n_del):
                    self._progress.setText(
                        f"No changes — {total} dataset(s) up to date. Double-click a row to open"
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
                        f"{', '.join(parts)} — {total} dataset(s) shown. Double-click a row to open"
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
                f"Failed to display datasets:\n{exc}\n\n{traceback.format_exc()}",
            )

    def _update_metrics(self) -> None:
        """All three cards from REAL data — never placeholders.

        - Pending Datasets: versionState DRAFT (plain drafts awaiting triage)
        - In Review: locked for review (confirmed via the locks endpoint)
        - Needs Action: drafts + in-review items with no logged decision yet
        """
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
        for card, val in zip(self._metric_cards, vals):
            v_lbl = card.findChild(QLabel, "metricValue")
            if v_lbl:
                v_lbl.setText(str(val))

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
        raw = ds.get(key, "")
        if key in ("file_count", "total_size_bytes"):
            if raw is None:
                # Unknown size (None from search) sorts below real sizes.
                return -1.0
            try:
                return float(raw or 0)
            except Exception:
                return 0.0
        if key in ("date_created", "date_published", "downloaded_at"):
            s = str(raw or "")
            if not s:
                return 0.0
            try:
                from datetime import datetime
                for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
                    try:
                        return datetime.strptime(s[:16], fmt).timestamp() if fmt == "%Y-%m-%d %H:%M" else datetime.strptime(s[:10], "%Y-%m-%d").timestamp()
                    except Exception:
                        continue
                return float(s[:4] or 0)
            except Exception:
                return s.lower()
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
                self._progress.setText(
                    f"{len(filtered)} / {len(self._all_datasets)} dataset(s) shown — "
                    "double-click a row to open"
                )

            self._table.setSortingEnabled(False)
            self._table.setRowCount(len(filtered))
            mono = QFont("JetBrains Mono")
            for row, ds in enumerate(filtered):
                for col, (key, _h, _v) in enumerate(COLUMNS):
                    text_val = self._cell_text(ds, key)
                    item = _SortItem(text_val)
                    item.setToolTip(text_val)
                    if key == "total_size_bytes":
                        if text_val == "—":
                            item.setToolTip("Size unknown — open the dataset to load its file inventory")
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
            self._table.viewport().update()
        except Exception as exc:
            import traceback
            self._refresh_btn.setEnabled(True)
            self._progress.setText("Error rendering results — details in dialog")
            from ui.dialogs import show_warning
            show_warning(
                self, "Dashboard",
                f"Failed to display datasets:\n{exc}\n\n{traceback.format_exc()}",
            )

    def _on_crawl_error(self, msg: str) -> None:
        from ui.dialogs import show_warning
        self._worker = None
        self._refresh_btn.setEnabled(True)
        self._progress.setText("Error — details in dialog (text is selectable/copyable)")
        show_warning(self, "Dataverse", f"Could not fetch datasets:\n{msg}")

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
