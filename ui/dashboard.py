"""Dashboard view: metrics + curation queue.

Table uses plain QTableWidgetItems only (no cell widgets) so text never
overlaps/garbles and Qt sorting moves whole rows. All columns are
user-resizable (Interactive) with the last visible column stretching to fill
leftover space, and toggleable via Columns… including the local Downloaded
date sourced from the workspace state.db + staged folders.
"""

from __future__ import annotations

import math
from datetime import UTC
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QBrush, QColor, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from curation.client import size_unavailable
from curation.config import Config
from curation.dashboard_cache import (
    dashboard_cache_key,
    diff_dashboard_datasets,
    load_dashboard_cache,
    save_dashboard_cache,
)
from curation.dashboard_cache import (
    merge_enriched_rows as _merge_enriched_rows,
)
from ui.i18n import t
from ui.table_layout import TableLayout
from ui.theme import (
    ACCENT_PRIMARY,
    ACCENT_TERTIARY,
    ACTIVE_THEME,
    BORDER_SUBTLE,
    STATE_ERROR_GRAPHIC,
    SURFACE_CARD,
    SURFACE_TINT,
    TEXT_MUTED,
    band_qss,
    page_background_qss,
    selectable_labels,
    surface_frame_qss,
    transparent_surface_qss,
)
from ui.widgets import (
    AppTable,
    ElidedLabel,
    RingProgress,
    flush_table_style,
    human_size,
    make_action_button,
    make_caption_label,
    make_card_title,
    make_combo,
    make_elided_label,
    make_refresh_button,
    make_search_field,
    make_small_body_label,
)
from ui.workers import BulkCheckWorker, CrawlWorker


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


class _ElidedBarLabel(ElidedLabel):
    """Elided label that notifies on setText.

    The crawl message can be a long sentence; it must not widen the
    status pill past the window, and it must not push the scope (which
    names the collection the curator is looking at) out of view.
    """

    changed = Signal(str)

    def setText(self, text: str) -> None:
        """Set the label text and notify watchers via :attr:`changed`."""
        super().setText(text)
        self.changed.emit(text)


# Full column model. `key` maps to dataset dict + enriched local dates.
# `default_visible=False` columns start hidden but can be enabled via Columns…
COLUMNS: list[tuple[str, str, bool]] = [
    ("title", t("dashboard.columns.title"), True),
    ("persistent_id", t("dashboard.columns.persistent_id"), False),
    ("contact", t("dashboard.columns.contact"), True),
    ("depositor", t("dashboard.columns.depositor"), False),
    ("date_created", t("dashboard.columns.date_created"), True),
    ("date_published", t("dashboard.columns.date_published"), False),
    ("collection", t("dashboard.columns.collection"), False),
    ("file_count", t("dashboard.columns.file_count"), True),
    ("total_size_bytes", t("dashboard.columns.total_size_bytes"), True),
    ("state", t("dashboard.columns.state"), True),
    ("access", t("dashboard.columns.access"), True),
    ("curation_label", t("dashboard.columns.curation_label"), True),
    ("follow_up", t("dashboard.columns.follow_up"), True),
    ("downloaded_at", t("dashboard.columns.downloaded_at"), True),
]

# Sentinel stored as the combo's *data* for the "No label" row. The wording
# the user reads comes from the catalogue (``dashboard.filters.label_none``);
# this token only identifies the row internally, so a curation label that
# happens to be called "No label" cannot collide with it.
_NO_LABEL_SENTINEL = "__no_label__"

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
    "access": 130,
    "curation_label": 150,
    "follow_up": 170,
    "downloaded_at": 130,
}

# What the account could read for one dataset, in the queue's Access column.
# The machine codes come from dataverse_client (the refusal classifier);
# the wording comes from the catalogue. A row that was read fine shows
# nothing — the column speaks only when there is something to say.
_ACCESS_LABEL_KEYS = {
    "draft_not_readable": "dashboard.access.draft_not_readable",
    "versions_not_readable": "dashboard.access.not_readable",
    "version_not_readable": "dashboard.access.not_readable",
    "not_readable": "dashboard.access.not_readable",
    "no_published_version": "dashboard.access.no_published_version",
    "no_readable_version": "dashboard.access.no_readable_version",
    "no_draft_version": "dashboard.access.no_readable_version",
    "no_versions_to_compare": "dashboard.access.no_readable_version",
    "not_under_curation": "dashboard.access.not_under_curation",
}

_ACCESS_TIP_KEYS = {
    "draft_not_readable": "dashboard.access.tip_draft_not_readable",
    "versions_not_readable": "dashboard.access.tip_not_readable",
    "version_not_readable": "dashboard.access.tip_not_readable",
    "not_readable": "dashboard.access.tip_not_readable",
    "no_published_version": "dashboard.access.tip_no_published_version",
    "no_readable_version": "dashboard.access.tip_no_readable_version",
    "no_draft_version": "dashboard.access.tip_no_readable_version",
    "no_versions_to_compare": "dashboard.access.tip_no_readable_version",
    "not_under_curation": "dashboard.access.tip_not_under_curation",
}


def _access_facts(ds: dict[str, Any]) -> tuple[str, str]:
    """(reason code, server detail) for what this account could read.

    Empty when everything about the dataset could be read - the Access
    column only speaks when the server refused something.
    """
    try:
        access = ds.get("access")
        if isinstance(access, dict):
            state = str(access.get("state") or "")
            if state and state != "readable":
                return (
                    str(access.get("reason") or "not_readable"),
                    str(access.get("detail") or ""),
                )
        curation = ds.get("curation_access")
        if isinstance(curation, dict) and str(curation.get("state") or "") == "unreadable":
            return (
                str(curation.get("reason") or "not_under_curation"),
                str(curation.get("detail") or ""),
            )
    except Exception:
        pass
    return "", ""


def _access_text(ds: dict[str, Any]) -> str:
    """Return the Access cell: a short label, empty when there is nothing to say."""
    reason, _detail = _access_facts(ds)
    if not reason:
        return ""
    key = _ACCESS_LABEL_KEYS.get(reason)
    return t(key) if key else t("dashboard.access.not_readable")


def _access_tooltip(ds: dict[str, Any]) -> str:
    """Why the account could not read everything (empty when it could)."""
    reason, detail = _access_facts(ds)
    if not reason:
        return ""
    key = _ACCESS_TIP_KEYS.get(reason)
    text = t(key) if key else t("dashboard.access.tip_not_readable")
    if detail:
        text = f"{text}\n{t('dashboard.access.server_said', detail=detail)}"
    return text


# Metric-card value: the real count (DisplayLG, 22px bold) versus a named
# pre-crawl state (StateMD, 12px muted words, 2026-10-02 P2) - the number
# slot never shows a bare "-", so a visible "0" can only mean a completed
# check counted zero. Both are theme tokens, not inline styles.
_METRIC_VALUE_TOKEN = "DisplayLG"
_METRIC_STATE_TOKEN = "StateMD"


def _apply_metric_token(label: QLabel) -> None:
    """Put a metric label on its theme token (DisplayLG / StateMD).

    The metric card swaps between the value and the named state, so the
    token changes at runtime: the object name carries the token, and the
    widget is re-polished so the theme's rule for the new token applies.
    """
    token = str(label.property("metricToken") or _METRIC_VALUE_TOKEN)
    if label.objectName() == token:
        return
    label.setObjectName(token)
    style = label.style()
    if style is not None:
        style.unpolish(label)
        style.polish(label)


def _system_datetime_text(mtime: float) -> str:
    """Local timestamp in the user's system date/time format (dv-bqk)."""
    from PySide6.QtCore import QDateTime, QLocale

    qdt = QDateTime.fromMSecsSinceEpoch(math.floor(mtime * 1000))
    return QLocale.system().toString(qdt, QLocale.FormatType.ShortFormat)


# One decimal (KB/MB) formatter in ui.widgets; keep the local name as a
# direct alias so every call site shares the same function object.
_human_size = human_size


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
        from datetime import datetime

        # ISO-8601 first (handles TZ suffixes the old loop ignored).
        try:
            iso = text.replace("Z", "+00:00") if text.endswith("Z") else text
            dt = datetime.fromisoformat(iso)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt.timestamp()
        except ValueError:
            pass
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(text[: len(fmt)], fmt)
                return dt.replace(tzinfo=UTC).timestamp()
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
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='curation_actions'"
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

        for pid in pids:
            if out[pid] or not pid:
                continue
            staged = ws / "downloads" / _sanitize(pid) / "files"
            try:
                if staged.exists():
                    out[pid] = _system_datetime_text(staged.stat().st_mtime)
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


def local_follow_ups(workspace: Path) -> dict[str, dict[str, Any]]:
    """{persistent_id: follow-up} for every open depositor follow-up (dv-5eg).

    One sqlite connect for the whole queue; never raises.
    """
    try:
        from curation.storage import open_state

        if not (Path(workspace) / "state.db").exists():
            return {}
        st = open_state(Path(workspace))
        try:
            return st.list_follow_ups()
        finally:
            st.close()
    except Exception:
        return {}


def attach_follow_ups(
    datasets: list[dict[str, Any]], follow_ups: dict[str, dict[str, Any]] | None
) -> None:
    """Stamp each dataset with its follow-up state for the queue column.

    The state is recomputed against the row's ``draft_updated_at`` (the
    server draft lastUpdateTime enrichment attached), so a newer draft flips
    an awaiting follow-up to "depositor updated" without another store read.
    """
    if not follow_ups:
        for ds in datasets or []:
            try:
                ds.pop("follow_up", None)
            except Exception:
                continue
        return
    try:
        import curation.follow_ups as _fu
    except Exception:  # pragma: no cover - module is part of the app
        _fu = None  # type: ignore[assignment]
    for ds in datasets or []:
        try:
            pid = str(ds.get("persistent_id") or "")
            row = follow_ups.get(pid)
            if not row:
                ds.pop("follow_up", None)
                continue
            state = str(row.get("state") or "")
            if _fu is not None:
                state = _fu.state_for(row.get("opened_at"), ds.get("draft_updated_at"))
            ds["follow_up"] = {
                "opened_at": str(row.get("opened_at") or ""),
                "decision_label": str(row.get("decision_label") or ""),
                "state": state,
            }
        except Exception:
            continue


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
                "SELECT name FROM sqlite_master WHERE type='table' AND name='curation_actions'"
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
    def __lt__(self, other: QTableWidgetItem) -> bool:
        a = self.data(Qt.ItemDataRole.UserRole)
        b = other.data(Qt.ItemDataRole.UserRole) if isinstance(other, QTableWidgetItem) else None
        # Numeric/date sort when both sides carry a float epoch or number
        if isinstance(a, float) and isinstance(b, float):
            return a < b
        return self.text() < other.text()


def _display_state(state: str) -> str:
    s = (state or "").upper()
    if "REVIEW" in s:
        return t("dashboard.display_state.review")
    if s == "DRAFT":
        return t("dashboard.display_state.draft")
    if s in ("RELEASED", "PUBLISHED"):
        return t("dashboard.display_state.published")
    if s == "DEACCESSIONED":
        return t("dashboard.display_state.deaccessioned")
    if not s:
        return t("dashboard.display_state.unknown")
    return s.title()


# The dashboard cache helpers (slot keys, row fingerprints, diffing,
# enrichment merge, load/save) live in the Qt-free root module
# dashboard_cache.py: the engine tests exercise them without importing the
# view layer (dv-hcg.26). They are imported at the top of this file.


class DashboardView(QWidget):
    """Lists datasets. Emits openRequested(pid, title, row) on double-click."""

    # The third argument is the queue row (a dict) — what the search
    # payload already knows about the dataset travels with the request.
    openRequested = Signal(str, str, object)
    # Empty-state CTA: "Open Settings" reaches the main window's pane switch.
    settingsRequested = Signal()

    # Painting window (W-11): the QTableWidget allocates one item per
    # cell, so painting 25k rows × 12 columns on every keystroke is
    # unusable. Filtering/sorting still cover the full set; only the
    # painted rows are capped, and the status line says how many are
    # hidden so the cap is never silent.
    #
    # Measured, not guessed (dv-fjr; tools/perf/bench_paint_window.py, 25k
    # synthetic rows, Windows offscreen, median of 5 runs): filtering all
    # 25k rows costs ~13 ms, painting costs ~0.45 ms per row, so a full
    # repaint is ~0.9 s at 2,000 painted rows, ~2.0 s at 5,000, ~4.0 s
    # at 10,000 and ~7.6 s uncapped. 2,000 is the highest cap whose
    # repaint stays inside a second, so the cap is confirmed, not raised.
    _MAX_PAINTED_ROWS = 2000

    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config
        self._worker: CrawlWorker | None = None
        self._all_datasets: list[dict[str, Any]] = []
        self._datasets: list[dict[str, Any]] = []
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
        # Bulk "Run checks for visible rows" (dv-9m2): at most the painting
        # window is enqueued, never the full crawl. The worker is a
        # sequential file-checks pass; a second trigger while it runs asks
        # to cancel instead of starting an overlapping batch.
        self._bulk_worker: BulkCheckWorker | None = None
        self._bulk_enqueued: list[tuple[str, str]] = []
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
        self.setStyleSheet(page_background_qss("DashboardView", theme=ACTIVE_THEME))

        # ---- Metrics cards (values always from real data; 0 when empty) ----
        self._metrics_row = QHBoxLayout()
        self._metrics_row.setSpacing(16)
        self._metric_cards: list[QFrame] = []
        self._metric_value_labels: list[QLabel] = []
        self._labelled_only: bool = False
        for accent, label, sub_text in [
            (
                "tertiary",
                t("dashboard.metrics.pending.label"),
                t("dashboard.metrics.pending.sub"),
            ),
            (
                "primary",
                t("dashboard.metrics.review.label"),
                t("dashboard.metrics.review.sub"),
            ),
            (
                "progress",
                t("dashboard.metrics.action.label"),
                t("dashboard.metrics.action.sub"),
            ),
        ]:
            card, value_label = self._make_metric_card(accent, label, sub_text)
            self._metrics_row.addWidget(card, 1)
            self._metric_cards.append(card)
            self._metric_value_labels.append(value_label)
        outer.addLayout(self._metrics_row)

        # ---- Curation Queue card ----
        queue_card = QFrame()
        queue_card.setObjectName("Card")
        queue_card.setStyleSheet(
            surface_frame_qss(
                SURFACE_CARD, BORDER_SUBTLE, selector="QFrame#Card", theme=ACTIVE_THEME
            )
        )
        queue_layout = QVBoxLayout(queue_card)
        queue_layout.setContentsMargins(0, 0, 0, 0)
        queue_layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("QueueHeaderBar")
        header.setStyleSheet(
            band_qss(
                SURFACE_TINT, BORDER_SUBTLE, selector="QFrame#QueueHeaderBar", theme=ACTIVE_THEME
            )
        )
        # The queue header follows the card contract: the title row carries
        # the title (and only the title - no tools), and every tool lives
        # on the row below. The tools row fits at the 960px floor because
        # the search field and the combos shrink to their minimum widths
        # (the combo labels elide; their full text stays in the menu).
        hdr_layout = QVBoxLayout(header)
        hdr_layout.setContentsMargins(16, 12, 16, 12)
        hdr_layout.setSpacing(10)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(12)
        hdr_title = make_elided_label(t("dashboard.queue.title"), object_name="HeadlineMD")
        title_row.addWidget(hdr_title, 1)
        hdr_layout.addLayout(title_row)

        filter_row = QHBoxLayout()
        filter_row.setContentsMargins(0, 0, 0, 0)
        filter_row.setSpacing(8)

        # No visible label: the field's placeholder and accessible name
        # carry the label (the visible one duplicated the placeholder and
        # pushed the tools row past the window).
        self._filter_edit = make_search_field(t("dashboard.queue.search"), min_width=140)
        self._filter_edit.setAccessibleName(t("dashboard.queue.search"))
        self._filter_edit.textChanged.connect(lambda _t: self._filter_timer.start())
        filter_row.addWidget(self._filter_edit, 1)

        self._state_filter = make_combo(
            [
                (t("dashboard.filters.all"), "All"),
                (t("dashboard.filters.pending"), "PENDING"),
                (t("dashboard.filters.draft"), "DRAFT"),
                (t("dashboard.filters.published"), "PUBLISHED"),
                (t("dashboard.filters.in_review"), "IN REVIEW"),
                (t("dashboard.filters.deaccessioned"), "DEACCESSIONED"),
            ],
            min_width=110,
        )
        self._state_filter.currentTextChanged.connect(self._on_state_filter_changed)
        filter_row.addWidget(self._state_filter)

        self._label_filter = make_combo(
            [
                (t("dashboard.filters.label_all"), ""),
                (t("dashboard.filters.label_none"), _NO_LABEL_SENTINEL),
            ],
            min_width=130,
            tip=t("dashboard.filters.label_tip"),
        )
        self._label_filter.currentTextChanged.connect(self._apply_filter)
        filter_row.addWidget(self._label_filter)

        self._collection_filter = make_combo(
            [(t("dashboard.filters.collection_all"), "")],
            min_width=130,
            tip=t("dashboard.filters.collection_tip"),
        )
        self._collection_filter.currentTextChanged.connect(self._apply_filter)
        filter_row.addWidget(self._collection_filter)

        self._columns_btn = make_action_button(t("dashboard.queue.columns"), kind="chip")
        self._columns_btn.clicked.connect(self._show_columns_menu)
        filter_row.addWidget(self._columns_btn)

        refresh = make_refresh_button(t("common.refresh"))
        refresh.clicked.connect(self.reload)
        self._refresh_btn = refresh
        filter_row.addWidget(refresh)

        self._filter_wrap = QWidget()
        self._filter_wrap.setObjectName("QueueFilterWrap")
        self._filter_wrap.setStyleSheet(
            transparent_surface_qss("QueueFilterWrap", theme=ACTIVE_THEME)
        )
        self._filter_wrap.setLayout(filter_row)
        hdr_layout.addWidget(self._filter_wrap)

        queue_layout.addWidget(header)

        # Queue table — standard behaviors (movable/resizable/sortable/copy).
        self._table = AppTable(
            [h for _k, h, _v in COLUMNS],
            widths={i: _COLUMN_WIDTHS.get(key, 120) for i, (key, _h, _v) in enumerate(COLUMNS)},
            row_height=40,
            # No stretch-last: the queue has no horizontal scrollbar, so
            # the columns are fitted to the viewport by hand and the last
            # visible column absorbs the slack (see _fit_queue_columns).
            # Qt's own stretch only re-applies when the header itself is
            # resized, and this header is hidden — after a drag the
            # columns overflowed the viewport and the right-hand labels
            # were cut off.
            stretch_last=False,
        )
        # No horizontal scrollbar on the dashboard: the queue reads at
        # window width (the filler column absorbs any slack).
        self._table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Flush under the banner header (last child: square top meets the
        # banner, 8px bottom meets the card border — see flush_table_style).
        self._table.setStyleSheet(flush_table_style())
        self._table.cellDoubleClicked.connect(self._on_double_click)
        # Keyboard parity for the queue: Enter/Return opens the focused row
        # (double-click alone locks out keyboard-only users), F5 refreshes,
        # Escape clears the search. See _on_table_key.
        self._table.installEventFilter(self)
        # Right-click on the queue: "Run checks for visible rows" capped at
        # the painting window (dv-9m2).
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_queue_context_menu)
        # The viewport is watched too: its width changes when the vertical
        # scrollbar appears (the columns must keep filling it).
        try:
            self._table.viewport().installEventFilter(self)
        except Exception:
            pass
        # Native header: keyboard focus + sort on Space/Return
        native_hdr = self._table.horizontalHeader()
        native_hdr.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        native_hdr.setSectionsClickable(True)
        # Ensure the sort indicator is shown at startup
        native_hdr.setSortIndicatorShown(True)
        self._table.setSortingEnabled(True)
        # Column bar: the table's own header is the column bar (native
        # mode, dv-5oh). Widths the fit scaled down are kept so a wider
        # window restores them.
        self._queue_unscaled: dict[int, int] | None = None
        self._table.horizontalHeader().setVisible(True)
        self._table.user_layout_changed.connect(self._on_user_layout_changed)
        self._table.columns_fitted.connect(self._on_columns_fitted)
        # Table + first-run overlay occupy the same grid cell so the card
        # floats over the (empty) table without any layout surgery when
        # datasets arrive.
        queue_stack = QWidget()
        queue_stack.setObjectName("QueueStack")
        queue_stack.setStyleSheet(transparent_surface_qss("QueueStack", theme=ACTIVE_THEME))
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
            surface_frame_qss(
                SURFACE_CARD, BORDER_SUBTLE, selector="QFrame#StatusPill", theme=ACTIVE_THEME
            )
        )
        pill_lay = QHBoxLayout(pill)
        pill_lay.setContentsMargins(14, 6, 14, 6)
        pill_lay.setSpacing(8)
        self._status_lbl = _BarLabel("")
        self._status_lbl.setObjectName("ValueMD")
        pill_lay.addWidget(self._status_lbl)
        pill_lay.setAlignment(self._status_lbl, Qt.AlignmentFlag.AlignVCenter)
        self._status_sep = make_caption_label("·")
        self._status_sep.hide()
        pill_lay.addWidget(self._status_sep)
        pill_lay.setAlignment(self._status_sep, Qt.AlignmentFlag.AlignVCenter)
        self._progress = _ElidedBarLabel("")
        self._progress.setObjectName("CaptionSM")
        # Circular progress ring, alongside the status text (the text
        # stays the accessible source of truth; the ring shows pace).
        self._ring = RingProgress(diameter=28)
        self._ring.hide()
        pill_lay.addWidget(self._ring)
        pill_lay.setAlignment(self._ring, Qt.AlignmentFlag.AlignVCenter)
        pill_lay.addWidget(self._progress, 1)
        pill_lay.setAlignment(self._progress, Qt.AlignmentFlag.AlignVCenter)

        def _sync_sep() -> None:
            # The dot joins scope and message only when both sides exist;
            # the tooltip carries the full message when it clips.
            # fullText(), not text(): the message is elided, so its
            # visible text can be empty on a zero-width label.
            msg = self._progress.fullText()
            self._status_sep.setVisible(bool(self._status_lbl.text()) and bool(msg))
            # An empty message takes no room: the scope then owns the
            # pill instead of sharing it with a blank half.
            self._progress.setVisible(bool(msg))
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

            _pix = _QPixmap(mark_icon_path(ACTIVE_THEME))
            if not _pix.isNull():
                # Native 16x16 — never upscale the pixel mark.
                mark.setPixmap(_pix.scaledToHeight(16, Qt.TransformationMode.SmoothTransformation))
                mark.setToolTip(t("app.name"))
        except Exception:
            pass
        mark.setStyleSheet(transparent_surface_qss("DocentMark", theme=ACTIVE_THEME))
        foot.addWidget(mark, 0, Qt.AlignmentFlag.AlignVCenter)

        outer.addLayout(foot)
        _sync_sep()
        self._sync_status_bar()

        self._apply_default_column_visibility()
        # Snapshot the construction view for the Columns-menu reset, then
        # restore the user's saved queue view (widths/sort/hidden/order)
        # after defaults and mirror it onto the display header.
        try:
            self._queue_layout = TableLayout(
                self._config.app.workspace,
                "dashboard_queue",
                self._table.horizontalHeader(),
                view=self._table,
            )
            if self._queue_layout.restore():
                self._table.disable_auto_fit()
        except Exception:
            pass
        selectable_labels(self)
        # Cache-first paint happens *after* the shell is visible (see
        # start_background_load): applying cached rows, local state and the
        # first crawl must never delay the window. Only the cache file is
        # read here — a small JSON parse that lets the first frame show an
        # honest "restoring" state instead of a misleading empty queue.
        self._shown_cache_key = ""
        self._cache_loaded = False
        self._startup_started = False
        self._startup_cache_entry = self._read_dashboard_cache()
        self._restoring = bool(self._startup_cache_entry)
        # First paint: named pre-crawl metric states + first-run card until
        # a crawl lands.
        self._update_metrics()

        has_token = bool((self._config.dataverse.api_token or "").strip())
        if not has_token and not self._restoring:
            self._progress.setText(t("dashboard.progress.api_key"))
        elif has_token:
            self._progress.setText(
                t("dashboard.progress.restoring")
                if self._restoring
                else t("dashboard.progress.contacting")
            )

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
                lbl.setText(
                    t(
                        "dashboard.status.scope",
                        scope=scope,
                        shown=len(shown_ds),
                        total=total,
                    )
                )
                lbl.setToolTip(
                    t(
                        "dashboard.status.scope_tip",
                        base=base,
                        collection=alias or t("dashboard.status.whole_repository"),
                    )
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
            from curation.client import read_allowed_labels_cache

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

    def start_background_load(self) -> None:
        """Paint the cached queue, then start the first crawl.

        Called by MainWindow once the window has painted its first frame
        (main.py). Applying the cache, reading state.db/staged folders and
        contacting the server all happen here instead of in __init__, so
        startup latency does not depend on cache size. Idempotent.
        """
        if self._startup_started:
            return
        self._startup_started = True
        self._restoring = False
        try:
            from curation.startup_probe import mark
        except Exception:  # pragma: no cover - probe is optional

            def mark(label: str) -> None:
                """No-op fallback when the startup probe is unavailable."""

        mark("dashboard: background load start")
        # Labels seed from disk before the cached rows (it imports the
        # Dataverse client, so it must not sit on the window-construction
        # path). The rows then merge their own labels from the cache.
        self._load_labels_cache()
        self._cache_loaded = self._show_cached_dashboard()
        self._update_metrics()
        has_token = bool((self._config.dataverse.api_token or "").strip())
        if not has_token:
            if self._cache_loaded:
                self._progress.setText(
                    self._progress.text() + t("dashboard.progress.api_key_suffix")
                )
            else:
                self._progress.setText(t("dashboard.progress.api_key"))
            mark("dashboard: ready (no token)")
            return
        self.reload()
        mark("dashboard: crawl started")

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

    def _read_dashboard_cache(self) -> dict[str, Any] | None:
        """Read this instance+collection's cached crawl (JSON only, no paint)."""
        try:
            ws = Path(getattr(getattr(self._config, "app", None), "workspace", Path.home()))
            return load_dashboard_cache(ws, self._dashboard_cache_key())
        except Exception:
            return None

    def _show_cached_dashboard(self) -> bool:
        """Paint the last crawl instantly (no network). True when shown."""
        try:
            ws = Path(getattr(getattr(self._config, "app", None), "workspace", Path.home()))
            # Prefetched in __init__ (so the first frame could say
            # "restoring"); fall back to a fresh read when called directly.
            entry = getattr(self, "_startup_cache_entry", None)
            self._startup_cache_entry = None
            if entry is None:
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
                attach_follow_ups(self._all_datasets, local_follow_ups(Path(ws)))
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
            self._sync_status_bar()
            self._progress.setText(
                t(
                    "dashboard.progress.cached",
                    count=len(self._all_datasets),
                    from_=t("dashboard.progress.cached_from", when=saved) if saved else "",
                )
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
            self._collection_filter.addItem(t("dashboard.filters.collection_all"), "")
            for coll in sorted(
                {str(ds.get("collection") or "") for ds in self._all_datasets} - {""}
            ):
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
            self._label_filter.addItem(t("dashboard.filters.label_all"), "")
            for label in self._curation_labels:
                self._label_filter.addItem(label, label)
            self._label_filter.addItem(t("dashboard.filters.label_none"), _NO_LABEL_SENTINEL)
            idx = self._label_filter.findData(current)
            self._label_filter.setCurrentIndex(idx if idx >= 0 else 0)
        finally:
            try:
                self._label_filter.blockSignals(False)
            except Exception:
                pass

    def _on_labels_discovered(self, labels: list[Any]) -> None:
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
            from curation.applog import get_app_log

            get_app_log().info(
                t(
                    "dashboard.log.label_filter_options",
                    labels=(
                        ", ".join(f"'{lbl}'" for lbl in seen)
                        if seen
                        else t("common.none_in_parentheses")
                    ),
                )
            )
        except Exception:
            pass

    def _on_allowed_probed(self, payload: dict[str, Any]) -> None:
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
            from curation.client import write_allowed_labels_cache

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
        wrap.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(24, 32, 24, 32)
        lay.setSpacing(0)

        card = QFrame()
        card.setObjectName("EmptyStateCard")
        card.setStyleSheet(
            surface_frame_qss(
                SURFACE_CARD,
                BORDER_SUBTLE,
                selector="QFrame#EmptyStateCard",
                theme=ACTIVE_THEME,
                border_style="dashed",
            )
        )
        inner = QVBoxLayout(card)
        inner.setContentsMargins(32, 32, 32, 28)
        inner.setSpacing(8)

        icon = _empty_icon("database", size=28, color=ACCENT_PRIMARY)
        head_wrap = QHBoxLayout()
        head_wrap.setSpacing(10)
        head_wrap.addWidget(icon, 0, Qt.AlignmentFlag.AlignVCenter)
        self._empty_head = make_card_title(t("dashboard.empty.none_loaded"))
        head_wrap.addWidget(self._empty_head, 1, Qt.AlignmentFlag.AlignVCenter)
        inner.addLayout(head_wrap)

        self._empty_body = make_small_body_label(t("dashboard.empty.none_loaded_body"))
        inner.addWidget(self._empty_body)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch(1)
        settings_btn = make_action_button(
            t("dashboard.empty.open_settings"), kind="primary", size="md"
        )
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
        restoring = bool(getattr(self, "_restoring", False))
        show = not self._all_datasets and not loading
        try:
            if show:
                if restoring:
                    self._empty_head.setText(t("dashboard.empty.restoring"))
                    self._empty_body.setText(t("dashboard.empty.restoring_body"))
                elif has_token:
                    self._empty_head.setText(t("dashboard.empty.no_collection"))
                    self._empty_body.setText(t("dashboard.empty.no_collection_body"))
                else:
                    self._empty_head.setText(t("dashboard.empty.none_loaded"))
                    self._empty_body.setText(t("dashboard.empty.none_loaded_body"))
            self._empty_overlay.setVisible(show)
        except Exception:
            pass

    def _make_metric_card(self, accent: str, label: str, sub: str) -> tuple[QFrame, QLabel]:
        """Slim single-line metric: icon + label on the left, value on the right."""
        card = QFrame()
        card.setObjectName("MetricCard")
        card.setProperty("accent", accent)
        border_color = {
            "tertiary": ACCENT_TERTIARY,
            "primary": ACCENT_PRIMARY,
            "progress": ACCENT_TERTIARY,
            "error": STATE_ERROR_GRAPHIC,
        }[accent]
        # No widget-level sheet: the global #MetricCard rule in theme.py paints
        # it. A local stylesheet would shadow the app sheet for the subtree
        # (dv-g98).
        card.setMinimumHeight(52)
        # No tooltip (dv-1k4): the card is a filter control, not a mystery
        # to explain. Hover feedback carries the affordance instead.
        lay = QHBoxLayout(card)
        lay.setContentsMargins(14, 8, 14, 8)
        lay.setSpacing(8)
        from ui.icons import icon_label as _metric_icon

        icon_map = {
            "tertiary": "clock",
            "primary": "eye",
            "progress": "pencil",
            "error": "octagon-alert",
        }
        icon = _metric_icon(icon_map.get(accent, "circle"), size=18, color=border_color)
        # The whole chip must be the click target: mouse-transparent
        # children let press/enter/leave reach the card's eventFilter.
        icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        lay.addWidget(icon, 0)
        # The caption is the widest thing in the card ("PENDING · Datasets
        # waiting for a decision"), so it elides instead of pushing the
        # three cards past the window. The card tooltip keeps the full
        # caption.
        lbl = make_elided_label(
            t("dashboard.metrics.card_label", label=label.upper(), sub=sub),
            object_name="LabelMD",
        )
        lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        lay.addWidget(lbl, 1)
        v = QLabel("0")
        v.setProperty("metricToken", _METRIC_VALUE_TOKEN)
        _apply_metric_token(v)
        v.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        v.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        lay.addWidget(v, 0)
        # Tappable filter (dv-896): click or Enter/Space applies the card's
        # filter via eventFilter. Cursor + focus make it discoverable.
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        card.installEventFilter(self)
        return card, v

    def _on_metric_clicked(self, accent: str) -> None:
        """Apply a metric card's filter (dv-896, dv-is4)."""
        if accent == "primary":
            self._labelled_only = False
            self._state_filter.setCurrentIndex(4)
        elif accent == "progress":
            # In Progress card: rows carrying any curation label, any state.
            self._labelled_only = True
            self._state_filter.setCurrentIndex(0)
        else:
            self._labelled_only = False
            self._state_filter.setCurrentIndex(1)
        self._apply_filter()

    def _on_state_filter_changed(self) -> None:
        if getattr(self, "_labelled_only", False):
            # User changed the combo themselves: clear the In Progress flag.
            try:
                idx = self._state_filter.currentIndex()
            except Exception:
                idx = -1
            if idx != 0:
                self._labelled_only = False
        self._apply_filter()

    def _on_columns_fitted(self) -> None:
        """Content fit changed the column widths: re-fit them.

        The fit sizes the columns to their content; the slack that is left
        over goes to the filler column so the queue still reads at window
        width.
        """
        self._fit_queue_columns()

    def _schedule_column_fit(self) -> None:
        """Re-fit the queue columns once the layout has settled.

        A window resize delivers the viewport a burst of intermediate
        widths. Fitting on each of them would scale the columns down for
        a width the user never saw, so the fit waits for the last one.
        """
        try:
            QTimer.singleShot(0, self._fit_queue_columns)
        except Exception:
            pass

    def _fit_queue_columns(self) -> None:  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
        """Make the visible queue columns fill the viewport exactly.

        The queue has no horizontal scrollbar, so the columns must add up
        to the viewport width: the last visible column is the filler and
        absorbs the slack (or gives it back). Qt's stretchLastSection
        cannot do this here — it only re-applies when the header itself
        is resized, and the queue's header is hidden — so after a drag
        the columns overflowed the viewport and the right-hand labels
        were cut off.

        When the filler is at its floor and the columns still do not fit
        (a narrow window), the other columns are scaled down by one ratio
        — the content fit's rule. The pre-scale widths are remembered,
        so widening the window restores them instead of leaving the queue
        stuck at the narrow layout.

        Signals are blocked: this is bookkeeping, not a user drag, so it
        must not lock the content auto-fit.
        """
        try:
            hdr = self._table.horizontalHeader()
            width = self._table.viewport().width()
            if width <= 0:
                return
            # Before the first paint the viewport carries a placeholder
            # width; fitting to it would bake a wrong layout into the
            # columns. The viewport resize that follows the show does the
            # real fit.
            if not self._table.isVisible():
                return
            visible = [i for i in range(hdr.count()) if not hdr.isSectionHidden(i)]
            if not visible:
                return
            floor = hdr.minimumSectionSize()
            filler = visible[-1]
            others = visible[:-1]
            want = {i: hdr.sectionSize(i) for i in visible}
            # A previous downscale is undone as soon as there is room for
            # the original widths again.
            restore = getattr(self, "_queue_unscaled", None)
            if restore:
                for i, w in restore.items():
                    if i in want:
                        want[i] = w
                if width - sum(want[i] for i in others) >= floor:
                    self._queue_unscaled = None
                else:
                    want = {i: hdr.sectionSize(i) for i in visible}
            other_total = sum(want[i] for i in others)
            target_filler = width - other_total
            if target_filler >= floor:
                # The filler absorbs the difference (the common case).
                want[filler] = target_filler
            else:
                # The filler is at its floor: scale the other columns down
                # by one ratio so nothing is cut off.
                room = max(0, width - floor)
                if other_total > room > 0:
                    ratio = room / other_total
                    if not getattr(self, "_queue_unscaled", None):
                        self._queue_unscaled = {i: hdr.sectionSize(i) for i in others}
                    for i in others:
                        want[i] = max(floor, round(want[i] * ratio))
                    want[filler] = max(floor, width - sum(want[i] for i in others))
                else:
                    want[filler] = max(floor, target_filler)
            # Rounding the scaled widths can leave the columns a pixel or
            # two too wide (each width was rounded and floored on its
            # own). Shave the difference off the widest sections so the
            # total matches the viewport exactly -- one pixel over is
            # still a clipped column.
            overflow = sum(want[i] for i in visible) - width
            if overflow > 0:
                for i in sorted(visible, key=lambda j: -want[j]):
                    if overflow <= 0:
                        break
                    take = min(overflow, max(0, want[i] - floor))
                    want[i] -= take
                    overflow -= take
            changed = {i: w for i, w in want.items() if w != hdr.sectionSize(i)}
            if not changed:
                return
            hdr.blockSignals(True)
            try:
                for i, w in changed.items():
                    hdr.resizeSection(i, w)
            finally:
                hdr.blockSignals(False)
        except Exception:
            pass

    def _save_queue_layout(self) -> None:
        """Persist the queue table's view (widths/sort/hidden/order).

        The layout controller owns the persistence: it saves user
        gestures (a dragged edge, a moved column, a re-sort) and ignores
        the app's own refits.
        """
        layout = getattr(self, "_queue_layout", None)
        if layout is None:
            return
        layout.save()

    def _on_user_layout_changed(self) -> None:
        """Keep the queue filling its viewport after a user layout change.

        The user resized or moved a column. The fit is deferred:
        sectionResized can fire before Qt applied the new size, and the
        fit must see the settled widths.
        """
        self._queue_unscaled = None
        self._schedule_column_fit()

    def _sort_by_column(self, logical: int) -> None:
        """Sort the table by a column (toggle on repeat), like a header click."""
        table_hdr = self._table.horizontalHeader()
        if table_hdr.sortIndicatorSection() == logical and table_hdr.isSortIndicatorShown():
            order = (
                Qt.SortOrder.DescendingOrder
                if table_hdr.sortIndicatorOrder() == Qt.SortOrder.AscendingOrder
                else Qt.SortOrder.AscendingOrder
            )
        else:
            order = Qt.SortOrder.AscendingOrder
        self._table.sortItems(logical, order)
        table_hdr.setSortIndicator(logical, order)
        table_hdr.setSortIndicatorShown(True)
        self._save_queue_layout()

    def _set_column_visible(self, idx: int, visible: bool) -> None:
        """Hide/show a column.

        No save here on purpose: __init__ calls this for defaults, and a
        save during defaults would clobber the persisted view before
        restore_table_state reads it. The Columns… menu (the only user
        surface) saves after toggling.
        """
        self._table.setColumnHidden(idx, not visible)
        # Hiding/showing a column changes the total width: re-fit so the
        # remaining columns keep filling the viewport.
        self._fit_queue_columns()

    def _apply_default_column_visibility(self) -> None:
        for i, (_key, _h, visible) in enumerate(COLUMNS):
            self._set_column_visible(i, visible)

    def _show_columns_menu(self) -> None:
        self._show_columns_menu_at(
            self._columns_btn.mapToGlobal(self._columns_btn.rect().bottomLeft())
        )

    def _show_columns_menu_at(self, pos: QPoint) -> None:
        menu = QMenu(self)
        for idx, (_key, header, _v) in enumerate(COLUMNS):
            action = QAction(header, menu)
            action.setCheckable(True)
            action.setChecked(not self._table.isColumnHidden(idx))

            def _apply(checked: bool, i: int = idx) -> None:
                self._set_column_visible(i, checked)
                # The user changed the column set: the fit starts over
                # from the widths as they are now.
                self._queue_unscaled = None
                self._save_queue_layout()

            action.toggled.connect(_apply)
            menu.addAction(action)
        menu.addSeparator()
        try:
            from ui.icons import icon as _menu_icon

            reset_action = QAction(
                _menu_icon("rotate-ccw"),
                t("dashboard.columns_menu.reset"),
                menu,
            )
        except Exception:
            reset_action = QAction(t("dashboard.columns_menu.reset"), menu)
        reset_action.setToolTip(t("dashboard.columns_menu.reset_tip"))
        reset_action.triggered.connect(self._reset_queue_layout)
        menu.addAction(reset_action)
        menu.exec(pos)

    def _visible_check_jobs(self) -> list[tuple[str, str]]:
        """pid+title of the rows the table paints, capped at the painting window."""
        jobs = []
        for ds in list(getattr(self, "_datasets", []))[: self._MAX_PAINTED_ROWS]:
            pid = str(ds.get("persistent_id") or "").strip()
            if pid:
                jobs.append((pid, str(ds.get("title") or "")))
        return jobs

    def _build_queue_context_menu(self) -> QMenu:
        """Build the queue's right-click menu (dv-9m2).

        One item while idle: bulk-run file checks for the visible rows
        (the painting window, never beyond). While a bulk run is in
        flight, the same menu offers to cancel it.
        """
        menu = QMenu(self)
        if self._bulk_worker is not None:
            cancel = menu.addAction(t("dashboard.context.cancel_bulk_checks"))
            cancel.triggered.connect(self._on_cancel_bulk_checks)
            return menu
        count = len(self._visible_check_jobs())
        action = menu.addAction(t("dashboard.context.run_checks_visible", count=count))
        action.setEnabled(count > 0)
        action.setToolTip(t("dashboard.context.run_checks_visible_tip"))
        action.triggered.connect(self._enqueue_visible_checks)
        return menu

    def _show_queue_context_menu(self, pos: QPoint) -> None:
        menu = self._build_queue_context_menu()
        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _enqueue_visible_checks(self) -> None:
        """Enqueue the visible rows for a bulk file-checks pass.

        Capped at the painting window by construction; the enqueued count
        is logged. The worker runs sequentially in the background and
        writes each report to the same checks-report.json the detail view
        auto-loads — open the dataset afterwards and the results are
        already there.
        """
        jobs = self._visible_check_jobs()
        count = len(jobs)
        self._bulk_enqueued = list(jobs)
        try:
            from curation.applog import get_app_log

            get_app_log().info(t("dashboard.log.bulk_checks_enqueued", count=count))
        except Exception:
            pass
        self._progress.setText(t("dashboard.progress.bulk_checks_enqueued", count=count))
        if not jobs:
            return
        if self._bulk_worker is not None:
            return
        self._bulk_worker = BulkCheckWorker(jobs, self._config.app.workspace, self)
        self._bulk_worker.progress.connect(self._progress.setText)
        self._bulk_worker.progressFraction.connect(self._on_bulk_fraction)
        self._bulk_worker.finished.connect(self._on_bulk_checks_finished)
        self._bulk_worker.cancelled.connect(self._on_bulk_checks_cancelled)
        self._bulk_worker.error.connect(self._on_bulk_checks_error)
        try:
            self._ring.reset()
            self._ring.setFraction(0.0)
            self._ring.show()
        except Exception:
            pass
        self._bulk_worker.start()

    def _on_bulk_fraction(self, fraction: float) -> None:
        try:
            self._ring.setFraction(fraction)
        except Exception:
            pass

    def _bulk_wrap_up(self) -> None:
        try:
            self._ring.setFraction(1.0)
        except Exception:
            pass
        self._hide_ring()
        self._bulk_worker = None
        self._sync_status_bar()

    def _on_bulk_checks_finished(self, summary: dict[str, Any]) -> None:
        total = int(summary.get("total", 0)) if isinstance(summary, dict) else 0
        completed = int(summary.get("completed", 0)) if isinstance(summary, dict) else 0
        skipped = int(summary.get("skipped", 0)) if isinstance(summary, dict) else 0
        failed = int(summary.get("failed", 0)) if isinstance(summary, dict) else 0
        try:
            from curation.applog import get_app_log

            get_app_log().info(
                t(
                    "dashboard.log.bulk_checks_done",
                    completed=completed,
                    skipped=skipped,
                    failed=failed,
                    total=total,
                )
            )
        except Exception:
            pass
        self._progress.setText(
            t(
                "dashboard.progress.bulk_checks_done",
                completed=completed,
                skipped=skipped,
                failed=failed,
                total=total,
            )
        )
        self._bulk_wrap_up()

    def _on_bulk_checks_cancelled(self) -> None:
        try:
            from curation.applog import get_app_log

            get_app_log().info(t("dashboard.log.bulk_checks_cancelled"))
        except Exception:
            pass
        self._progress.setText(t("dashboard.progress.bulk_checks_cancelled"))
        self._bulk_wrap_up()

    def _on_bulk_checks_error(self, message: str) -> None:
        from ui.dialogs import describe_error, show_warning

        headline, details = describe_error(message)
        self._progress.setText(t("dashboard.progress.bulk_checks_error"))
        self._bulk_wrap_up()
        show_warning(
            self,
            t("dashboard.dialogs.bulk_checks_title"),
            headline,
            details=details,
        )

    def _on_cancel_bulk_checks(self) -> None:
        worker = self._bulk_worker
        if worker is not None:
            try:
                worker.cancel()
            except Exception:
                pass

    def _reset_queue_layout(self) -> None:
        """Reset the queue table to its construction view, then repaint."""
        try:
            layout = getattr(self, "_queue_layout", None)
            if layout is not None:
                layout.reset()
            self._table.enable_auto_fit()
            self._queue_unscaled = None
            self._fit_queue_columns()
            # Repaint rows (repopulation re-sorts exactly like a fresh
            # table, so reset reproduces startup order precisely).
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
        # A manual refresh owns the queue from here: the deferred startup
        # paint must not overwrite fresher rows with stale cache.
        self._startup_started = True
        self._restoring = False
        if self._worker is not None and self._worker.isRunning():
            self._progress.setText(t("dashboard.progress.already_loading"))
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
                self._progress.setText(t("dashboard.progress.api_key"))
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
                t(
                    "dashboard.progress.checking_cached",
                    count=len(self._all_datasets),
                )
            )
        else:
            self._progress.setText(t("dashboard.progress.contacting"))

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

    def _apply_size_cache(self, datasets: list[dict[str, Any]]) -> None:
        """Fill unknown Size cells from the downloaded-metadata cache.

        Search records carry no byte totals; once a dataset's metadata has
        been loaded in the detail view, its summed inventory size is cached
        on disk and shown here instead of "—".
        """
        try:
            from curation.storage import read_size_cache

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
            attach_follow_ups(self._all_datasets, local_follow_ups(Path(ws)))
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

    def _on_enrichment_batch(self, batch: list[dict[str, Any]]) -> None:
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

    def _on_crawl_finished(  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
        self, datasets: list[dict[str, Any]]
    ) -> None:
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
            attach_follow_ups(datasets, local_follow_ups(Path(ws)))
            try:
                self._decided_cache = _decided_ids(Path(ws))
            except Exception:
                self._decided_cache = set()
            self._apply_size_cache(datasets)
            self._all_datasets = datasets
            self._crawled = True
            self._merge_row_labels()
            self._rebuild_collection_filter()
            # Persist this crawl so the next app open paints instantly.
            try:
                save_dashboard_cache(
                    ws, self._dashboard_cache_key(), datasets, self._curation_labels
                )
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
                    self._progress.setText(t("dashboard.progress.first_result", total=total))
                elif not (n_new or n_chg or n_del):
                    self._progress.setText(t("dashboard.progress.no_changes", total=total))
                else:
                    parts = []
                    if n_new:
                        parts.append(t("dashboard.progress.new", count=n_new))
                    if n_chg:
                        parts.append(t("dashboard.progress.updated", count=n_chg))
                    if n_del:
                        parts.append(t("dashboard.progress.removed", count=n_del))
                    self._progress.setText(
                        t(
                            "dashboard.progress.changes",
                            changes=", ".join(parts),
                            total=total,
                        )
                    )
            except Exception:
                pass
        except Exception as exc:
            import traceback

            self._refresh_btn.setEnabled(True)
            self._progress.setText(t("dashboard.progress.render_error"))
            from ui.dialogs import show_warning

            show_warning(
                self,
                t("dashboard.dialogs.render_title"),
                t("dashboard.dialogs.render_text"),
                details=f"{exc}\n\n{traceback.format_exc()}",
            )

    def _update_metrics(self) -> None:
        """All three cards from REAL data; named states before the first crawl.

        - Pending Datasets: versionState DRAFT (plain drafts awaiting triage)
        - In Review: locked for review (confirmed via the locks endpoint)
        - In Progress: rows carrying any curation label (any state)

        Before the first crawl finishes each card states its condition in
        words ("Checking…" while the crawl runs, "Not fetched" when idle)
        instead of a bare "—", so a visible 0 can only ever mean a completed
        check counted zero. Cards carry no tooltip (dv-1k4): a hover state
        shows they filter the queue.
        """
        loading = self._worker is not None and self._worker.isRunning()
        restoring = bool(getattr(self, "_restoring", False))
        if not self._crawled:
            state = (
                t("dashboard.metrics.checking")
                if (loading or restoring)
                else t("dashboard.metrics.not_fetched")
            )
            for v_lbl in self._metric_value_labels:
                if v_lbl:
                    v_lbl.setText(state)
                    v_lbl.setProperty("metricToken", _METRIC_STATE_TOKEN)
                    _apply_metric_token(v_lbl)
            self._update_empty_state()
            return
        in_review = sum(1 for d in self._all_datasets if "REVIEW" in (d.get("state") or "").upper())
        pending = sum(1 for d in self._all_datasets if (d.get("state") or "").upper() == "DRAFT")
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
        for val, v_lbl in zip(vals, self._metric_value_labels, strict=False):
            if v_lbl:
                v_lbl.setText(str(val))
                v_lbl.setProperty("metricToken", _METRIC_VALUE_TOKEN)
                _apply_metric_token(v_lbl)
        self._update_empty_state()

    def _cell_text(self, ds: dict[str, Any], key: str) -> str:
        if key == "total_size_bytes":
            raw = ds.get(key)
            if raw is None or raw == "":
                return "—"
            return _human_size(raw)
        if key == "state":
            return _display_state(ds.get("state") or "")
        if key == "access":
            return _access_text(ds)
        if key == "follow_up":
            fu = ds.get("follow_up")
            if not isinstance(fu, dict) or not fu:
                return ""
            if str(fu.get("state") or "") == "depositor_updated":
                return t("dashboard.follow_up.updated")
            return t(
                "dashboard.follow_up.awaiting",
                date=str(fu.get("opened_at") or "")[:10],
            )
        v = ds.get(key, "")
        return "" if v is None else str(v)

    def _cell_sort_key(self, ds: dict[str, Any], key: str) -> float | str:
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
        if key == "follow_up":
            fu = ds.get("follow_up")
            if not isinstance(fu, dict) or not fu:
                return 0.0
            if str(fu.get("state") or "") == "depositor_updated":
                return 2.0
            return 1.0
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

    def _filter_criteria(self) -> tuple[str, str, str, str]:
        """Read the three filter combos and the search box, defensively."""
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
        return text, str(state_key), str(wanted_label), str(wanted_collection)

    @staticmethod
    def _matches_state(ds: dict[str, Any], wanted: str, state_key: str) -> bool:
        ds_state = (ds.get("state") or "").upper()
        if state_key == "All":
            return True
        if wanted == "PENDING":
            # Pending metric: plain drafts plus locked in-review.
            return ds_state == "DRAFT" or "REVIEW" in ds_state
        if wanted == "PUBLISHED":
            return ds_state in ("RELEASED", "PUBLISHED")
        if wanted == "DRAFT":
            return ds_state == "DRAFT"
        if wanted == "IN REVIEW":
            return "REVIEW" in ds_state
        if wanted == "DEACCESSIONED":
            return "DEACCESSIONED" in ds_state
        return wanted == ds_state

    def _matches_filters(self, ds: dict[str, Any], criteria: tuple[str, str, str, str]) -> bool:
        text, state_key, wanted_label, wanted_collection = criteria
        wanted = state_key.upper() if state_key != "All" else ""
        if not self._matches_state(ds, wanted, state_key):
            return False
        # In Progress card: rows with any curation label, any state.
        if (
            getattr(self, "_labelled_only", False)
            and not str(ds.get("curation_label") or "").strip()
        ):
            return False
        label = str(ds.get("curation_label") or "").strip().lower()
        if wanted_label == _NO_LABEL_SENTINEL:
            if label:
                return False
        elif wanted_label and label != wanted_label.strip().lower():
            return False
        if wanted_collection and str(ds.get("collection") or "") != wanted_collection:
            return False
        if text:
            haystack = " ".join(
                str(ds.get(k, ""))
                for k in (
                    "title",
                    "persistent_id",
                    "contact",
                    "depositor",
                    "collection",
                    "state",
                    "curation_label",
                )
            ).lower()
            if text not in haystack:
                return False
        return True

    def _filter_status(self, filtered: list[dict[str, Any]]) -> None:
        if not self._all_datasets:
            self._progress.setText(t("dashboard.progress.no_datasets"))
        elif not filtered:
            self._progress.setText(t("dashboard.progress.no_match", total=len(self._all_datasets)))
        else:
            # Counts + scope live in the status bar now — the pill keeps
            # the standing hint instead of repeating them.
            self._progress.setText(t("dashboard.progress.open_hint"))

    @staticmethod
    def _decorate_size_cell(ds: dict[str, Any], item: Any, text_val: str) -> None:
        """Set the size cell tooltip and dim it when access was refused."""
        if text_val != t("dashboard.display_state.unknown"):
            if ds.get("size_enriched"):
                item.setToolTip(t("dashboard.table.size_enriched", value=text_val))
            elif ds.get("size_from_cache"):
                item.setToolTip(t("dashboard.table.size_cached", value=text_val))
            return
        if ds.get("size_pending"):
            item.setToolTip(t("dashboard.table.size_pending"))
        elif size_unavailable(ds):
            # dv-zhf: the size cannot be had — this account read no
            # version of the dataset. The em dash is dimmed so the cell
            # reads as unavailable, and the hover carries the reason.
            item.setForeground(QBrush(QColor(TEXT_MUTED)))
            item.setToolTip(_access_tooltip(ds))
        else:
            item.setToolTip(t("dashboard.table.size_unknown"))

    def _paint_rows(self, paint_rows: list[dict[str, Any]]) -> None:
        """Rebuild the capped visible slice (filtering itself is uncapped)."""
        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(paint_rows))
        for row, ds in enumerate(paint_rows):
            for col, (key, _h, _v) in enumerate(COLUMNS):
                text_val = self._cell_text(ds, key)
                item = _SortItem(text_val)
                item.setToolTip(text_val)
                if key == "access":
                    # The reason the server refused something, in full.
                    tip = _access_tooltip(ds)
                    if tip:
                        item.setToolTip(tip)
                if key == "total_size_bytes":
                    self._decorate_size_cell(ds, item, text_val)
                sort_key = self._cell_sort_key(ds, key)
                item.setData(Qt.ItemDataRole.UserRole, sort_key)
                # PID/date cells used to carry a raw JetBrains Mono QFont.
                # Table items are not widgets, so QSS never reached them and
                # they rendered in an arbitrary system substitution at 12pt.
                # Leaving the item font unset makes the table's own Inter face
                # apply, like every other cell.
                if key == "title":
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
                self._table.setItem(row, col, item)
        self._table.setSortingEnabled(True)
        # Content-width columns first (no-op once fitted/locked); the
        # columns_fitted signal mirrors sizes onto the display header.
        # Re-arm the one-shot latch before fitting: cached rows can land
        # before the view has its final width, and the fit would otherwise
        # latch at that too-small width and leave the columns squished
        # until the user reset them (dv-81l).
        self._table.refit_columns_to_content()
        self._table.fit_columns_to_content()
        self._table.viewport().update()

    def _apply_filter(self) -> None:
        try:
            criteria = self._filter_criteria()
            filtered = [ds for ds in self._all_datasets if self._matches_filters(ds, criteria)]
            self._datasets = filtered
            self._update_metrics()
            self._sync_status_bar()
            self._filter_status(filtered)

            # Painting window: the table is a QTableWidget (one heap
            # item per cell), so 25k rows × 12 columns is 300k items
            # rebuilt on every filter keystroke. Filter and sort still
            # run over the FULL set; only the painted rows are capped.
            paint_rows = filtered[: DashboardView._MAX_PAINTED_ROWS]
            if len(paint_rows) < len(filtered):
                self._progress.setText(
                    t(
                        "dashboard.progress.painted_cap",
                        shown=len(paint_rows),
                        matching=len(filtered),
                        total=len(self._all_datasets),
                    )
                )
            self._paint_rows(paint_rows)
        except Exception as exc:
            import traceback

            self._refresh_btn.setEnabled(True)
            self._progress.setText(t("dashboard.progress.render_error"))
            from ui.dialogs import show_warning

            show_warning(
                self,
                t("dashboard.dialogs.render_title"),
                t("dashboard.dialogs.render_text"),
                details=f"{exc}\n\n{traceback.format_exc()}",
            )

    def _on_crawl_error(self, msg: str) -> None:
        from ui.dialogs import describe_error, show_warning

        self._worker = None
        self._refresh_btn.setEnabled(True)
        self._progress.setText(t("dashboard.progress.load_error"))
        # Red ring: the failure is visible without opening the dialog.
        try:
            self._ring.show()
            self._ring.setError()
        except Exception:
            pass
        headline, details = describe_error(msg)
        show_warning(
            self,
            t("dashboard.dialogs.load_title"),
            headline,
            details=details,
            retry=self.reload,
        )
        self._update_empty_state()

    def eventFilter(  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
        self, obj: QObject, event: QEvent
    ) -> bool:
        """Keyboard parity for the queue table (P0).

        Enter/Return opens the focused row (double-click alone locks out
        keyboard-only users), F5 refreshes, Escape clears the search box.

        The table's viewport is watched as well: when the window (or the
        vertical scrollbar) changes its width, the queue columns are
        re-fitted so they keep filling it.
        """
        tbl = getattr(self, "_table", None)
        if event.type() == QEvent.Type.Resize:
            try:
                if tbl is not None and (obj is tbl or obj is tbl.viewport()):
                    self._schedule_column_fit()
                    return False
            except Exception:
                pass
        # Metric cards are tappable filters (dv-896).
        if isinstance(obj, QFrame) and obj.objectName() == "MetricCard":
            event = cast(QMouseEvent, event)
            if (
                event.type() == QEvent.Type.MouseButtonPress
                and event.button() == Qt.MouseButton.LeftButton
            ):
                self._on_metric_clicked(str(obj.property("accent") or ""))
                return True
            if event.type() == QEvent.Type.KeyPress and cast(QKeyEvent, event).key() in (
                Qt.Key.Key_Return,
                Qt.Key.Key_Enter,
                Qt.Key.Key_Space,
            ):
                self._on_metric_clicked(str(obj.property("accent") or ""))
                return True
        if tbl is not None and obj is tbl and event.type() == QEvent.Type.KeyPress:
            event = cast(QKeyEvent, event)
            key = event.key()
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                row = self._table.currentRow()
                if row >= 0 and self._table.rowCount():
                    self._on_double_click(row, 0)
                return True
            if key == Qt.Key.Key_F5:
                self.reload()
                return True
            if key == Qt.Key.Key_Escape and self._filter_edit.text():
                self._filter_edit.clear()
                return True
        # Header keyboard sort: Space/Return toggles sort on focused section
        hdr = tbl.horizontalHeader() if tbl is not None else None
        if hdr is not None and obj is hdr and event.type() == QEvent.Type.KeyPress:
            event = cast(QKeyEvent, event)
            key = event.key()
            if key in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
                logical = cast(
                    Any, hdr
                ).currentIndex()  # QHeaderView.currentIndex() is an int at runtime
                if logical >= 0:
                    self._sort_by_column(logical)
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
            row_data: dict[str, Any] = {}
            if not pid:
                # Fallback: match by title (titles are unique enough here)
                match = next((d for d in self._datasets if d.get("title") == title), None)
                if match:
                    pid = match.get("persistent_id", "")
                    title = match.get("title", title)
            for ds in self._datasets:
                if pid and str(ds.get("persistent_id") or "") == pid:
                    row_data = ds
                    break
            if pid:
                # The row travels with the request: what the search payload
                # already knows (draft or no draft) saves the detail view
                # from asking for versions that cannot exist.
                self.openRequested.emit(pid, title or pid, row_data)
        except Exception:
            pass
