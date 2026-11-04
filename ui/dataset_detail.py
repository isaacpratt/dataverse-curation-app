"""Dataset detail — 2-column assessment layout (metadata/files/checks + sticky sidebar).

Left: Auto-Checks + Assessment Action. Right: File Manifest.
Header: persistent ID badge, status pill, title, depositor/date, actions.
Preserves all workers (MetadataWorker, DownloadWorker, CheckWorker) and
the metadata check card (profile selector).
"""

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config import Config
from dataverse_client import DataverseClient
from download_manager import DownloadManager
from metadata_check import DEFAULT_PROFILE, PROFILES
from ui.dialogs import describe_error, show_critical, show_info, show_warning
from ui.download_dialog import DownloadApprovalDialog
from ui.ring import RingProgress
from ui.theme import (
    AMBER_700,
    BACKGROUND,
    ERROR,
    ERROR_CONTAINER,
    ERROR_OUTLINE,
    ERROR_SURFACE,
    ON_ERROR_CONTAINER,
    ON_PRIMARY,
    ON_SECONDARY_CONTAINER,
    ON_SURFACE,
    ON_SURFACE_VARIANT,
    OUTLINE_VARIANT,
    PRIMARY,
    SUCCESS,
    SUCCESS_DARK,
    SURFACE_CONTAINER,
    SURFACE_CONTAINER_HIGH,
    SURFACE_CONTAINER_LOW,
    SURFACE_CONTAINER_LOWEST,
    SURFACE_VARIANT,
    WARNING,
    action_button_style,
    enable_list_copy,
    label_badge_style,
    selectable_labels,
)
from ui.widgets import (
    AppButton,
    AppTable,
    add_info_tip,
    flush_list_style,
    flush_table_style,
    make_card,
    make_combo,
    make_page_heading,
    make_search_field,
)
from ui.workers import CheckWorker, DownloadWorker, MetadataWorker


def _human_size(n: int) -> str:
    """Human-readable size with B/KB/MB/GB/TB (shared with dashboard)."""
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


def _icon_for_ext(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext in (".csv",):
        return "description"
    if ext in (".nc", ".h5", ".hdf5"):
        return "map"
    if ext in (".zip", ".tar", ".gz", ".7z"):
        return "code"
    if ext in (".pdf",):
        return "picture_as_pdf"
    if ext in (".json",):
        return "data_object"
    if ext in (".txt", ".md"):
        return "article"
    return "description"


def _manifest_display_for_entry(e: dict) -> tuple[str, int, str]:
    """(display_path, size_bytes, fmt) for one file-inventory entry.

    Tabular ingests are server-generated `.tab` derivatives of the
    depositor's upload: show the ORIGINAL file (name/format/size) so the
    manifest reads `eco.sav` / SAV rather than `eco.tab` / TAB. The display
    path matches where `DownloadManager.download_originals` stages the
    original (`parent/original_name`), so staged checks and engine-report
    matching keep working. Non-tabular entries (or tabular ones without a
    recorded original) fall back to the inventory path as before.
    """
    try:
        path = str(e.get("path", "") or "")
    except Exception:
        return "", 0, "FILE"
    if not isinstance(e, dict):
        return path, 0, "FILE"
    try:
        size = int(e.get("size_bytes", 0) or 0)
    except (TypeError, ValueError):
        size = 0
    mime = str(e.get("mime_type", "") or "")
    if not (e.get("tabular") and str(e.get("original_name", "") or "").strip()):
        ext = Path(path).suffix.lower().lstrip(".").upper()
        return path, size, ext or mime.split("/")[-1].upper() or "FILE"
    original_base = Path(str(e["original_name"])).name
    parent = path.rpartition("/")[0] if "/" in path else ""
    display = f"{parent}/{original_base}" if parent else original_base
    ext = Path(original_base).suffix.lower().lstrip(".").upper()
    if not ext:
        # Original name without an extension: map the recorded MIME type.
        try:
            import mimetypes as _mimetypes

            guessed = _mimetypes.guess_extension(
                str(e.get("original_format", "") or "").split(";")[0].strip()
            )
            ext = (guessed or "").lstrip(".").upper()
        except Exception:
            ext = ""
    try:
        original_size = int(e.get("original_size", 0) or 0)
    except (TypeError, ValueError):
        original_size = 0
    return (
        display,
        original_size or size,
        ext or Path(path).suffix.lower().lstrip(".").upper() or "FILE",
    )


def _pill_state(version_state: str, in_review: bool = False) -> tuple[str, str]:
    """Return the same words as the dashboard status column (Draft/Published/In Review)."""
    s = (version_state or "").upper()
    if s == "DRAFT":
        if in_review:
            return ("PillInReview", "In Review")
        return ("PillDraft", "Draft")
    if s in ("RELEASED", "PUBLISHED"):
        return ("PillReady", "Published")
    if s == "DEACCESSIONED":
        return ("PillDraft", "Deaccessioned")
    if "REVIEW" in s:
        return ("PillInReview", "In Review")
    if not s:
        return ("PillDraft", "Draft")
    return ("PillDraft", s.title())


def _format_metadata(metadata: dict) -> str:
    if not metadata:
        return "(no metadata returned)"
    try:
        lines = []
        latest = metadata.get("latestVersion") or {}
        blocks = latest.get("metadataBlocks") or metadata.get("metadataBlocks") or {}
        if blocks:
            for block_name, block in blocks.items():
                lines.append(f"[{block_name}] {block.get('displayName','')}")
                for field in block.get("fields", []):
                    t = field.get("typeName", "")
                    v = field.get("value", "")
                    if isinstance(v, list):
                        v = "; ".join(str(x.get("value") if isinstance(x, dict) and "value" in x else x) for x in v[:5])
                    lines.append(f"  {t}: {v}")
                lines.append("")
        lines.append("— Full JSON —")
        lines.append(json.dumps(metadata, indent=2, ensure_ascii=False)[:12000])
        return "\n".join(lines)
    except Exception as exc:
        return json.dumps(metadata, indent=2, ensure_ascii=False)[:12000] + f"\n\n(format error: {exc})"


class DatasetDetailView(QWidget):
    backRequested = Signal()
    metadataLoaded = Signal(str, dict, list)
    # emitted when the real title is known (header/metadata), so TopNav chips show titles
    titleChanged = Signal(str, str)

    def minimumSizeHint(self):  # noqa: N802 (Qt naming)
        """Never let the stacked layout force-grow the main window.

        QStackedWidget's minimum is the max over ALL pages — the tall
        DetailTopBar + Response-page editors would otherwise expand the
        window the first time a dataset opens. Every page scrolls its own
        content, so a modest floor is safe.
        """
        from PySide6.QtCore import QSize

        return QSize(720, 480)

    def sizeHint(self):  # noqa: N802 (Qt naming)
        from PySide6.QtCore import QSize

        return QSize(1200, 760)

    def __init__(
        self,
        config: Config,
        persistent_id: str,
        title: str,
        cached_metadata: dict | None = None,
        cached_inventory: list | None = None,
    ) -> None:
        super().__init__()
        self._config = config
        self._pid = persistent_id
        self._title = title or persistent_id
        self._report = None
        self._inventory: list[dict] = cached_inventory or []
        self._metadata: dict | None = cached_metadata
        self._guestbook: dict | None = None
        self._account: dict = {}
        self._curation: dict = {}
        self._version_diff: dict | None = None
        self._versions: list = []
        self._timestamps: dict = {}
        self._review_submissions: list = []
        self._in_review: bool = False
        self._profile = DEFAULT_PROFILE
        self._check_worker: CheckWorker | None = None
        self._dl_worker: DownloadWorker | None = None
        self._meta_worker: MetadataWorker | None = None
        # Response pane state: full rule results (with rule_id/level/pending),
        # assembled sections, and whether the draft has manual edits.
        self._completeness_full: list = []
        self._ruleset: dict = {}
        self._response_sections: list = []
        self._response_dirty = False
        self._response_loading = False
        self._response_save_timer: QTimer | None = None

        self._client = DataverseClient(config.dataverse.base_url, config.dataverse.api_token)
        self._dl_mgr = DownloadManager(self._client, config.app.workspace)
        # Auto-cached checks report: saved into the dataset's workspace
        # folder after every run and re-loaded here so results survive
        # re-opening the dataset (no re-run needed; re-run refreshes it).
        self._report = self._load_cached_report()
        # Scoped to self: a bare `background` rule would act subtree-wide
        # and override app-level backgrounds (tables, lists, scrollbars).
        self.setObjectName("DetailView")
        self.setStyleSheet(f"QWidget#DetailView {{ background: {BACKGROUND}; }}")
        self.setAutoFillBackground(False)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- Fixed page header (title, actions, status) ----
        top = QWidget()
        top.setObjectName("DetailTopBar")
        top.setStyleSheet(f"QWidget#DetailTopBar {{ background: {BACKGROUND}; border: none; }}")
        top_lay = QVBoxLayout(top)
        top_lay.setContentsMargins(24, 24, 24, 12)
        top_lay.setSpacing(8)
        root.addWidget(top)

        # ---- Pages: Review (existing assessment layout) + Response (draft) ----
        from PySide6.QtWidgets import QStackedWidget as _QStackedWidget

        self._pages = _QStackedWidget()
        self._pages.setObjectName("DetailPages")
        self._pages.setStyleSheet(f"QWidget#DetailPages {{ background: {BACKGROUND}; border: none; }}")
        root.addWidget(self._pages, 1)
        review_page = QWidget()
        review_page.setObjectName("DetailReviewPage")
        review_page.setStyleSheet(f"QWidget#DetailReviewPage {{ background: {BACKGROUND}; border: none; }}")

        # ---- Content row: scrolling main column + sticky sidebar ----
        content_row = QHBoxLayout(review_page)
        content_row.setContentsMargins(0, 0, 0, 0)
        content_row.setSpacing(0)

        # ---- Main column scroll ----
        main_scroll = QScrollArea()
        main_scroll.setWidgetResizable(True)
        main_scroll.setFrameShape(QFrame.NoFrame)
        main_scroll.setStyleSheet(f"QScrollArea {{ background: {BACKGROUND}; border: none; }} QWidget#Canvas {{ background: {BACKGROUND}; }}")
        self._scroll = main_scroll
        canvas = QWidget()
        canvas.setObjectName("Canvas")
        self._canvas = canvas
        main_scroll.setWidget(canvas)
        canvas_lay = QVBoxLayout(canvas)
        canvas_lay.setContentsMargins(24, 12, 12, 24)
        canvas_lay.setSpacing(20)
        # Main column takes the lion's share so the File Manifest tree
        # gets real horizontal room (sidebar stays 280–400 on its own).
        content_row.addWidget(main_scroll, 5)

        # ---- Sticky sidebar (own scroll so Sections never scrolls away) ----
        side_scroll = QScrollArea()
        side_scroll.setWidgetResizable(True)
        side_scroll.setFrameShape(QFrame.NoFrame)
        side_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        side_scroll.setMinimumWidth(280)
        side_scroll.setMaximumWidth(400)
        side_scroll.setStyleSheet(f"QScrollArea {{ background: {BACKGROUND}; border: none; }}")
        content_row.addWidget(side_scroll, 2)

        # ---- Page header (ID badge + status, title, depositor, actions) ----
        header_row = QHBoxLayout()
        header_row.setSpacing(16)
        header_left = QVBoxLayout()
        header_left.setSpacing(6)
        badge_row = QHBoxLayout()
        badge_row.setSpacing(8)
        badge_row.setContentsMargins(0, 0, 0, 0)
        # Full persistent ID, never truncated (DOIs run well past 18 chars).
        self._id_badge = QLabel(self._pid)
        self._id_badge.setToolTip(self._pid)
        self._id_badge.setStyleSheet(
            f"QLabel {{ background: {SURFACE_CONTAINER}; color: {ON_SURFACE_VARIANT}; border: 1px solid {OUTLINE_VARIANT}; border-radius: 8px; padding: 3px 8px; font-family: 'JetBrains Mono', Consolas, monospace; font-size: 12px; }}"
        )
        badge_row.addWidget(self._id_badge)
        self._status_pill = QLabel("Loading…")
        self._status_pill.setObjectName("PillInReview")
        self._status_pill.setStyleSheet(label_badge_style("loading"))
        badge_row.addWidget(self._status_pill)
        self._curation_pill = QLabel("")
        self._curation_pill.setObjectName("PillDraft")
        self._curation_pill.setVisible(False)
        self._curation_pill.setToolTip("Curation label assigned in Dataverse")
        badge_row.addWidget(self._curation_pill)
        badge_row.addStretch()
        header_left.addLayout(badge_row)

        # Same page-heading contract as Settings / Review configuration /
        # Log / About (HeadlineLG theme token).
        self._title_lbl, _subtitle = make_page_heading(self._title)
        self._title_lbl.setWordWrap(True)

        # Clickable Dataverse link sits next to the title
        self._header_link = QLabel()
        self._header_link.setTextFormat(Qt.RichText)
        self._header_link.setOpenExternalLinks(True)
        self._header_link.setStyleSheet(f"font-size: 12px; color: {ON_SURFACE_VARIANT}; border: none; background: transparent;")
        title_row = QHBoxLayout()
        title_row.setSpacing(12)
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.addWidget(self._title_lbl, 1)
        title_row.addWidget(self._header_link, 0, Qt.AlignBottom)
        header_left.addLayout(title_row)

        self._depositor_lbl = QLabel("Loading metadata…")
        self._depositor_lbl.setStyleSheet(f"font-size: 13px; color: {ON_SECONDARY_CONTAINER}; border: none; background: transparent;")
        header_left.addWidget(self._depositor_lbl)
        # Called last: needs _depositor_lbl/_title_lbl/_header_link to exist,
        # and cached metadata makes `meta` truthy immediately.
        self._update_header_link(None)

        header_row.addLayout(header_left, 1)

        # Actions: Download, Export, Load metadata (aligned row), then Run checks
        actions_col = QVBoxLayout()
        actions_col.setSpacing(8)
        actions_col.setAlignment(Qt.AlignTop)
        actions_row = QHBoxLayout()
        actions_row.setSpacing(8)
        self._dl_btn = AppButton("Download All", kind="secondary", size="md")
        # Inline button style: app-level QSS fails to paint button faces inside
        # some main-window subtrees, so critical actions carry their own CSS.
        self._dl_btn.setStyleSheet(action_button_style(False))
        self._dl_btn.clicked.connect(self._on_download)
        actions_row.addWidget(self._dl_btn)
        # Mid-download Cancel — hidden until a worker starts, so the action
        # row keeps its idle layout (critique P3: no silent 15-min wait).
        self._dl_cancel_btn = AppButton("Cancel", kind="secondary", size="md")
        self._dl_cancel_btn.setStyleSheet(action_button_style(False))
        self._dl_cancel_btn.setToolTip("Stop the download — files already staged stay on disk")
        self._dl_cancel_btn.setAccessibleName("Cancel download")
        self._dl_cancel_btn.clicked.connect(self._on_download_cancel_click)
        self._dl_cancel_btn.setVisible(False)
        actions_row.addWidget(self._dl_cancel_btn)
        self._history_btn = AppButton("Export reports…", kind="secondary", size="md")
        self._history_btn.setStyleSheet(action_button_style(False))
        self._history_btn.setToolTip("Save the DatasetReport JSON + Markdown (runs after checks complete)")
        self._history_btn.clicked.connect(self._on_export)
        actions_row.addWidget(self._history_btn)
        self._load_meta_btn = AppButton("Load metadata", kind="secondary", size="md")
        self._load_meta_btn.setStyleSheet(action_button_style(False))
        self._load_meta_btn.setToolTip("Fetch the dataset's file list and all metadata fields from the Dataverse (no download)")
        self._load_meta_btn.clicked.connect(self._on_load_metadata)
        actions_row.addWidget(self._load_meta_btn)
        actions_col.addLayout(actions_row)
        # Run checks as primary (always enabled; warns when nothing is staged)
        self._check_btn = AppButton("Run checks", kind="primary", size="lg")
        self._check_btn.setStyleSheet(action_button_style(True))
        self._check_btn.setToolTip("Download the dataset first — checks run on the staged files")
        self._check_btn.clicked.connect(self._on_run_checks)
        actions_col.addWidget(self._check_btn)
        header_row.addLayout(actions_col, 0)
        top_lay.addLayout(header_row)

        # Status + progress (subtle)
        self._status = QLabel("")
        self._status.setStyleSheet(f"font-size: 11px; color: {ON_SURFACE_VARIANT}; background: {SURFACE_CONTAINER_LOWEST}; border: 1px solid {OUTLINE_VARIANT}; border-radius: 8px; padding: 6px 10px;")
        self._status.setWordWrap(True)
        self._status.setVisible(False)
        top_lay.addWidget(self._status)
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._progress.setFixedHeight(6)
        top_lay.addWidget(self._progress)
        # Circular ring for download/check progress (W-12): a determinate
        # arc beside the linear bar, since the bar is indeterminate for
        # streamed bundles.
        self._ring = RingProgress(diameter=18)
        self._ring.hide()
        top_lay.addWidget(self._ring)
        top_lay.setAlignment(self._ring, Qt.AlignVCenter)

        # Review / Response switch (second page per dataset: the depositor draft).
        tab_row = QHBoxLayout()
        tab_row.setSpacing(8)
        tab_row.setContentsMargins(0, 4, 0, 0)
        self._tab_review = AppButton("Review", kind="secondary", size="sm")
        self._tab_review.setStyleSheet(action_button_style(False))
        self._tab_review.clicked.connect(self._show_review_page)
        tab_row.addWidget(self._tab_review)
        self._tab_response = AppButton("Response", kind="secondary", size="sm")
        self._tab_response.setStyleSheet(action_button_style(False))
        self._tab_response.setToolTip("Draft the review response for the dataset depositor")
        self._tab_response.clicked.connect(self._show_response_page)
        tab_row.addWidget(self._tab_response)
        tab_row.addStretch(1)
        self._response_hint = QLabel("")
        self._response_hint.setStyleSheet(f"font-size: 11px; color: {ON_SECONDARY_CONTAINER}; background: transparent; border: none;")
        tab_row.addWidget(self._response_hint)
        top_lay.addLayout(tab_row)

        # ---- Main column content (inside main_scroll canvas) ----
        # MAIN column: completeness → files → auto-checks → version diff
        main_wrap = QVBoxLayout()
        main_wrap.setSpacing(20)
        main_wrap.setContentsMargins(0, 0, 0, 0)

        self._meta_card = self._build_metadata_card()
        main_wrap.addWidget(self._meta_card)

        self._file_card = self._build_file_manifest_card()
        main_wrap.addWidget(self._file_card, 1)

        self._auto_card = self._build_auto_checks_card()
        main_wrap.addWidget(self._auto_card)

        self._version_card = self._build_version_card()
        main_wrap.addWidget(self._version_card)

        # Raw metadata expandable (minimal)
        self._raw_btn = AppButton("Show all metadata fields", kind="ghost", size=None)
        self._raw_btn.clicked.connect(self._toggle_raw)
        try:
            from ui.icons import icon as _rw_icon

            self._raw_btn.setIcon(_rw_icon("chevron-right"))
        except Exception:
            pass
        main_wrap.addWidget(self._raw_btn)
        self._raw_view = QTextEdit()
        self._raw_view.setVisible(False)
        self._raw_view.setReadOnly(True)
        self._raw_view.setMinimumHeight(180)
        self._raw_view.setStyleSheet(f"QTextEdit {{ background: {SURFACE_CONTAINER_LOWEST}; border: 1px solid {OUTLINE_VARIANT}; border-radius: 8px; font-family: 'JetBrains Mono', Consolas, monospace; font-size: 11px; }}")
        main_wrap.addWidget(self._raw_view)

        main_container = QWidget()
        main_container.setLayout(main_wrap)
        main_container.setObjectName("DetailMainContainer")
        main_container.setStyleSheet("QWidget#DetailMainContainer { background: transparent; }")
        canvas_lay.addWidget(main_container)

        # SIDEBAR (right, sticky): navigation → dataset log
        # (Assessment Action moved to the Response page.)
        side_wrap = QVBoxLayout()
        side_wrap.setSpacing(20)
        side_wrap.setContentsMargins(12, 12, 24, 24)

        self._nav_card = self._build_nav_card()
        side_wrap.addWidget(self._nav_card)

        self._dataset_log_card = self._build_dataset_log_card()
        # Stretch factor 1: the log owns the sidebar's free vertical space
        # so the timeline reads without constant scrolling.
        side_wrap.addWidget(self._dataset_log_card, 1)

        side_container = QWidget()
        side_container.setLayout(side_wrap)
        side_container.setObjectName("DetailSideContainer")
        side_container.setStyleSheet("QWidget#DetailSideContainer { background: transparent; }")
        side_scroll.setWidget(side_container)

        # Response page (second page per dataset) + register both pages.
        self._response_page = self._build_response_page()
        self._pages.addWidget(review_page)
        self._pages.addWidget(self._response_page)
        self._pages.setCurrentWidget(review_page)
        self._in_response = False

        # Default handling for cached metadata (session cache, else disk
        # cache from a previous launch — disk and fresh views refresh in
        # the background; session-cached views do not refetch).
        session_cached = self._metadata is not None
        from_disk = False
        if not session_cached:
            try:
                disk_meta, disk_inv = self._dl_mgr.load_metadata(self._pid)
            except Exception:
                disk_meta, disk_inv = None, None
            if disk_meta is not None:
                self._metadata = disk_meta
                self._inventory = disk_inv or []
                from_disk = True
        if self._metadata is not None:
            self._update_header_link(self._metadata)
            self._raw_view.setPlainText(_format_metadata(self._metadata))
            self._populate_completeness(self._metadata)
            self._populate_version_diff()
            if self._inventory:
                self._populate_from_inventory()
                if from_disk:
                    self._set_status(
                        f"Loaded saved metadata ({len(self._inventory)} file(s)) — refreshing… "
                    )
                else:
                    self._set_status(
                        f"Metadata cached — {len(self._inventory)} file(s) in inventory."
                    )
            elif isinstance(self._inventory, list) and len(self._inventory) == 0:
                # Cached, and genuinely zero files — say so plainly
                from ui.checks_tree import build_tree_model

                self._file_tree.setModel(build_tree_model([], None))
                self._all_file_rows = []
                self._file_footer_left.setText("This dataset contains no files.")
                self._file_footer_right.setText("")
                self._set_status("This dataset contains no files in Dataverse — metadata checks above still apply.")
            else:
                self._refresh_files_placeholder()
            self._refresh_curation_preview()
            self._refresh_decision_options()
            self._refresh_dataset_log()
            if not session_cached:
                QTimer.singleShot(100, self._on_load_metadata)
        else:
            self._refresh_files_placeholder()
            self._refresh_dataset_log()
            QTimer.singleShot(100, self._on_load_metadata)

        if self._report is not None:
            # Cached checks report (auto-saved on every run): results are
            # already rendered by the refresh calls above; keep Export
            # available and say where the results came from.
            try:
                self._history_btn.setEnabled(True)
            except Exception:
                pass
            if not self._status.isVisible():
                try:
                    stamp = str(getattr(self._report, "timestamp", "") or "")[:19].replace("T", " ")
                    self._set_status(
                        f"Loaded saved checks report ({stamp}) — Run checks to refresh."
                    )
                except Exception:
                    pass

        # Text selection + table copy support
        enable_list_copy(self._dataset_log)
        # Selectable labels get the app's selection colours (see
        # selectable_labels): the system highlight painted a black box
        # behind the "N/M fields complete" summary.
        selectable_labels(self)

        # Review is the landing page; restore any saved per-dataset draft
        # after the first completeness evaluation built the findings list.
        try:
            self._show_review_page()
            if self._metadata is not None:
                self._load_working_draft()
        except Exception:
            pass

    # ---- Builders ----
    def _build_auto_checks_card(self) -> QFrame:
        card, _body_host, _title, header_lay = make_card("Auto-Checks")
        add_info_tip(
            header_lay,
            "Dataset checks appear here with their full messages. Rows list "
            "every finding (dataset checks plus per-file failures and skips); "
            "per-file passes live in File Manifest below — expand a file to "
            "see every check, passes included.",
            "✓ pass · ✕ issue · ○ SKIPPED · MISSING = optional library not installed.",
            name="Auto-Checks",
        )
        # Named pre-run state, never "—" (2026-10-02 P2); refreshed to
        # "N check(s) will run"/counts/"No file checks" as data lands.
        self._auto_summary = QLabel("Not run yet")
        self._auto_summary.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {ON_SURFACE_VARIANT}; background: transparent; border: none;")
        header_lay.addWidget(self._auto_summary)
        # Body: scroll of checks (factory body reused directly)
        self._auto_body = _body_host
        self._auto_body.setContentsMargins(16, 12, 16, 12)
        self._auto_body.setSpacing(8)
        # Placeholder
        self._auto_placeholder = QLabel("No file list yet — load metadata to see which checks will run.")
        self._auto_placeholder.setWordWrap(True)
        self._auto_placeholder.setStyleSheet(f"font-size: 12px; color: {ON_SECONDARY_CONTAINER}; border: none; background: transparent;")
        self._auto_body.addWidget(self._auto_placeholder)
        return card

    def _build_metadata_card(self) -> QFrame:
        card, body, _title, header_lay = make_card("Metadata check")
        add_info_tip(
            header_lay,
            "Metadata completeness for the active profile. Each row shows the "
            "field, its metadata block, the current value and a pass/issue "
            "status; incomplete rows are what is left to fill before "
            "publication. The requirement for a field lives in its tooltip.",
            name="Metadata check",
        )
        # Flush card (manifest-tree pattern): zero body margins; the table
        # bleeds edge-to-edge.
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        # x/xx summary lives in the header, right next to the title (the
        # old in-body summary line was removed).
        self._meta_summary = QLabel("Not loaded yet")
        self._meta_summary.setTextFormat(Qt.RichText)
        self._meta_summary.setStyleSheet(
            f"font-size: 12px; font-weight: 600; color: {ON_SURFACE_VARIANT}; "
            "background: transparent; border: none;"
        )
        self._meta_summary.setToolTip("Load metadata from Dataverse to evaluate completeness")
        header_lay.insertWidget(2, self._meta_summary)
        # Complete/incomplete filter for the checklist table.
        self._meta_filter = make_combo(
            [("All fields", "all"), ("Complete", "complete"), ("Incomplete", "incomplete")],
            min_width=110,
            tip="Show only complete or incomplete metadata checks",
        )
        self._meta_filter.currentIndexChanged.connect(lambda _i: self._apply_meta_filter())
        header_lay.addWidget(self._meta_filter)
        # Standard 36px field like every other combo (a shorter button here
        # made this menu's rows read differently-sized vs the rest).
        self._profile_combo = make_combo(
            [(info["label"], key) for key, info in PROFILES.items()],
            min_width=140,
        )
        idx = list(PROFILES.keys()).index(DEFAULT_PROFILE) if DEFAULT_PROFILE in PROFILES else 0
        self._profile_combo.setCurrentIndex(idx)
        self._profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        header_lay.addWidget(self._profile_combo)
        self._meta_reset_btn = AppButton("", kind="ghost", size="sm")
        self._meta_reset_btn.setFixedSize(28, 28)
        self._meta_reset_btn.setAccessibleName("Reset metadata table columns")
        try:
            from ui.icons import icon as _reset_icon

            self._meta_reset_btn.setIcon(_reset_icon("rotate-ccw"))
        except Exception:
            self._meta_reset_btn.setText("Reset")
        self._meta_reset_btn.setToolTip("Reset columns, sort and widths to default")
        self._meta_reset_btn.clicked.connect(self._on_reset_meta_view)
        header_lay.addWidget(self._meta_reset_btn)
        # Every check with its status — visible table
        # (Field | Block | Value | Status). Requirement text lives in the
        # Field cell's tooltip. Value is Interactive so its right edge
        # (the Value↔Status boundary) can be drag-resized — Stretch mode
        # makes that handle dead. Status stretches last and absorbs slack.
        self._meta_check_table = AppTable(
            ["Check", "Block", "Value", "Status"],
            widths={0: 150, 1: 180, 2: 220, 3: 110},
            row_height=28,
        )
        from PySide6.QtWidgets import QHeaderView as _QHV

        _meta_hdr = self._meta_check_table.horizontalHeader()
        _meta_hdr.setStretchLastSection(True)
        for _i in range(self._meta_check_table.columnCount()):
            _meta_hdr.setSectionResizeMode(_i, _QHV.Interactive)
        self._meta_check_table.setStyleSheet(flush_table_style())
        self._track_table_widths("dataset_meta", self._meta_check_table.horizontalHeader())
        # No internal scrollbars: the card always fits every row; the page
        # canvas scrolls instead. Height is fitted in _apply_meta_filter.
        self._meta_check_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._meta_check_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body.addWidget(self._meta_check_table)
        return card

    def _apply_meta_filter(self) -> None:
        """Apply the Complete/Incomplete header filter and refit the card.

        Hidden rows never leave blank space: the card height follows the
        visible row count (same fit formula as before filtering).
        """
        table = self._meta_check_table
        try:
            mode = self._meta_filter.currentData() or "all"
        except Exception:
            mode = "all"
        for row in range(table.rowCount()):
            item = table.item(row, 3)
            try:
                ok = bool(item.data(Qt.UserRole)) if item is not None else False
            except Exception:
                ok = False
            table.setRowHidden(
                row, (mode == "complete" and not ok) or (mode == "incomplete" and ok)
            )
        try:
            visible = sum(
                1 for row in range(table.rowCount()) if not table.isRowHidden(row)
            )
            header_h = table.horizontalHeader().height() or 30
            row_h = table.verticalHeader().defaultSectionSize() or 28
            table.setFixedHeight(header_h + visible * row_h + 4)
        except Exception:
            pass

    def _build_assessment_card(self) -> QFrame:
        card, body, _title, _header = make_card("Assessment Action")
        add_info_tip(
            _header,
            "Record the curation decision and internal notes for this dataset. "
            "Commit Decision writes the chosen label to Dataverse when the "
            "instance exposes curation labels, and appends the action to the "
            "Dataset log.",
            name="Assessment Action",
        )
        body.setContentsMargins(16, 16, 16, 16)
        body.setSpacing(12)
        # Internal Notes
        lbl = QLabel("Internal Notes (Markdown supported)")
        lbl.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {ON_SURFACE_VARIANT}; letter-spacing: 0.5px; background: transparent; border: none;")
        body.addWidget(lbl)
        self._notes_edit = QTextEdit()
        self._notes_edit.setPlaceholderText("Enter findings, issues, or specific instructions for the author...")
        self._notes_edit.setFixedHeight(110)
        self._notes_edit.setStyleSheet(f"QTextEdit {{ background: {SURFACE_CONTAINER_LOWEST}; border: 1px solid {OUTLINE_VARIANT}; border-radius: 8px; font-size: 12px; }} QTextEdit:focus {{ border: 1px solid {PRIMARY}; }}")
        body.addWidget(self._notes_edit)
        # Decision State
        lbl2 = QLabel("Decision State")
        lbl2.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {ON_SURFACE_VARIANT}; letter-spacing: 0.5px; background: transparent; border: none;")
        body.addWidget(lbl2)
        self._decision_combo = make_combo(
            tip="Curation labels from this Dataverse instance "
            "(falls back to generic states when labels are unavailable)",
        )
        self._refresh_decision_options()
        body.addWidget(self._decision_combo)
        # One-line consequence helper: names what recording the choice will
        # actually do BEFORE the commit, and Commit stays disabled while the
        # combo sits on the non-answer placeholder (2026-10-02 P3 — the
        # widest decision point had neither).
        self._decision_help = QLabel("")
        self._decision_help.setWordWrap(True)
        self._decision_help.setStyleSheet(
            f"font-size: 11px; color: {ON_SECONDARY_CONTAINER}; "
            "background: transparent; border: none;"
        )
        body.addWidget(self._decision_help)
        # Commit button row
        row = QHBoxLayout()
        row.addStretch()
        commit = AppButton("Commit Decision", kind="primary", size="md")
        commit.setStyleSheet(action_button_style(True))
        commit.clicked.connect(self._on_commit)
        self._commit_btn = commit
        row.addWidget(commit)
        body.addLayout(row)
        # Widgets exist now: gate + helper follow the restored choice, and
        # every later combo change re-syncs them.
        self._decision_combo.currentIndexChanged.connect(self._sync_decision_state)
        self._sync_decision_state()
        return card

    def _build_nav_card(self) -> QFrame:
        """Sidebar section navigation — jumps the main column to each box."""
        from ui.icons import icon as _nav_icon

        card, body, _title, _header = make_card("Sections")
        body.setSpacing(6)
        self._nav_buttons: list = []
        for label, attr in [
            ("Metadata check", "_meta_card"),
            ("File Manifest", "_file_card"),
            ("Auto-Checks", "_auto_card"),
            ("Version log", "_version_card"),
        ]:
            btn = AppButton(label, kind="ghost", size=None)
            btn.setStyleSheet(
                "QPushButton { text-align: left; padding: 7px 8px; font-size: 12px; "
                f"color: {PRIMARY}; background: transparent; border: none; border-radius: 8px; }}"
                f"QPushButton:hover {{ background: {SURFACE_CONTAINER}; }}"
            )
            try:
                btn.setIcon(_nav_icon("arrow-right", color=PRIMARY))
            except Exception:
                pass
            btn.clicked.connect(lambda _c, a=attr: self._goto_section(a))
            body.addWidget(btn)
            self._nav_buttons.append(btn)
        return card

    # ---- Response page (second page per dataset) ---------------------------
    def _build_response_page(self) -> QWidget:
        from PySide6.QtWidgets import QListWidget, QListWidgetItem  # noqa: F401

        # Scroll-wrapped so the page's own minimum stays small: the stacked
        # layout takes the max of all page minimums, and the editors below
        # (240 + 280 px) used to force the main window taller on first open.
        outer = QWidget()
        outer.setObjectName("DetailResponsePage")
        outer.setStyleSheet(f"QWidget#DetailResponsePage {{ background: {BACKGROUND}; border: none; }}")
        outer_lay = QVBoxLayout(outer)
        outer_lay.setContentsMargins(0, 0, 0, 0)
        outer_lay.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(f"QScrollArea {{ background: {BACKGROUND}; border: none; }}")
        outer_lay.addWidget(scroll)
        page = QWidget()
        page.setObjectName("DetailResponseInner")
        page.setStyleSheet(f"QWidget#DetailResponseInner {{ background: {BACKGROUND}; border: none; }}")
        scroll.setWidget(page)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(24, 12, 24, 24)
        lay.setSpacing(12)

        intro = QLabel("Response — draft the message for the dataset depositor. The checklist on the left is pulled from the active ruleset (incomplete checks) plus failed file checks; uncheck items to drop them, then edit the draft on the right freely and copy or export it.")
        intro.setWordWrap(True)
        intro.setStyleSheet(f"font-size: 12px; color: {ON_SECONDARY_CONTAINER}; background: transparent; border: none;")
        lay.addWidget(intro)

        self._response_summary = QLabel("Load metadata to build the draft.")
        self._response_summary.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {ON_SURFACE_VARIANT}; background: transparent; border: none;")
        lay.addWidget(self._response_summary)

        # Two columns: findings checklist (left) | editable draft (right).
        cols = QHBoxLayout()
        cols.setSpacing(12)

        findings_card, findings_body, _t, _h = make_card("Findings included in the draft")
        add_info_tip(
            _h,
            "Incomplete metadata checks and failed file checks included in the "
            "response draft. Uncheck an item to drop it from the draft.",
            name="Findings included in the draft",
        )
        self._response_list = QListWidget()
        self._response_list.setMinimumHeight(240)
        self._response_list.setStyleSheet(
            f"QListWidget {{ background: {SURFACE_CONTAINER_LOWEST}; border: 1px solid {SURFACE_CONTAINER_HIGH}; border-radius: 8px; "
            f"font-size: 12px; color: {ON_SURFACE_VARIANT}; }}"
        )
        self._response_list.itemChanged.connect(self._on_response_item_changed)
        findings_body.addWidget(self._response_list, 1)
        cols.addWidget(findings_card, 1)

        draft_card, draft_body, _t2, _h2 = make_card("Draft (editable)")
        add_info_tip(
            _h2,
            "Editable response text. Regenerate rebuilds it from the checked "
            "findings (discarding edits); Export saves it as Markdown.",
            name="Draft",
        )
        self._response_edit = QTextEdit()
        self._response_edit.setPlaceholderText("The draft appears here once metadata is loaded…")
        self._response_edit.setMinimumHeight(280)
        self._response_edit.setStyleSheet(f"QTextEdit {{ background: {SURFACE_CONTAINER_LOWEST}; border: 1px solid {OUTLINE_VARIANT}; border-radius: 8px; font-size: 13px; }} QTextEdit:focus {{ border: 1px solid {PRIMARY}; }}")
        self._response_edit.textChanged.connect(self._on_response_text_edited)
        draft_body.addWidget(self._response_edit, 1)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        # One primary, the rest ghost — equal-weight secondaries read as
        # three peers with no obvious next step (2026-10-02 minor).
        ghost_sm = (
            f"QPushButton {{ background: transparent; border: none; color: {ON_SURFACE}; "
            "border-radius: 8px; font-size: 12px; }"
            f"QPushButton:hover {{ background: {SURFACE_CONTAINER}; }}"
        )
        regen = AppButton("Regenerate", kind="ghost", size="sm")
        regen.setStyleSheet(ghost_sm)
        regen.setToolTip("Rebuild the draft from the current findings (discards manual edits)")
        regen.clicked.connect(lambda: self._refresh_response(force=True))
        btn_row.addWidget(regen)
        copy_btn = AppButton("Copy", kind="ghost", size="sm")
        copy_btn.setStyleSheet(ghost_sm)
        copy_btn.clicked.connect(self._on_response_copy)
        btn_row.addWidget(copy_btn)
        export_btn = AppButton("Export…", kind="primary", size="sm")
        export_btn.setStyleSheet(action_button_style(True))
        export_btn.setToolTip("Save the draft as Markdown (logged in the Dataset log)")
        export_btn.clicked.connect(self._on_response_export)
        btn_row.addWidget(export_btn)
        btn_row.addStretch(1)
        self._response_dirty_lbl = QLabel("")
        self._response_dirty_lbl.setStyleSheet(f"font-size: 11px; color: {ON_SECONDARY_CONTAINER}; background: transparent; border: none;")
        btn_row.addWidget(self._response_dirty_lbl)
        draft_body.addLayout(btn_row)
        cols.addWidget(draft_card, 2)

        lay.addLayout(cols, 1)

        # Assessment Action (moved from the review-page sidebar): the
        # response workflow reads left-to-right, top-to-bottom —
        # checklist → draft → decision — so the commit step lives here.
        self._assessment_card = self._build_assessment_card()
        lay.addWidget(self._assessment_card)
        lay.addStretch(1)
        return outer

    def _show_review_page(self) -> None:
        try:
            self._pages.setCurrentIndex(0)
            self._in_response = False
            self._tab_review.setStyleSheet(action_button_style(True))
            self._tab_response.setStyleSheet(action_button_style(False))
        except Exception:
            pass

    def _show_response_page(self) -> None:
        try:
            self._pages.setCurrentIndex(1)
            self._in_response = True
            self._tab_review.setStyleSheet(action_button_style(False))
            self._tab_response.setStyleSheet(action_button_style(True))
            self._refresh_response()
        except Exception:
            pass

    def _staged_dir_or_none(self):  # type: ignore[no-untyped-def]
        try:
            staged = self._dl_mgr.files_dir(self._pid)
            return staged if staged.exists() else None
        except Exception:
            return None

    def refresh_rules(self) -> None:
        """Reload rule profiles (after Review-config save) and re-evaluate."""
        try:
            import metadata_check as _mc

            _mc.refresh_profiles_from_rulesets()
            combo = getattr(self, "_profile_combo", None)
            if combo is not None:
                current = self._profile
                combo.blockSignals(True)
                try:
                    combo.clear()
                    for key, info in _mc.PROFILES.items():
                        combo.addItem(info.get("label", key), key)
                    idx = combo.findData(current)
                    combo.setCurrentIndex(idx if idx >= 0 else 0)
                    self._profile = combo.currentData() or current
                finally:
                    combo.blockSignals(False)
            if self._metadata is not None:
                self._populate_completeness(self._metadata)
        except Exception:
            pass

    def _response_draft_path(self):  # type: ignore[no-untyped-def]
        try:
            return self._dl_mgr.dataset_dir(self._pid) / "response_draft.md"
        except Exception:
            return None

    def _refresh_response(self, force: bool = False) -> None:
        """Rebuild findings + draft (skips overwriting manual edits unless forced)."""
        if getattr(self, "_response_loading", False):
            return
        try:
            from response_draft import build_response
        except Exception:
            return
        if self._metadata is None:
            try:
                self._response_summary.setText("Load metadata to build the draft.")
            except Exception:
                pass
            return
        if self._response_dirty and not force:
            # Findings may have changed; keep the editor, nudge to regenerate.
            try:
                n = sum(1 for s in (self._response_sections or []) if s.get("included"))
                self._response_hint.setText(f"{n} finding(s) in draft — findings changed, press Regenerate to update.")
            except Exception:
                pass
            self._rebuild_findings_list(keep_checks=True)
            return
        try:
            ruleset = self._ruleset if isinstance(self._ruleset, dict) and self._ruleset else None
            if ruleset is None:
                import review_rules as _rr

                try:
                    pool = _rr.load_rulesets()
                except Exception:
                    pool = {}
                key = "mcmaster-default"
                try:
                    import metadata_check as _mc

                    key = _mc.PROFILE_TO_RULESET.get(self._profile, self._profile)
                    if key not in pool:
                        key = "mcmaster-default"
                except Exception:
                    pass
                ruleset = _rr.get_ruleset(key, pool)
                self._ruleset = ruleset
            md, sections = build_response(
                ruleset, self._completeness_full or [], self._report,
                self._title, self._pid,
            )
            self._response_sections = sections
            self._rebuild_findings_list(keep_checks=False)
            self._response_loading = True
            try:
                self._response_edit.setPlainText(md)
            finally:
                self._response_loading = False
            self._response_dirty = False
            self._update_response_chrome()
            if force:
                # Explicit Regenerate discards manual edits — persist the new
                # draft so a reopen shows it. Automatic refreshes never
                # clobber a previously saved working draft on load.
                self._save_working_draft()
        except Exception:
            pass

    def _rebuild_findings_list(self, keep_checks: bool = False) -> None:
        from PySide6.QtWidgets import QListWidgetItem

        try:
            prev = {}
            if keep_checks:
                for i in range(self._response_list.count()):
                    item = self._response_list.item(i)
                    if item is not None:
                        prev[str(item.data(Qt.UserRole) or "")] = item.checkState() == Qt.Checked
            self._response_list.blockSignals(True)
            self._response_list.clear()
            for s in (self._response_sections or []):
                kind = "metadata" if s.get("kind") == "metadata" else "file check"
                # Severity raised in the label + colour: errors red,
                # warnings amber (file-check levels from the run, metadata
                # levels from the active ruleset).
                level = str(s.get("level") or "").lower()
                tag = {
                    "error": "error",
                    "warning": "warning",
                    "required": "required",
                    "optional": "recommended",
                }.get(level, level)
                label = f"[{kind}{f' — {tag}' if tag else ''}] {s.get('label','')}"
                item = QListWidgetItem(label)
                if level == "error":
                    item.setForeground(QColor(ERROR))
                elif level == "warning":
                    item.setForeground(QColor(AMBER_700))
                item.setData(Qt.UserRole, str(s.get("id") or label))
                item.setToolTip(str(s.get("message") or "")[:400])
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                if keep_checks:
                    checked = prev.get(str(s.get("id") or label), bool(s.get("included")))
                else:
                    checked = bool(s.get("included"))
                s["included"] = checked
                item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
                self._response_list.addItem(item)
        except Exception:
            pass
        finally:
            try:
                self._response_list.blockSignals(False)
            except Exception:
                pass

    def _update_response_chrome(self) -> None:
        try:
            sections = [s for s in (self._response_sections or []) if s.get("included")]
            n = len(sections)
            total = len(self._response_sections or [])
            if total == 0:
                self._response_summary.setText("No outstanding items — the dataset looks ready for the next step.")
                self._response_hint.setText("")
            else:
                errors = sum(1 for s in sections if str(s.get("level") or "").lower() == "error")
                warns = sum(1 for s in sections if str(s.get("level") or "").lower() == "warning")
                severity = (
                    f" ({warns} warning(s), {errors} error(s))" if warns or errors else ""
                )
                self._response_summary.setText(f"{n} of {total} finding(s) included in the draft{severity}.")
                self._response_hint.setText(f"{n} finding(s) in draft" if n else "Draft excludes all findings")
            self._response_dirty_lbl.setText("edited" if self._response_dirty else "")
        except Exception:
            pass

    def _on_response_item_changed(self, _item) -> None:
        if getattr(self, "_response_loading", False):
            return
        try:
            states = {}
            for i in range(self._response_list.count()):
                item = self._response_list.item(i)
                if item is not None:
                    states[str(item.data(Qt.UserRole) or "")] = item.checkState() == Qt.Checked
            for s in (self._response_sections or []):
                sid = str(s.get("id") or "")
                if sid in states:
                    s["included"] = states[sid]
            from response_draft import render_response

            md = render_response(self._ruleset or {}, self._response_sections or [], self._title, self._pid)
            self._response_loading = True
            try:
                self._response_edit.setPlainText(md)
            finally:
                self._response_loading = False
            self._response_dirty = False
            self._update_response_chrome()
            self._save_working_draft()
        except Exception:
            pass

    def _on_response_text_edited(self) -> None:
        if getattr(self, "_response_loading", False):
            return
        try:
            self._response_dirty = True
            self._update_response_chrome()
            # Debounced auto-save of the working draft (per-dataset).
            timer = getattr(self, "_response_save_timer", None)
            if timer is None:
                timer = QTimer(self)
                timer.setSingleShot(True)
                timer.setInterval(1500)
                timer.timeout.connect(self._save_working_draft)
                self._response_save_timer = timer
            timer.start()
        except Exception:
            pass

    def _save_working_draft(self) -> None:
        try:
            path = self._response_draft_path()
            text = self._response_edit.toPlainText() if hasattr(self, "_response_edit") else ""
            if path is None or not text.strip():
                return
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        except Exception:
            pass

    def _load_working_draft(self) -> bool:
        """Restore the saved per-dataset draft once (marks editor dirty)."""
        try:
            path = self._response_draft_path()
            if path is None or not path.exists():
                return False
            text = path.read_text(encoding="utf-8")
            if not text.strip():
                return False
            self._response_loading = True
            try:
                self._response_edit.setPlainText(text)
            finally:
                self._response_loading = False
            self._response_dirty = True
            self._update_response_chrome()
            return True
        except Exception:
            return False

    def _on_response_copy(self) -> None:
        try:
            from PySide6.QtWidgets import QApplication

            QApplication.clipboard().setText(self._response_edit.toPlainText())
            self._set_status("Response draft copied to clipboard.")
        except Exception:
            pass

    def _on_response_export(self) -> None:
        from pathlib import Path as _P

        from ui.dialogs import show_critical, show_warning

        text = ""
        try:
            text = self._response_edit.toPlainText()
        except Exception:
            pass
        if not text.strip():
            show_warning(self, "Response", "The draft is empty — nothing to export.")
            return
        try:
            from PySide6.QtWidgets import QFileDialog

            try:
                self._dl_mgr.reports_dir(self._pid).mkdir(parents=True, exist_ok=True)
                start = str(self._dl_mgr.reports_dir(self._pid) / "depositor_response.md")
            except Exception:
                start = "depositor_response.md"
            path, _ = QFileDialog.getSaveFileName(
                self, "Export response draft", start, "Markdown (*.md)",
                options=QFileDialog.DontUseNativeDialog,
            )
        except Exception as exc:
            show_critical(self, "Response", f"Could not open the save dialog:\n{exc}")
            return
        if not path:
            return
        try:
            out = _P(path)
            if out.suffix.lower() != ".md":
                out = out.with_suffix(".md")
            out.write_text(text, encoding="utf-8")
        except Exception as exc:
            show_critical(self, "Response", f"Could not write the draft:\n{exc}")
            return
        self._save_working_draft()
        self._log_action("response_exported", f"Response draft saved to {out.name}",
                         {"path": str(out)})
        self._set_status(f"Response draft saved: {out.name} (recorded in Dataset log)")

    def _track_table_widths(self, name: str, header) -> None:
        """Restore the saved table view once, then persist every change.

        Saved on: column resize, column move, and sort clicks. Sort state
        restores here (indicator set on the header); populates re-enable
        sorting afterwards, which re-applies that indicator to fresh rows.
        The pre-restore construction view is snapshotted for the header
        reset buttons (see _reset_table_view).
        """
        try:
            from storage import restore_table_state, save_table_state, snapshot_table_view

            ws = self._config.app.workspace
            try:
                snaps = getattr(self, "_table_snaps", None)
                if snaps is None:
                    self._table_snaps = snaps = {}
                if name not in snaps:
                    snaps[name] = snapshot_table_view(header)
            except Exception:
                pass
            if restore_table_state(ws, name, header):
                try:
                    tbl = header.parent()
                    if hasattr(tbl, "disable_auto_fit"):
                        tbl.disable_auto_fit()
                except Exception:
                    pass

            # Connect the persistence hooks once per header. The file
            # manifest tracks the same header on every refresh (the saved
            # widths have to be re-applied after the content fit), and
            # reconnecting each time would save the layout once per
            # refresh.
            tracked = getattr(self, "_table_tracked_headers", None)
            if tracked is None:
                self._table_tracked_headers = tracked = {}
            if tracked.get(name) is not header:
                tracked[name] = header

                def _save(*_a, _n=name, _h=header) -> None:
                    save_table_state(self._config.app.workspace, _n, _h)

                header.sectionResized.connect(_save)
                header.sectionMoved.connect(_save)
                try:
                    header.sortIndicatorChanged.connect(_save)
                except Exception:
                    pass
        except Exception:
            pass

    def _reset_table_view(self, name: str, header) -> bool:
        """Reset a tracked table to its construction view.

        Restores widths/order/visibility/sort. Clears the persisted entry
        so the reset survives restarts. Returns True when a snapshot was
        applied.
        """
        try:
            from storage import apply_table_view, clear_table_state

            snap = (getattr(self, "_table_snaps", None) or {}).get(name)
            clear_table_state(self._config.app.workspace, name)
            try:
                tbl = header.parent()
                if hasattr(tbl, "enable_auto_fit"):
                    tbl.enable_auto_fit()
            except Exception:
                pass
            if isinstance(snap, dict):
                apply_table_view(header, snap)
                return True
        except Exception:
            pass
        return False

    def _goto_section(self, attr: str) -> None:
        """Scroll so the section's top sits at the main column's top (+ margin)."""
        try:
            if getattr(self, "_in_response", False):
                self._show_review_page()
        except Exception:
            pass
        try:
            from PySide6.QtCore import QPoint

            widget = getattr(self, attr, None)
            bar = self._scroll.verticalScrollBar() if self._scroll is not None else None
            canvas = getattr(self, "_canvas", None)
            if widget is None or bar is None or canvas is None:
                if widget is not None and self._scroll is not None:
                    self._scroll.ensureWidgetVisible(widget, 0, 0)
                return
            y = widget.mapTo(canvas, QPoint(0, 0)).y()
            bar.setValue(max(0, y - 12))
        except Exception:
            pass

    def _build_dataset_log_card(self) -> QFrame:
        from PySide6.QtWidgets import QListWidget

        card, body, _title, _header = make_card("Dataset log")
        add_info_tip(
            _header,
            "Timeline for this dataset (newest first): creation, versions, "
            "record dates, review submissions, curation labels, embargoes, "
            "and local curation actions.",
            name="Dataset log",
        )
        self._dataset_log = QListWidget()
        # Tall timeline: minimum keeps it readable on short screens, the
        # higher maximum + Expanding policy lets it claim the sidebar's
        # free space (the card carries stretch 1 in the sidebar layout).
        self._dataset_log.setMinimumHeight(320)
        self._dataset_log.setMaximumHeight(650)
        self._dataset_log.setSizeAdjustPolicy(QListWidget.AdjustToContentsOnFirstShow)
        self._dataset_log.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self._dataset_log.setWordWrap(True)
        self._dataset_log.setStyleSheet(
            f"QListWidget {{ background: {SURFACE_CONTAINER_LOWEST}; border: 1px solid {SURFACE_CONTAINER_HIGH}; border-radius: 8px; "
            f"font-size: 11px; color: {ON_SURFACE_VARIANT}; }}"
        )
        self._dataset_log.setToolTip(
            "Timeline for this dataset (newest first): creation, versions, "
            "record dates, review submissions, curation labels, embargoes, "
            "and local curation actions"
        )
        body.addWidget(self._dataset_log)
        return card

    def _state(self):  # type: ignore[no-untyped-def]
        """Open the workspace state.db (best-effort; returns None on failure)."""
        try:
            from storage import open_state
            return open_state(self._config.app.workspace)
        except Exception:
            return None

    def _log_action(self, action: str, notes: str = "", details: dict | None = None) -> None:
        st = None
        try:
            st = self._state()
            if st is None:
                return
            st.log_action(self._pid, action, notes=notes, details=details or {})
        except Exception:
            pass
        finally:
            if st is not None:
                try:
                    st.close()
                except Exception:
                    pass
        try:
            self._refresh_dataset_log()
        except Exception:
            pass

    def _refresh_dataset_log(self) -> None:
        """Newest-first timeline: versions, record dates, review, labels, files, local actions.

        Sources (each best-effort; missing sources are simply skipped):
        - versions list: draft created / version published / deaccessioned
        - timestamps endpoint: first published (when different from created),
          DOI minted, draft last updated
        - notifications inbox: submitted for review (matched by title)
        - curation history: label assigned (+ assigner)
        - file inventory: embargo / retention dates
        - local state.db: downloaded / checks run / decision / exported
        """
        from PySide6.QtWidgets import QListWidgetItem

        events: list[tuple[str, str]] = []  # (sort_key, display text)

        def _fmt_ts(raw: str) -> str:
            """Display timestamp as date + time when a time is present.

            ISO datetimes (2026-09-15T14:30:00Z, with TZ/seconds, or space-
            separated) render as 'YYYY-MM-DD HH:MM'; date-only values stay
            date-only so embargo/retention dates don't gain a bogus midnight.
            """
            s = (raw or "").strip()
            if not s:
                return "—"
            t = s.replace("T", " ").replace("Z", "").strip()
            # Drop seconds + fractional/timezone suffixes, keep HH:MM.
            parts = t.split()
            if len(parts) >= 2 and len(parts[0]) == 10 and parts[1][:2].isdigit():
                return f"{parts[0]} {parts[1][:5]}"
            if len(s) > 10 and (s[10] in ("T", " ")):
                return s[:16].replace("T", " ")
            return s[:10]

        def _add(ts: Any, text: str) -> None:
            raw = str(ts or "").strip()
            if raw:
                events.append((raw, f"{_fmt_ts(raw)} — {text}"))
            else:
                events.append(("0000", f"— {text}"))

        versions = self._versions if isinstance(self._versions, list) else []
        dated_creations: list[str] = []
        version_published_days: set[str] = set()
        for v in versions:
            if not isinstance(v, dict):
                continue
            num = v.get("number", "") or ""
            state = (v.get("state", "") or "").upper()
            ct, rt = v.get("create_time", ""), v.get("release_time", "")
            if ct:
                dated_creations.append(ct)
            if state == "DRAFT":
                _add(ct, f"Version {num} draft created (in progress)")
            elif state == "DEACCESSIONED":
                _add(rt or ct, f"Version {num} deaccessioned")
            else:
                if rt:
                    _add(rt, f"Version {num} published")
                    version_published_days.add(rt[:10])
                if ct and ct[:10] != (rt or "")[:10]:
                    _add(ct, f"Version {num} created")
        if dated_creations:
            first = sorted(dated_creations)[0]
            events.append((first, f"{_fmt_ts(first)} — Dataset first created"))

        # Lifecycle timestamps endpoint (dataset-level record dates).
        ts = self._timestamps if isinstance(self._timestamps, dict) else {}
        ts_created = str(ts.get("createTime") or "")
        if not dated_creations and ts_created:
            # No version dates at all — timestamps are the only source.
            events.append((ts_created, f"{_fmt_ts(ts_created)} — Dataset first created"))
        ts_published = str(ts.get("publicationTime") or "")
        if (
            ts_published
            and ts_published[:10] != ts_created[:10]
            and ts_published[:10] not in version_published_days
        ):
            # Only shown when it differs from creation (per curator request)
            # and no version event already covers that day.
            events.append((ts_published, f"{_fmt_ts(ts_published)} — Dataset first published"))
        ts_doi = str(ts.get("globalIdCreateTime") or "")
        if ts_doi:
            events.append((ts_doi, f"{_fmt_ts(ts_doi)} — DOI minted"))
        ts_touched = str(ts.get("lastUpdateTime") or "")
        if ts_touched:
            events.append((ts_touched, f"{_fmt_ts(ts_touched)} — Draft last updated"))

        # Review submissions (SUBMITTEDDS inbox notes, PID-matched).
        for sub in self._review_submissions if isinstance(self._review_submissions, list) else []:
            if not isinstance(sub, dict):
                continue
            when = str(sub.get("time") or "")
            dv = str(sub.get("dataverse") or "").strip()
            who = str(sub.get("requestor") or "").strip()
            text = f"Submitted for review{(' to be published in ' + dv) if dv else ''}{(' by ' + who) if who else ''}"
            if when:
                events.append((when, f"{_fmt_ts(when)} — {text}"))
            else:
                events.append(("0000", f"— {text}"))

        for h in ((self._curation or {}).get("history") or []):
            if not isinstance(h, dict):
                continue
            label = str(h.get("label") or "").strip()
            if not label:
                continue
            who = str(h.get("assigner") or "").strip()
            _add(h.get("time", ""), f"Curation label '{label}' assigned" + (f" by {who}" if who else ""))

        st = None
        try:
            st = self._state()
            actions = st.list_actions(self._pid, limit=50) if st is not None else []
        except Exception:
            actions = []
        finally:
            if st is not None:
                try:
                    st.close()
                except Exception:
                    pass
        _local_text = {
            "downloaded": "Dataset downloaded for curation",
            "checks_run": "Automated checks run",
            "checks_saved": "Checks report auto-saved",
            "decision": "Decision recorded",
            "exported": "Curation report exported",
            "response_exported": "Response draft exported",
        }
        for a in actions:
            act = a.get("action") or ""
            if act not in _local_text:
                continue
            notes = (a.get("notes") or "").strip()
            text = _local_text[act] + (f": {notes[:90]}" if notes else "")
            _add(a.get("timestamp", ""), text)

        # Embargo / retention dates from the file inventory (as applicable).
        for entry in self._inventory if isinstance(self._inventory, list) else []:
            if not isinstance(entry, dict):
                continue
            path = str(entry.get("path") or "").strip() or "(unnamed file)"
            embargo = str(entry.get("embargo_date") or "").strip()
            if embargo:
                _add(embargo, f"File '{path}' embargoed until {embargo[:10]}")
            retention = str(entry.get("retention") or "").strip()
            if retention:
                _add(retention, f"File '{path}' retention: {retention[:60]}")

        try:
            self._dataset_log.clear()
            if not events:
                self._dataset_log.addItem(
                    "No dataset history yet — load metadata from Dataverse for the full timeline."
                )
                return
            events.sort(key=lambda e: e[0], reverse=True)
            for _key, text in events[:100]:
                item = QListWidgetItem(text)
                item.setToolTip(text)
                self._dataset_log.addItem(item)
        except Exception:
            pass

    def _build_version_card(self) -> QFrame:
        """Version log: every version plus the published→draft diff."""
        card, _body_host, _title, header_lay = make_card("Version log")
        add_info_tip(
            header_lay,
            "Every published version plus the draft, with field-level changes "
            "and files added, removed or replaced between the previous version "
            "and the draft. A first submission shows “Initial draft”.",
            name="Version log",
        )
        # Flush card (manifest-tree pattern): dynamic children are edge to
        # edge and paint their own corners in _populate_version_diff.
        _body_host.setContentsMargins(0, 0, 0, 0)
        _body_host.setSpacing(0)
        # Named not-loaded state, never "—" (2026-10-02 P2).
        self._version_summary = QLabel("Not loaded yet")
        self._version_summary.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {ON_SURFACE_VARIANT}; background: transparent; border: none;")
        header_lay.addWidget(self._version_summary)
        self._version_reset_btn = AppButton("", kind="ghost", size="sm")
        self._version_reset_btn.setFixedSize(28, 28)
        self._version_reset_btn.setAccessibleName("Reset version log columns")
        try:
            from ui.icons import icon as _reset_icon2

            self._version_reset_btn.setIcon(_reset_icon2("rotate-ccw"))
        except Exception:
            self._version_reset_btn.setText("Reset")
        self._version_reset_btn.setToolTip("Reset columns, sort and widths to default")
        self._version_reset_btn.clicked.connect(self._on_reset_version_view)
        header_lay.addWidget(self._version_reset_btn)
        self._version_body = _body_host
        return card

    def _version_placeholder(self, text: str) -> None:
        wrap = QWidget()
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(16, 12, 16, 12)
        ph = QLabel(text)
        ph.setWordWrap(True)
        ph.setStyleSheet(f"font-size: 12px; color: {ON_SECONDARY_CONTAINER}; background: transparent; border: none;")
        lay.addWidget(ph)
        self._version_body.addWidget(wrap)

    @staticmethod
    def _short(value: str, limit: int = 150) -> str:
        s = (value or "").strip()
        return (s[:limit] + "…") if len(s) > limit else (s or "—")

    def _populate_version_diff(self) -> None:
        """Render the version list plus the published→draft diff."""
        from PySide6.QtWidgets import QListWidget, QListWidgetItem

        while self._version_body.count():
            item = self._version_body.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        diff = self._version_diff
        versions = self._versions if isinstance(self._versions, list) else []
        versions = [v for v in versions if isinstance(v, dict)]
        # Flush children in card order: corners are painted by position
        # (first: square top; last: 8px bottom; middle: square both).
        flush_widgets: list = []

        def _apply_flush_corners() -> None:
            for i, (w, kind) in enumerate(flush_widgets):
                last = i == len(flush_widgets) - 1
                try:
                    w.setStyleSheet(
                        flush_table_style(last=last)
                        if kind == "table"
                        else flush_list_style(last=last)
                    )
                except Exception:
                    pass

        def _version_line(v: dict) -> tuple[str, str]:
            num = v.get("number", "") or ""
            state = (v.get("state", "") or "").upper()
            ct, rt = v.get("create_time", ""), v.get("release_time", "")
            if state == "DRAFT":
                return f"Draft — created {ct[:10] or 'date unknown'} (current)", PRIMARY
            if state == "DEACCESSIONED":
                return f"v{num} — deaccessioned {(rt or ct)[:10] or 'date unknown'}", ERROR
            if rt:
                return f"v{num} — published {rt[:10]}", SUCCESS_DARK
            return f"v{num} — created {ct[:10] or 'date unknown'}", ON_SECONDARY_CONTAINER

        # Version list first (current + all previous)
        if versions:
            vlist = QListWidget()
            vlist.setMaximumHeight(min(150, 30 + 26 * len(versions)))
            enable_list_copy(vlist)
            for v in versions:
                text, color = _version_line(v)
                entry = QListWidgetItem(text)
                entry.setToolTip(text)
                entry.setForeground(QColor(color))
                vlist.addItem(entry)
            self._version_body.addWidget(vlist)
            flush_widgets.append((vlist, "list"))
        elif self._metadata is None:
            self._version_summary.setText("Not loaded yet")
            self._version_placeholder("Version comparison appears after loading metadata from Dataverse.")
            return
        else:
            # Metadata loaded but no version history came back: first version.
            initial = QListWidgetItem("Initial draft — no previous versions")
            initial.setToolTip("This looks like the dataset's first version")
            initial.setForeground(QColor(PRIMARY))
            vlist = QListWidget()
            vlist.setMaximumHeight(56)
            vlist.addItem(initial)
            self._version_body.addWidget(vlist)
            flush_widgets.append((vlist, "list"))

        n_versions = len(versions) if versions else 1
        if not diff:
            self._version_summary.setText(f"{n_versions} version(s)")
            _apply_flush_corners()
            return
        old_num = (diff.get("old") or {}).get("number") or "published"
        total = int(diff.get("total_changes") or 0)
        meta = diff.get("metadata_changes") or []
        terms = diff.get("terms_changes") or []
        self._version_summary.setText(f"{n_versions} version(s) · v{old_num} → Draft · {total} change(s)")
        if total == 0:
            self._version_placeholder(f"No changes since v{old_num} — the draft matches the published version.")
            return
        # Metadata + terms field changes
        rows = [(c.get("field", ""), c.get("block", ""), c.get("old", ""), c.get("new", "")) for c in meta]
        rows += [(f"Terms: {c.get('field', '')}", "Terms of Access", c.get("old", ""), c.get("new", "")) for c in terms]
        if rows:
            table = AppTable(
                ["Field", f"Previous (v{old_num})", "New (Draft)"],
                widths={0: 190, 1: 220, 2: 220},
                row_height=30,
            )
            table.setSortingEnabled(False)
            table.setRowCount(len(rows))
            self._track_table_widths("dataset_version", table.horizontalHeader())
            table.setMaximumHeight(260)
            for r, (field, block, old_v, new_v) in enumerate(rows):
                f_item = QTableWidgetItem(field)
                f_item.setToolTip(f"{block}\n\nField: {field}" if block else field)
                o_item = QTableWidgetItem(self._short(old_v))
                o_item.setToolTip(old_v or "—")
                n_item = QTableWidgetItem(self._short(new_v))
                n_item.setToolTip(new_v or "—")
                n_item.setForeground(QColor(PRIMARY))
                table.setItem(r, 0, f_item)
                table.setItem(r, 1, o_item)
                table.setItem(r, 2, n_item)
            table.setSortingEnabled(True)
            table.fit_columns_to_content()
            self._version_body.addWidget(table)
            flush_widgets.append((table, "table"))
        # File changes
        from PySide6.QtWidgets import QListWidget, QListWidgetItem

        def _fname(f: dict) -> str:
            path, name = (f.get("path") or "").strip(), (f.get("name") or "").strip()
            if path and name:
                return f"{path}/{name}"
            return name or path or "(unnamed file)"

        from ui.icons import icon as _ver_icon

        entries: list[tuple[str, str, str]] = []
        for f in diff.get("files_added") or []:
            entries.append((f"{_fname(f)} — added", SUCCESS_DARK, "plus"))
        for f in diff.get("files_removed") or []:
            entries.append((f"{_fname(f)} — removed", ERROR, "minus"))
        for pair in diff.get("files_replaced") or []:
            old_f, new_f = pair.get("old") or {}, pair.get("new") or {}
            entries.append(
                (f"{_fname(old_f)} → {_fname(new_f)} — replaced",
                 AMBER_700, "arrow-right-left")
            )
        for fc in diff.get("file_changes") or []:
            for ch in fc.get("changes") or []:
                entries.append(
                    (f"{fc.get('file', '')}: {ch.get('field', '')} changed",
                     PRIMARY, "pencil")
                )
        if entries:
            flist = QListWidget()
            flist.setMaximumHeight(min(140, 28 + 24 * len(entries)))
            for text, color, icon_name in entries:
                item = QListWidgetItem(text)
                item.setToolTip(text)
                item.setForeground(QColor(color))
                try:
                    item.setIcon(_ver_icon(icon_name, color=color))
                except Exception:
                    pass
                flist.addItem(item)
            self._version_body.addWidget(flist)
            flush_widgets.append((flist, "list"))
        _apply_flush_corners()

    def _build_file_manifest_card(self) -> QFrame:
        card, _body_unused, _title, header_lay = make_card("File Manifest")
        add_info_tip(
            header_lay,
            "Every file in this dataset — the staged download when available, "
            "otherwise the Dataverse inventory — grouped folder > file > check. "
            "Expand a file to see every check, passes included; hover a check "
            "for its full message and details. Open folder reveals the staged files.",
            name="File Manifest",
        )
        _body_unused.setContentsMargins(0, 0, 0, 0)
        _body_unused.setSpacing(0)
        self._open_folder_btn = AppButton("Open folder", kind="secondary", size="md")
        self._open_folder_btn.setStyleSheet(action_button_style(False))
        self._open_folder_btn.setToolTip("Open the staged download folder in the file explorer")
        self._open_folder_btn.clicked.connect(self._on_open_folder)
        header_lay.addWidget(self._open_folder_btn)
        # Expand/Collapse all toggle for the folder > file > check tree.
        self._expand_btn = AppButton("Expand all", kind="secondary", size="md")
        self._expand_btn.setStyleSheet(action_button_style(False))
        self._expand_btn.setToolTip("Expand or collapse every folder and file in the manifest")
        self._expand_btn.clicked.connect(self._on_toggle_expand_all)
        header_lay.addWidget(self._expand_btn)
        self._file_filter = make_search_field("Filter files...", height=36, min_width=180)
        self._file_filter.textChanged.connect(self._on_file_filter)
        header_lay.addWidget(self._file_filter)
        self._scan_filter = make_combo(
            [(label, key) for label, key in [
                ("All statuses", "all"), ("Issues", "issues"),
                ("Errors", "errors"), ("Warnings", "warnings"),
                ("Skipped", "skipped"), ("Clean", "clean"),
                ("No check", "unchecked"),
            ]],
            height=36,
            min_width=130,
        )
        self._scan_filter.currentIndexChanged.connect(lambda _i: self._apply_file_filter_internal())
        header_lay.addWidget(self._scan_filter)
        # Reset columns button — restores default widths/order
        self._file_reset_btn = AppButton("", kind="ghost", size="sm")
        self._file_reset_btn.setFixedSize(28, 28)
        self._file_reset_btn.setAccessibleName("Reset file manifest columns")
        try:
            from ui.icons import icon as _reset_icon
            self._file_reset_btn.setIcon(_reset_icon("rotate-ccw"))
        except Exception:
            self._file_reset_btn.setText("Reset")
        self._file_reset_btn.setToolTip("Reset column widths and order to defaults")
        self._file_reset_btn.clicked.connect(self._on_reset_file_view)
        header_lay.addWidget(self._file_reset_btn)
        lay = QVBoxLayout()
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        # NOTE: tree + footer live in a flush sub-layout so the header keeps
        # its top radius and the footer keeps its bottom radius.
        card.layout().addLayout(lay)

        # Tree: folder > file > check hierarchy (Carbon-inspired, native QTreeView).
        # Column 0 carries the tree (caret + indent + icons); Size/Format/Scan
        # mirror the old table columns. Check nodes show the full untruncated
        # message; details live in the tooltip.
        from PySide6.QtWidgets import QTreeView

        self._file_tree = QTreeView()
        self._file_tree.setHeaderHidden(False)
        self._file_tree.setUniformRowHeights(False)
        self._file_tree.setExpandsOnDoubleClick(True)
        self._file_tree.setAnimated(True)
        self._file_tree.setIndentation(18)
        # Lucide chevron branch images (expand affordance); folder
        # icons track open/closed via _sync_tree_carets.
        from ui.icons import tree_branch_qss as _branch_qss

        # Header: square top-left corner to meet the card's top bar flush;
        # scrollbar lanes transparent so the vertical scrollbar starts below
        # the header (no overlap). Thumbs/grooves come from the global theme.
        self._file_tree.setStyleSheet(
            f"QTreeView {{ background: {SURFACE_CONTAINER_LOWEST}; border: none; font-size: 12px; color: {ON_SURFACE}; }}"
            "QTreeView::item { height: 30px; border: none; }"
            f"QTreeView::item:hover {{ background: {SURFACE_CONTAINER_LOW}; }}"
            f"QTreeView::item:selected {{ background: {SURFACE_CONTAINER}; color: {ON_SURFACE}; }}"
            "QHeaderView::section:first { border-top-left-radius: 0px; }"
            "QHeaderView::section:last { border-top-right-radius: 0px; border-right: none; }"
            f"QHeaderView::section {{ background: {SURFACE_CONTAINER}; }}"
            "QTreeView QScrollBar:vertical { background: transparent; }"
            "QTreeView QScrollBar:horizontal { background: transparent; }"
            + _branch_qss()
        )
        self._file_tree.clicked.connect(self._on_tree_clicked)
        self._file_tree.expanded.connect(lambda _i: (self._sync_tree_carets(), self._update_expand_btn()))
        self._file_tree.collapsed.connect(lambda _i: (self._sync_tree_carets(), self._update_expand_btn()))
        lay.addWidget(self._file_tree, 1)
        # Compat alias: old code paths referenced _file_table; keep a None
        # placeholder so stray attribute access fails loudly, not silently.
        self._file_table = None

        # Footer: showing X of Y + total size
        footer = QFrame()
        footer.setStyleSheet(f"QFrame {{ background: {BACKGROUND}; border-top: 1px solid {SURFACE_CONTAINER_LOW}; border-bottom-left-radius: 8px; border-bottom-right-radius: 8px; }}")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(16, 10, 16, 10)
        self._file_footer_left = QLabel("No files yet")
        self._file_footer_left.setStyleSheet(f"font-size: 12px; color: {ON_SURFACE_VARIANT}; background: transparent; border: none;")
        fl.addWidget(self._file_footer_left)
        fl.addStretch()
        self._file_footer_right = QLabel("")
        self._file_footer_right.setStyleSheet(f"font-size: 12px; color: {ON_SURFACE_VARIANT}; background: transparent; border: none;")
        fl.addWidget(self._file_footer_right)
        lay.addWidget(footer)

        # Hidden checks list for compatibility (was QListWidget; now we show inline)
        # Keep _file_checks as simple list for optional advanced view
        self._file_checks_data: dict[str, list] = {}
        return card

    # ---- Helpers ----
    def _set_status(self, msg: str) -> None:
        self._status.setText(msg)
        self._status.setVisible(bool(msg))

    def _update_header_link(self, metadata: dict | None = None) -> None:
        # Defensive: runs mid-__init__ before all header widgets exist, and
        # again on every metadata load (cached metadata makes `meta` truthy
        # on the very first call — see the reopen crash this guards).
        meta = metadata if metadata is not None else self._metadata
        version_state = ""
        if isinstance(meta, dict):
            latest = meta.get("latestVersion") or {}
            version_state = (latest.get("versionState") or "").upper()
        # Badge (words match the dashboard status column; color is per
        # label via label_badge_style, DOI-badge chrome)
        _pill_name, pill_text = _pill_state(version_state, getattr(self, "_in_review", False))
        status_pill = getattr(self, "_status_pill", None)
        if status_pill is not None:
            status_pill.setText(pill_text.upper())
            status_pill.setStyleSheet(label_badge_style(pill_text))
        # Contact/date
        if meta and isinstance(meta, dict):
            latest = meta.get("latestVersion") or {}
            blocks = latest.get("metadataBlocks") or {}
            cite = blocks.get("citation", {}) if isinstance(blocks, dict) else {}
            fields = cite.get("fields", []) if isinstance(cite, dict) else []
            depositor = ""
            for f in fields:
                if f.get("typeName") == "datasetContact":
                    v = f.get("value", [])
                    if isinstance(v, list) and v:
                        first = v[0]
                        name = first.get("datasetContactName", {}).get("value", "") if isinstance(first.get("datasetContactName"), dict) else ""
                        depositor = name or "—"
                    break
            # Prefer the real Dataverse title when metadata arrives (TopNav chips use it)
            try:
                from dataverse_client import extract_title
                real_title = extract_title(latest) if isinstance(latest, dict) else ""
                if real_title and real_title != self._title:
                    self._title = real_title
                    try:
                        self.titleChanged.emit(self._pid, self._title)
                    except Exception:
                        pass
            except Exception:
                pass
            depositor_lbl = getattr(self, "_depositor_lbl", None)
            if depositor_lbl is None:
                return
            depositor_lbl.setText(f"Submitted by {depositor}" if depositor else f"{self._pid}")
            date = (latest.get("createTime") or latest.get("lastUpdateTime") or "")[:10]
            if date:
                depositor_lbl.setText(depositor_lbl.text() + f"  •  {date}")
        url = f"{self._config.dataverse.base_url}/dataset.xhtml?persistentId={self._pid}" + ("&version=DRAFT" if version_state == "DRAFT" else "")
        header_link = getattr(self, "_header_link", None)
        if header_link is not None:
            header_link.setText(f"<a href='{url}' style='color:{PRIMARY}; text-decoration:none;'>Open in Dataverse{' — DRAFT' if version_state=='DRAFT' else ''} ↗</a>")
        title_lbl = getattr(self, "_title_lbl", None)
        if title_lbl is not None:
            title_lbl.setText(self._title)

    def _update_curation_pill(self) -> None:
        """Show the Dataverse curation label (if any) next to the status pill."""
        label = ""
        tip = "Curation label assigned in Dataverse"
        try:
            label = str((self._curation or {}).get("label") or "").strip()
            when = str((self._curation or {}).get("time") or "")[:16].replace("T", " ")
            who = str((self._curation or {}).get("assigner") or "").strip()
            if label and (when or who):
                tip = f"{label}\nSet {when} by {who}".strip()
        except Exception:
            label = ""
        try:
            if label:
                self._curation_pill.setText(label.upper())
                self._curation_pill.setToolTip(tip)
                self._curation_pill.setStyleSheet(label_badge_style(label))
                self._curation_pill.setVisible(True)
            else:
                self._curation_pill.setVisible(False)
        except Exception:
            pass

    def _refresh_curation_preview(self) -> None:
        """Populate Dataset-checks card: dataset-level results + summary.

        Per-file results live in the File Manifest tree (folder > file >
        check) to avoid duplicating 80+ rows here. This card shows dataset
        checks (inventory.*) with full messages, plus aggregate counts.
        """
        try:
            from engine.runner import list_planned_checks
            from engine.status import summarize
            staged = self._dl_mgr.files_dir(self._pid)
            if staged.exists():
                files = sorted(p for p in staged.rglob("*") if p.is_file())
            elif self._inventory:
                files = [Path(e.get("path", "")) for e in self._inventory]
            else:
                files = []
            planned = list_planned_checks(files)
            # Clear existing rows; the header summary is updated below.
            for i in reversed(range(self._auto_body.count())):
                item = self._auto_body.takeAt(i)
                w = item.widget() if item is not None else None
                if w is not None:
                    w.deleteLater()
            if not files:
                if self._inventory is not None and len(self._inventory) == 0 and self._metadata is not None:
                    ph = QLabel("This dataset contains no files in Dataverse — file checks do not apply. Metadata checks above still apply.")
                    # A measured zero, not a placeholder — name it (2026-10-02 P2).
                    self._auto_summary.setText("No file checks")
                else:
                    ph = QLabel("No file list yet — load metadata to see which checks will run.")
                    self._auto_summary.setText("Not run yet")
                ph.setWordWrap(True)
                ph.setStyleSheet(f"font-size: 12px; color: {ON_SECONDARY_CONTAINER}; background: transparent; border: none;")
                self._auto_body.addWidget(ph)
                return
            # Count will_run
            will = sum(1 for p in planned if p.get("will_run"))
            if self._report is not None:
                # Dataset-level results with FULL messages (no truncation);
                # per-file results are in the manifest tree.
                all_results = list(self._report.dataset_checks) + [
                    c for f in self._report.files for c in f.checks
                ]
                summary = summarize(all_results)
                self._auto_summary.setText(
                    f"{summary['passed']} passed · {summary['failed-warning']} warn · "
                    f"{summary['failed-error']} errors · {summary['skipped']} skipped"
                )
                for c in self._report.dataset_checks:
                    row = self._auto_row(c.check_id, c.message, c.passed, c.level)
                    try:
                        from ui.checks_tree import format_details_tooltip

                        row.setToolTip(format_details_tooltip(c))
                    except Exception:
                        pass
                    self._auto_body.addWidget(row)
                # Every per-file finding also surfaces here (not just
                # inventory.*): failed checks with their file path, and
                # skipped checks (missing library) that did not run.
                # Passes stay in the manifest tree only — they are the
                # bulk and the tree shows them per file.
                from engine.status import classify

                file_findings = [
                    (f, c)
                    for f in self._report.files
                    for c in f.checks
                    if classify(c) in ("failed-error", "failed-warning", "skipped")
                ]
                for f, c in file_findings:
                    kind = classify(c)
                    desc = f"{f.path} — {c.message}"
                    if kind == "skipped":
                        row = self._auto_row(c.check_id, desc, True, "warning", badge="SKIPPED")
                    else:
                        row = self._auto_row(c.check_id, desc, c.passed, c.level)
                    try:
                        from ui.checks_tree import format_details_tooltip

                        row.setToolTip(format_details_tooltip(c))
                    except Exception:
                        pass
                    self._auto_body.addWidget(row)
                if (
                    not self._report.dataset_checks
                    and not file_findings
                    and not any(f.checks for f in self._report.files)
                ):
                    ok = QLabel("All checks passed — no findings.")
                    ok.setStyleSheet(f"font-size: 12px; color: {PRIMARY}; background: transparent; border: none;")
                    self._auto_body.addWidget(ok)
            else:
                # Only checks that will actually run for this dataset's
                # files (checks with no matching files are not listed).
                self._auto_summary.setText(f"{will} check(s) will run")
                if not will:
                    ph = QLabel("No automated checks match the files in this dataset.")
                    ph.setWordWrap(True)
                    ph.setStyleSheet(f"font-size: 12px; color: {ON_SECONDARY_CONTAINER}; background: transparent; border: none;")
                    self._auto_body.addWidget(ph)
                for p in planned:
                    if not p.get("will_run"):
                        continue
                    # lib_map check
                    lib_map = {
                        "format.spss": "pyreadstat", "format.stata": "pyreadstat", "format.sas": "pyreadstat",
                        "format.netcdf": "netCDF4", "format.hdf5": "h5py", "format.tiff": "tifffile",
                        "format.images": "Pillow", "format.pdf": "pypdf", "format.xml": "lxml", "format.xlsx": "openpyxl",
                    }
                    pip_pkg = lib_map.get(p["check_id"], "")
                    missing = ""
                    if pip_pkg:
                        try:
                            __import__(pip_pkg if pip_pkg != "Pillow" else "PIL")
                        except ImportError:
                            missing = f"Missing: pip install {pip_pkg}"
                    status = missing or "Will run"
                    # Interpret for row styling: missing = warn, else pass tone
                    if missing:
                        row = self._auto_row(p["check_id"], p["description"], False, "warning", badge="MISSING")
                    else:
                        row = self._auto_row(p["check_id"], p["description"], True, "info", badge="PASS")
                    # Add subtitle with file_types + status
                    row.setToolTip(f"{p['description']}\n\n{status}")
                    self._auto_body.addWidget(row)
        except Exception:
            pass
        try:
            selectable_labels(self._auto_card)
        except Exception:
            pass

    def _auto_row(self, check_id: str, desc: str, passed: bool, level: str, badge: str | None = None) -> QFrame:
        frame = QFrame()
        # Explicit SKIPPED (warning+passed with "Missing"/"skipped" wording)
        # renders grey so it is never confused with a real pass.
        from ui.icons import icon_label as _icon_label

        if passed and level == "warning" and (
            (badge or "").upper() in ("SKIPPED", "MISSING")
            or "skipped" in (badge or desc).lower()
            or "not executed" in desc.lower()
            or "Missing" in (badge or desc)
        ):
            frame.setStyleSheet(f"QFrame {{ background: {SURFACE_CONTAINER_LOW}; border: 1px solid {OUTLINE_VARIANT}; border-radius: 8px; }}")
            icon_name, icon_color = "circle-dashed", ON_SURFACE_VARIANT
            badge_text = "SKIPPED" if "SKIP" in (badge or "").upper() or "skipped" in desc.lower() else (badge or "WARN")
            badge_bg = SURFACE_VARIANT
            badge_fg = ON_SURFACE_VARIANT
        elif not passed and level in ("error", "warning"):
            frame.setStyleSheet(f"QFrame {{ background: {ERROR_CONTAINER}; border: 1px solid {ERROR_OUTLINE}; border-radius: 8px; }}")
            icon_name, icon_color = (
                ("octagon-x", ERROR) if level == "error"
                else ("octagon-alert", WARNING)
            )
            badge_text = badge or "FAIL"
            badge_bg = ERROR_CONTAINER
            badge_fg = ON_ERROR_CONTAINER
        elif passed and level == "warning" and "Missing" in (badge or desc):
            frame.setStyleSheet(f"QFrame {{ background: {ERROR_SURFACE}; border: 1px solid {ERROR_OUTLINE}; border-radius: 8px; }}")
            icon_name, icon_color = "octagon-alert", WARNING
            badge_text = badge or "WARN"
            badge_bg = ERROR_CONTAINER
            badge_fg = ON_ERROR_CONTAINER
        elif passed:
            frame.setStyleSheet(f"QFrame {{ background: {SURFACE_CONTAINER}; border: 1px solid {OUTLINE_VARIANT}; border-radius: 8px; }}")
            icon_name, icon_color = "check", PRIMARY
            badge_text = badge or "PASS"
            badge_bg = PRIMARY
            badge_fg = ON_PRIMARY
        else:
            frame.setStyleSheet(f"QFrame {{ background: {SURFACE_CONTAINER}; border: 1px solid {OUTLINE_VARIANT}; border-radius: 8px; }}")
            icon_name, icon_color = "minus", ON_SURFACE_VARIANT
            badge_text = badge or "—"
            badge_bg = SURFACE_VARIANT
            badge_fg = ON_SURFACE_VARIANT
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(8)
        lay.addWidget(_icon_label(icon_name, size=16, color=icon_color))
        txt = QVBoxLayout()
        txt.setSpacing(1)
        cid = QLabel(check_id)
        cid.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {ON_SURFACE}; background: transparent; border: none;")
        txt.addWidget(cid)
        d = QLabel(desc)
        d.setWordWrap(True)
        d.setStyleSheet(f"font-size: 11px; color: {ON_SURFACE_VARIANT}; background: transparent; border: none;")
        txt.addWidget(d)
        lay.addLayout(txt, 1)
        badge_lbl = QLabel(badge_text)
        badge_lbl.setAlignment(Qt.AlignCenter)
        badge_lbl.setFixedHeight(20)
        badge_lbl.setMinimumWidth(56)
        badge_lbl.setStyleSheet(f"QLabel {{ background: {badge_bg}; color: {badge_fg}; border: 1px solid {OUTLINE_VARIANT}; border-radius: 8px; font-size: 10px; font-weight: 700; padding: 0 6px; }}")
        lay.addWidget(badge_lbl)
        return frame

    def _refresh_files_placeholder(self) -> None:
        # Note: Run checks / Export stay enabled at all times — without
        # staged files or a report they explain themselves via dialogs.
        # Prefer the inventory view whenever we have one: canonical
        # Dataverse paths plus a per-file staged checkmark. The raw staged
        # listing is only a fallback when no inventory was ever loaded
        # (its basenames can differ from directoryLabel paths).
        staged = self._dl_mgr.files_dir(self._pid)
        if self._inventory:
            self._populate_from_inventory()
            try:
                n_staged = sum(1 for _r in getattr(self, "_all_file_rows", []) if self._is_staged(_r[0]))
                if staged.exists():
                    self._set_status(
                        f"Inventory: {len(self._all_file_rows)} file(s), {n_staged} staged locally in {staged}"
                    )
            except Exception:
                pass
        elif staged.exists():
            files = sorted(p for p in staged.rglob("*") if p.is_file())
            self._populate_file_table_staged(files)
            self._set_status(f"Staged: {len(files)} file(s) in {staged}")
        else:
            from ui.checks_tree import build_tree_model

            self._file_tree.setModel(build_tree_model([], None))
            self._file_footer_left.setText("No files yet — load metadata to see the Dataverse file list.")
            self._file_footer_right.setText("")
        self._refresh_curation_preview()

    def _populate_file_table_staged(self, files: list[Path]) -> None:
        import mimetypes

        self._all_file_rows = []
        for path in files:
            try:
                rel = path.relative_to(self._dl_mgr.files_dir(self._pid)).as_posix() if path.is_relative_to(self._dl_mgr.files_dir(self._pid)) else path.name
            except (ValueError, OSError):
                rel = path.name
            mime = mimetypes.guess_type(path.name)[0] or ""
            try:
                size = path.stat().st_size
            except OSError:
                continue
            ext = Path(rel).suffix.lower().lstrip(".").upper() or mime.split("/")[-1].upper() or "FILE"
            self._all_file_rows.append((rel, size, ext, rel))
        self._staged_files = files
        self._apply_file_filter_internal()
        # Staged fallback: every listed file is on disk by construction.
        # Header grammar: major actions are text-only in every state —
        # "Downloaded (N)" already carries the meaning (2026-10-02 minor).
        try:
            self._dl_btn.setText(f"Downloaded ({len(files)})")
            self._dl_btn.setToolTip("All staged files are on disk — clicking verifies instead of re-downloading")
        except Exception:
            pass

    def _populate_from_inventory(self) -> None:
        self._all_file_rows: list[tuple[str, int, str, str]] = []
        total = 0
        for e in self._inventory if isinstance(self._inventory, list) else []:
            if not isinstance(e, dict):
                continue
            inv_path = str(e.get("path", "") or "")
            if not inv_path:
                continue
            display, size, fmt = _manifest_display_for_entry(e)
            total += size
            # Row 4th element keeps the inventory (.tab) path so tooltips can
            # name the server derivative behind a displayed original.
            self._all_file_rows.append((display, size, fmt, inv_path))
        self._apply_file_filter_internal()

    def _set_file_row(self, row: int, path: str, size: int, fmt: str, scan: str, downloaded: bool = False) -> None:
        # Legacy table API removed with the tree view; kept as a no-op guard
        # so any external callers fail gracefully during migration.
        return None

    def _is_staged(self, path: str) -> bool:
        """Check whether the inventory path is staged locally.

        Checks the exact directoryLabel path first, then falls back to a
        basename match anywhere under files_dir: server bundles have not
        always preserved subfolders, and without the fallback every file
        reads as "not downloaded" (and Download All re-prompts forever).
        Uses a cached name set (no per-row tree walk, glob-safe).
        """
        try:
            root = self._dl_mgr.files_dir(self._pid)
            if not path:
                return False
            try:
                direct = self._dl_mgr._contained(root, path)
            except Exception:
                direct = None
            try:
                if direct is not None and direct.is_file():
                    return True
            except OSError:
                pass
            base = Path(path).name
            if not base:
                return False
            # Cached staged-name set built by _refresh_download_state /
            # _populate_* (avoids O(files × walk) rglob(base) which also
            # misbehaves on names with *?[] glob chars).
            cached = getattr(self, "_staged_names_cache", None)
            if isinstance(cached, set):
                return base in cached
            try:
                if not root.exists():
                    return False
                for candidate in root.rglob("*"):
                    try:
                        if candidate.is_file() and candidate.name == base:
                            return True
                    except OSError:
                        continue
            except OSError:
                return False
            return False
        except Exception:
            return False

    def _refresh_download_state(self) -> None:
        """Reflect staged state on the Download button so it never surprises.

        Fully-staged inventories read "Downloaded (N)" with a check icon
        and a tooltip saying the approval dialog will be skipped; partial
        stages show "Download All (k/N staged)". No inventory → plain
        "Download All".
        """
        try:
            btn = getattr(self, "_dl_btn", None)
            if btn is None:
                return
            rows = getattr(self, "_all_file_rows", []) or []
            if not rows:
                btn.setText("Download All")
                btn.setToolTip("Download the dataset bundle for local checks")
                return
            root = self._dl_mgr.files_dir(self._pid)
            staged_paths: set[str] = set()
            staged_names: set[str] = set()
            try:
                if root.exists():
                    for p in root.rglob("*"):
                        try:
                            if p.is_file():
                                staged_names.add(p.name)
                                try:
                                    staged_paths.add(p.relative_to(root).as_posix())
                                except (ValueError, OSError):
                                    pass
                        except OSError:
                            continue
            except OSError:
                pass
            # Cache for _is_staged fast path (avoids per-row walks).
            try:
                self._staged_names_cache = set(staged_names)
                self._staged_paths_cache = set(staged_paths)
            except Exception:
                pass
            n_staged = sum(
                1 for (path, _s, _f, _o) in rows
                if (path in staged_paths) or (Path(path).name in staged_names)
            )
            total = len(rows)
            # Header grammar: text-only major action in every state; the
            # count in the label ("Downloaded (N)") is the status cue.
            if total and n_staged >= total:
                btn.setText(f"Downloaded ({total})")
                btn.setToolTip(
                    "All files are already staged locally — clicking verifies "
                    "and skips the download instead of re-prompting"
                )
            elif n_staged:
                btn.setText(f"Download All ({n_staged}/{total} staged)")
                btn.setToolTip(
                    f"{n_staged} of {total} file(s) already staged — "
                    "only missing files will be fetched after approval"
                )
            else:
                btn.setText("Download All")
                btn.setToolTip("Download the dataset bundle for local checks")
        except Exception:
            pass

    def _on_open_folder(self) -> None:
        """Open the staged download folder in the desktop file explorer."""
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        staged = self._dl_mgr.files_dir(self._pid)
        target = staged if staged.exists() else self._dl_mgr.dataset_dir(self._pid)
        if not target.exists():
            show_info(self, "Open folder", "Nothing downloaded yet — download the dataset first.")
            return
        try:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target.resolve())))
        except Exception as exc:
            show_warning(self, "Open folder", f"Could not open {target}:\n{exc}")

    def _on_file_filter(self, text: str) -> None:
        self._apply_file_filter_internal()

    def _apply_file_filter_internal(self) -> None:
        from engine.status import classify
        from ui.checks_tree import build_tree_model, matches_status_filter

        filt = (self._file_filter.text() or "").lower().strip()
        try:
            status_filt = self._scan_filter.currentData() or "all"
        except Exception:
            status_filt = "all"
        all_rows = list(getattr(self, "_all_file_rows", []))
        by_path = {}
        if self._report is not None:
            by_path = {f.path: f for f in self._report.files}

        def _row_badges(path: str) -> list[str]:
            entry = by_path.get(path)
            if not entry or not entry.checks:
                return []
            return [classify(c) for c in entry.checks]

        def _scan_text(path: str) -> str:
            entry = by_path.get(path)
            if self._report is None:
                return ""
            if entry is None:
                return "Not in report"
            if not entry.checks:
                return "No automated check"
            from engine.status import status_label

            return status_label(entry.checks)

        rows = []
        for r in all_rows:
            path = r[0]
            if filt and filt not in path.lower():
                # Keep a file if one of its check messages matches.
                entry = by_path.get(path)
                hay = " ".join(
                    (c.check_id + " " + c.message).lower()
                    for c in (entry.checks if entry else [])
                )
                if filt not in hay:
                    continue
            if not matches_status_filter(_scan_text(path), _row_badges(path), status_filt):
                continue
            rows.append(r)
        model = build_tree_model(
            rows,
            self._report,
            self._is_staged,
            _human_size,
            inventory=self._inventory if isinstance(self._inventory, list) else None,
        )
        # The header's signals are blocked while the tree is rebuilt and
        # the columns are fitted to their content: sectionResized persists
        # the layout, so an auto-fit would overwrite the widths the user
        # saved before the restore below can apply them.
        _hdr = self._file_tree.header()
        try:
            _hdr.blockSignals(True)
        except Exception:
            _hdr = None
        try:
            self._file_tree.setModel(model)
            self._file_tree.expandToDepth(0)
            # Auto-expand files with issues so findings are visible.
            for r in range(model.rowCount()):
                folder = model.item(r, 0)
                if folder is not None and folder.hasChildren():
                    for i in range(folder.rowCount()):
                        scan = folder.child(i, 3).text() if folder.child(i, 3) else ""
                        if scan.startswith(("Error", "Warning")):
                            idx = model.index(i, 0, model.index(r, 0))
                            self._file_tree.expand(idx)
                else:
                    scan = model.item(r, 3).text() if model.item(r, 3) else ""
                    if scan.startswith(("Error", "Warning")):
                        self._file_tree.expand(model.index(r, 0))
            self._file_tree.resizeColumnToContents(0)
            # Give Size/Format/Scan real width too (defaults truncate long
            # formats like application/x-spss-sav and ingest notes).
            for _c in (1, 2, 3):
                try:
                    self._file_tree.resizeColumnToContents(_c)
                except Exception:
                    pass
            try:
                self._file_tree.setColumnWidth(
                    0, max(self._file_tree.columnWidth(0), 260)
                )
            except Exception:
                pass
            self._sync_tree_carets()
        except Exception:
            pass
        finally:
            if _hdr is not None:
                try:
                    _hdr.blockSignals(False)
                except Exception:
                    pass
        total = sum(r[1] for r in all_rows)
        self._file_footer_left.setText(f"Showing {len(rows)} of {len(all_rows)} files")
        self._file_footer_right.setText(f"Total Size: {_human_size(total)}" if total else "")
        self._refresh_download_state()
        self._update_expand_btn()
        # Track header widths/order for persistence and reset button
        self._track_table_widths("dataset_files", self._file_tree.header())

    def _sync_tree_carets(self) -> None:
        """Re-sync folder icons with the manifest tree's expanded state."""
        try:
            from ui.checks_tree import update_carets

            model = self._file_tree.model()
            if model is not None:
                update_carets(model, self._file_tree.isExpanded)
        except Exception:
            pass

    def _tree_has_collapsed(self) -> bool:
        """Check whether any expandable manifest node is currently collapsed."""
        try:
            model = self._file_tree.model()
            if model is None or model.rowCount() == 0:
                return False
            stack = [self._file_tree.rootIndex()]
            while stack:
                parent = stack.pop()
                for r in range(model.rowCount(parent)):
                    idx = model.index(r, 0, parent)
                    if model.hasChildren(idx):
                        if not self._file_tree.isExpanded(idx):
                            return True
                        stack.append(idx)
            return False
        except Exception:
            return False

    def _update_expand_btn(self) -> None:
        """Keep the toggle label in sync with the tree's real state."""
        try:
            self._expand_btn.setText(
                "Collapse all" if not self._tree_has_collapsed() else "Expand all"
            )
        except Exception:
            pass

    def _on_toggle_expand_all(self) -> None:
        """Expand every node when any is collapsed; otherwise collapse all."""
        try:
            if self._tree_has_collapsed():
                self._file_tree.expandAll()
            else:
                self._file_tree.collapseAll()
            self._sync_tree_carets()
            self._update_expand_btn()
        except Exception:
            pass

    def take_running_workers(self) -> list:
        """QThreads still running (for the owner to adopt before teardown)."""
        out = []
        for attr in ("_meta_worker", "_dl_worker", "_check_worker"):
            try:
                worker = getattr(self, attr, None)
                if worker is not None and worker.isRunning():
                    out.append(worker)
            except Exception:
                continue
        return out

    # -- progress ring -----------------------------------------------------
    def _on_ring_fraction(self, fraction: float) -> None:
        """Drive the circular progress ring (download / checks)."""
        try:
            self._ring.show()
            self._ring.setFraction(fraction)
            self._ring.setAccessibleDescription(self._ring.accessibleDescription())
        except Exception:
            pass

    def _hide_ring(self) -> None:
        """Hide the ring when the work it tracks is done."""
        try:
            self._ring.hide()
        except Exception:
            pass

    # -- metadata loading -------------------------------------------------
    def _on_load_metadata(self) -> None:
        if self._meta_worker is not None and self._meta_worker.isRunning():
            self._set_status("Metadata load already running — please wait…")
            return
        self._load_meta_btn.setEnabled(False)
        self._set_status("Loading metadata from Dataverse…")
        self._progress.setVisible(True)
        self._progress.setRange(0, 0)
        try:
            _collection = (
                getattr(self._config.dataverse, "collection", "")
                or getattr(self._config.dataverse, "subtree", "")
                or ""
            )
        except Exception:
            _collection = ""
        self._meta_worker = MetadataWorker(self._config.dataverse.base_url, self._config.dataverse.api_token, self._pid, self, collection=_collection)
        self._meta_worker.finished.connect(self._on_metadata_finished)
        self._meta_worker.error.connect(self._on_metadata_error)
        self._meta_worker.finished.connect(self._meta_worker.deleteLater)
        self._meta_worker.error.connect(self._meta_worker.deleteLater)
        self._meta_worker.start()

    def _on_metadata_finished(self, metadata: dict, inventory: list[dict], curation: dict | None = None, version_diff: dict | None = None, extra: dict | None = None) -> None:
        self._progress.setVisible(False)
        self._load_meta_btn.setEnabled(True)
        self._inventory = inventory if isinstance(inventory, list) else []
        self._metadata = metadata
        self._curation = curation if isinstance(curation, dict) else {}
        self._version_diff = version_diff if isinstance(version_diff, dict) else {}
        extra = extra if isinstance(extra, dict) else {}
        guestbook = extra.get("guestbook")
        self._guestbook = guestbook if isinstance(guestbook, dict) else None
        account = extra.get("account")
        self._account = account if isinstance(account, dict) else {}
        self._versions = extra.get("versions") if isinstance(extra.get("versions"), list) else []
        self._timestamps = extra.get("timestamps") if isinstance(extra.get("timestamps"), dict) else {}
        self._review_submissions = extra.get("review_submissions") if isinstance(extra.get("review_submissions"), list) else []
        self._in_review = bool(extra.get("in_review", False))
        self._update_header_link(metadata)
        self._update_curation_pill()
        self._populate_version_diff()
        self._refresh_decision_options()
        self._raw_view.setPlainText(_format_metadata(metadata))
        self._populate_completeness(metadata)
        self.metadataLoaded.emit(self._pid, metadata, self._inventory)
        self._refresh_curation_preview()
        self._refresh_dataset_log()
        inv_failed = bool(extra.get("inventory_failed", False))
        if not inv_failed:
            try:
                from storage import write_size_entry

                write_size_entry(
                    self._config.app.workspace,
                    self._pid,
                    sum(int(f.get("size_bytes", 0) or 0) for f in self._inventory),
                    len(self._inventory),
                )
            except Exception:
                pass
            # Persist metadata + manifest beside the downloads for next launch.
            # Skipped on inventory failure so a good cache is never clobbered.
            try:
                self._dl_mgr.save_metadata(self._pid, metadata, self._inventory)
            except Exception:
                pass
        self._log_action(
            "metadata_loaded" if not inv_failed else "metadata_failed",
            f"{len(self._inventory)} file(s) in inventory" if not inv_failed else "file list failed to load",
            {"file_count": len(self._inventory)},
        )
        if inv_failed:
            # Network/auth failure is not an empty dataset — say so plainly
            # and offer the retry instead of implying zero files.
            from ui.checks_tree import build_tree_model as _btm

            self._set_status("Could not load the file list (network or auth error) — metadata above may be partial. Check the log, then press Load metadata to retry.")
            self._file_tree.setModel(_btm([], None))
            self._all_file_rows = []
            self._file_footer_left.setText("File list failed to load — retry with Load metadata.")
            self._file_footer_right.setText("")
        elif self._inventory:
            self._populate_from_inventory()
            self._set_status(f"Metadata loaded — {len(self._inventory)} file(s) in inventory. Download to stage, then Run checks.")
        else:
            # Metadata loaded fine but the version genuinely has zero files —
            # say so plainly instead of implying a fetch failure.
            version_state = ""
            try:
                version_state = ((metadata.get("latestVersion") or {}).get("versionState") or "").upper()
            except Exception:
                pass
            ver_note = f" ({version_state.title()} version)" if version_state else ""
            self._set_status(f"This dataset contains no files in Dataverse{ver_note} — metadata checks above still apply.")
            from ui.checks_tree import build_tree_model as _btm2

            self._file_tree.setModel(_btm2([], None))
            self._all_file_rows = []
            self._file_footer_left.setText("This dataset contains no files.")
            self._file_footer_right.setText("")

    def _on_profile_changed(self) -> None:
        key = self._profile_combo.currentData()
        if isinstance(key, str):
            self._profile = key
        if self._metadata is not None:
            self._populate_completeness(self._metadata)

    def _on_reset_meta_view(self) -> None:
        try:
            self._reset_table_view(
                "dataset_meta", self._meta_check_table.horizontalHeader()
            )
            if self._metadata is not None:
                self._populate_completeness(self._metadata)
        except Exception:
            pass

    def _on_reset_version_view(self) -> None:
        try:
            from PySide6.QtWidgets import QTableWidget

            table = self._version_body.findChild(QTableWidget)
            if table is not None:
                self._reset_table_view(
                    "dataset_version", table.horizontalHeader()
                )
            self._populate_version_diff()
        except Exception:
            pass

    def _on_reset_file_view(self) -> None:
        try:
            self._reset_table_view("dataset_files", self._file_tree.header())
            self._apply_file_filter_internal()
        except Exception:
            pass

    def _meta_block_label(self, block: str) -> str:
        """Display name for a metadata block id (catalog label, else capitalized)."""
        try:
            b = str(block or "").strip()
        except Exception:
            b = ""
        if not b:
            return "—"
        try:
            cache = getattr(self, "_block_labels", None)
            if cache is None:
                cache = {}
                try:
                    from dataverse_client import read_metadata_fields_cache

                    for f in read_metadata_fields_cache(
                        self._config.app.workspace, self._config.dataverse.base_url
                    ) or []:
                        if isinstance(f, dict) and f.get("block") and f.get("block_label"):
                            cache.setdefault(str(f["block"]), str(f["block_label"]))
                except Exception:
                    pass
                self._block_labels = cache
            if b in cache:
                return cache[b]
        except Exception:
            pass
        return b[:1].upper() + b[1:]

    def _populate_completeness(self, metadata: dict) -> None:
        # Rule-driven evaluation (keeps rule_id/level/pending for Response).
        try:
            from metadata_check import check_with_ruleset

            full, ruleset = check_with_ruleset(
                metadata, self._profile, self._inventory, self._staged_dir_or_none()
            )
            self._completeness_full = full
            self._ruleset = ruleset
            results = [
                {"field": r["field"], "requirement": r["requirement"],
                 "value": r.get("value", "—"), "status": r["status"],
                 "block": r.get("block", "") or ""}
                for r in full
            ]
        except Exception:
            from metadata_check import check_metadata_completeness

            results = check_metadata_completeness(metadata, profile=self._profile, inventory=self._inventory)
            self._completeness_full = [
                {**r, "rule_id": r.get("field", ""), "level": "required", "pending": False,
                 "response_template": ""}
                for r in results
            ]
        complete = sum(1 for r in results if r["status"] == "complete")
        total = len(results)
        color = SUCCESS_DARK if complete == total else AMBER_700 if complete > total / 2 else ERROR
        # Header carries just the count (profile name is already visible in
        # the header combo; the old in-body summary line was removed).
        self._meta_summary.setText(
            f"<span style='font-weight:700;color:{color}'>{complete}/{total} fields complete</span>"
        )
        # Auto-checks header belongs to the checks summary (see
        # _refresh_curation_preview); leave it alone once a report exists.
        if self._report is None:
            self._auto_summary.setText(f"{complete}/{total} metadata fields")
        # Full per-check table: Check | Block | Value | Status (requirement
        # in the Check cell's tooltip).
        # Sorting stays OFF while rows are inserted: with sorting on, each
        # setItem re-sorts immediately and later writes land in the wrong
        # visual rows (duplicated text in some rows, empty cells in others).
        _was_sorting = self._meta_check_table.isSortingEnabled()
        self._meta_check_table.setSortingEnabled(False)
        # Block header signals too: changing row counts toggles the
        # vertical scrollbar, which recomputes the stretch (Value) column
        # and would otherwise persist a mid-populate width.
        try:
            self._meta_check_table.horizontalHeader().blockSignals(True)
        except Exception:
            pass
        try:
            self._meta_check_table.setRowCount(total)
            for row, r in enumerate(results):
                ok = r["status"] == "complete"
                field_item = QTableWidgetItem(r["field"])
                field_item.setToolTip(r["requirement"])
                _ff = field_item.font()
                _ff.setBold(True)
                field_item.setFont(_ff)
                value_item = QTableWidgetItem(r.get("value", "—"))
                value_item.setToolTip(f"{r['requirement']}\n\nValue: {r.get('value', '—')}")
                from ui.icons import icon as _icon

                block_item = QTableWidgetItem(self._meta_block_label(r.get("block", "")))
                block_item.setToolTip(
                    self._meta_block_label(r.get("block", ""))
                    + (f"\n\n{r['requirement']}" if r.get("requirement") else "")
                )
                status_item = QTableWidgetItem("Complete" if ok else "Incomplete")
                status_item.setToolTip(r["requirement"])
                status_item.setForeground(QColor(SUCCESS_DARK if ok else ERROR))
                status_item.setData(Qt.UserRole, bool(ok))
                try:
                    status_item.setIcon(
                        _icon("check", color=SUCCESS)
                        if ok else _icon("x", color=ERROR)
                    )
                except Exception:
                    pass
                _bf = status_item.font()
                _bf.setBold(True)
                status_item.setFont(_bf)
                self._meta_check_table.setItem(row, 0, field_item)
                self._meta_check_table.setItem(row, 1, block_item)
                self._meta_check_table.setItem(row, 2, value_item)
                self._meta_check_table.setItem(row, 3, status_item)
        finally:
            try:
                self._meta_check_table.horizontalHeader().blockSignals(False)
            except Exception:
                pass
            self._meta_check_table.setSortingEnabled(_was_sorting)
        self._meta_check_table.resizeRowsToContents()
        # Content-width columns (Value stays Stretch and absorbs slack);
        # no-op when a saved view was restored or the user resized.
        self._meta_check_table.fit_columns_to_content()
        # Apply the active Complete/Incomplete filter; it also refits the
        # card height to the visible rows (no internal scrollbar).
        self._apply_meta_filter()
        # Keep the Response draft in sync (preserves manual edits).
        try:
            self._refresh_response()
        except Exception:
            pass

    def _toggle_raw(self) -> None:
        from ui.icons import icon as _icon

        vis = not self._raw_view.isVisible()
        self._raw_view.setVisible(vis)
        self._raw_btn.setText("Hide raw metadata" if vis else "Show all metadata fields")
        try:
            self._raw_btn.setIcon(
                _icon("chevron-up" if vis else "chevron-right")
            )
        except Exception:
            pass

    def _on_metadata_error(self, msg: str) -> None:
        self._progress.setVisible(False)
        self._load_meta_btn.setEnabled(True)
        self._set_status("")
        headline, details = describe_error(msg)
        show_critical(self, "Metadata", headline, details=details,
                     retry=self._on_load_metadata)

    def _decision_choices(self) -> tuple[list[str], bool]:
        """(options, from_labels): instance curation labels when known."""
        try:
            allowed = [str(lbl).strip() for lbl in ((self._curation or {}).get("allowed") or []) if str(lbl).strip()]
        except Exception:
            allowed = []
        if allowed:
            seen: list[str] = []
            for label in allowed:
                if label not in seen:
                    seen.append(label)
            return seen, True
        return ["Approve & Publish", "Contact Author (Revisions Required)", "Reject Submission", "Hold for Internal Review"], False

    def _refresh_decision_options(self) -> None:
        try:
            current = self._decision_combo.currentText()
        except Exception:
            current = ""
        try:
            self._decision_combo.blockSignals(True)
            self._decision_combo.clear()
            options, from_labels = self._decision_choices()
            self._decision_combo.addItem("Select decision…", None)
            for opt in options:
                self._decision_combo.addItem(opt, opt)
            idx = self._decision_combo.findText(current)
            self._decision_combo.setCurrentIndex(idx if idx > 0 else 0)
            tip = (
                "Curation labels from this Dataverse instance"
                if from_labels
                else "No instance labels available — generic states"
            )
            self._decision_combo.setToolTip(tip)
        finally:
            try:
                self._decision_combo.blockSignals(False)
            except Exception:
                pass
            # Rebuilt list → helper line + commit gate follow the restored
            # choice (no-op before the widgets exist at build time).
            self._sync_decision_state()

    def _decision_consequence(self, choice: str, from_labels: bool) -> str:
        """One line naming what recording this choice actually does.

        The four generic states get real consequence copy; instance curation
        labels (arbitrary server strings) fall back to the shared mechanics
        (dataset log + Dataverse label), so the line never overpromises.
        """
        known = {
            "Approve & Publish": (
                "Curator sign-off: records approval in this dataset's log; "
                "publish the draft in Dataverse when ready."
            ),
            "Contact Author (Revisions Required)": (
                "Requests changes: records the request here; send the drafted "
                "response above to the author."
            ),
            "Reject Submission": (
                "Declines this version: records the rejection; the draft "
                "stays in Dataverse until withdrawn."
            ),
            "Hold for Internal Review": (
                "Parks the dataset for a second look: records the hold; no "
                "Dataverse state changes."
            ),
        }
        text = known.get(choice, f"Records '{choice}' in this dataset's log.")
        if from_labels:
            text += " Also set as this dataset's Dataverse curation label."
        return text

    def _sync_decision_state(self, *_ignored: object) -> None:
        """Gate Commit + refresh the helper line for the current choice.

        Commit is disabled while the combo sits on the "Select decision…"
        non-answer, so the decision can't be skipped past silently — the
        placeholder itself explains why (2026-10-02 P3).
        """
        try:
            choice = self._decision_combo.currentData()
            choice = choice if isinstance(choice, str) and choice else ""
            help_lbl = getattr(self, "_decision_help", None)
            if help_lbl is not None:
                if choice:
                    _options, from_labels = self._decision_choices()
                    help_lbl.setText(
                        self._decision_consequence(choice, from_labels)
                    )
                else:
                    help_lbl.setText(
                        "Pick an action to see what it does — Commit stays "
                        "disabled until one is chosen."
                    )
            commit = getattr(self, "_commit_btn", None)
            if commit is not None:
                commit.setEnabled(bool(choice))
        except Exception:
            pass

    # -- assessment commit --
    def _on_commit(self) -> None:
        decision = self._decision_combo.currentData()
        if not isinstance(decision, str) or not decision:
            show_warning(self, "Assessment", "Please select a decision state.")
            return
        _options, from_labels = self._decision_choices()
        notes = self._notes_edit.toPlainText().strip()
        msg = f"Decision: {decision}"
        if notes:
            msg += f"\n\nNotes:\n{notes}"
        if self._report is not None:
            msg += f"\n\nReport has {len(self._report.files)} file(s) with findings — use Export report… to save."
        self._log_action("decision", f"{decision}" + (f" — {notes[:200]}" if notes else ""), {"decision": decision, "notes": notes[:2000]})
        pushed = False
        push_error = ""
        if from_labels:
            # The decision IS a Dataverse curation label — assign it there too.
            try:
                pushed = bool(self._client.set_curation_label(self._pid, decision))
                if pushed:
                    self._curation["label"] = decision
                    try:
                        self._update_curation_pill()
                    except Exception:
                        pass
                else:
                    push_error = "Dataverse rejected the label change."
            except Exception as exc:
                push_error = str(exc)[:200]
        if from_labels and not pushed:
            show_warning(self, "Assessment committed (local only)", msg + f"\n\n{push_error or 'Label not set in Dataverse.'}\nRecorded in Dataset log below.")
        else:
            tail = "\n\n(Label set in Dataverse + recorded in Dataset log.)" if pushed else "\n\n(Recorded in Dataset log below.)"
            show_info(self, "Assessment committed", msg + tail)

    # -- download / checks -------------------------------------------------
    def _on_download(self) -> None:
        try:
            inventory = self._dl_mgr.inventory(self._pid)
        except Exception as exc:
            show_warning(self, "Download", f"Could not get file inventory:\n{exc}")
            return
        quote = DownloadManager.quote_from(inventory, self._pid)
        # Skip the bundle entirely when everything is already staged.
        try:
            missing = self._dl_mgr.missing_files(self._pid, inventory)
        except Exception:
            missing = ["(inventory check failed — downloading anyway)"]
        if inventory and not missing:
            ok, problems, warnings = self._dl_mgr.verify(self._pid)
            self._refresh_files_placeholder()
            self._check_btn.setEnabled(True)
            self._check_btn.setToolTip("Run the automated curation checks on the staged files")
            self._set_status(
                f"All {len(inventory)} file(s) already downloaded and verified — skipping download."
            )
            self._log_action("downloaded", f"Already staged ({len(inventory)} files) — skipped", {"skipped": True})
            if problems or warnings:
                show_warning(
                    self, "Download",
                    "Staged files found, but with notes:\n"
                    + "\n".join((problems + warnings)[:10]),
                )
            else:
                show_info(
                    self, "Download",
                    f"All {len(inventory)} file(s) are already downloaded and verified — nothing to fetch.",
                )
            return
        # A guestbook must be answered inside the approval window. It is
        # normally preloaded with the metadata; fall back to one small GET
        # when this view came from cached metadata or a stale record.
        guestbook = self._guestbook
        if not (isinstance(guestbook, dict) and guestbook.get("id")):
            guestbook = None
            gb_id = (
                self._metadata.get("guestbookId")
                if isinstance(self._metadata, dict)
                else None
            )
            if gb_id:
                try:
                    guestbook = self._client.get_guestbook(gb_id)
                    self._guestbook = guestbook
                    if not self._account:
                        self._account = self._client.get_current_user()
                except Exception as exc:
                    show_warning(
                        self,
                        "Download",
                        "This dataset requires a guestbook response, but its "
                        f"fields could not be loaded:\n{exc}\n\n"
                        "Check the API token in Settings (Ctrl+,), then try again.",
                    )
                    return
        if isinstance(guestbook, dict) and guestbook.get("enabled") is False:
            guestbook = None
        dlg = DownloadApprovalDialog(
            quote, self, guestbook=guestbook, account=self._account
        )
        if dlg.exec() != QDialog.Accepted:
            return
        guestbook_response = dlg.guestbook_response() if guestbook else None
        self._dl_btn.setEnabled(False)
        self._set_status("Downloading bundle…")
        self._progress.setVisible(True)
        self._progress.setRange(0, 0)
        self._dl_worker = DownloadWorker(
            self._client,
            self._config.app.workspace,
            self._pid,
            self,
            guestbook_response=guestbook_response,
        )
        self._dl_worker.progress.connect(lambda n: self._progress.setFormat(f"{n / 1024**2:.1f} MB"))
        self._dl_worker.progressFraction.connect(self._on_ring_fraction)
        self._dl_worker.finished.connect(self._on_download_finished)
        self._dl_worker.error.connect(self._on_download_error)
        self._dl_worker.cancelled.connect(self._on_download_cancelled)
        self._dl_worker.finished.connect(self._dl_worker.deleteLater)
        self._dl_worker.error.connect(self._dl_worker.deleteLater)
        self._dl_worker.cancelled.connect(self._dl_worker.deleteLater)
        self._dl_cancel_btn.setEnabled(True)
        self._dl_cancel_btn.setVisible(True)
        self._dl_worker.start()

    def _on_download_finished(self, staged: Path) -> None:
        self._progress.setVisible(False)
        self._hide_ring()
        self._dl_btn.setEnabled(True)
        ok, problems, warnings = self._dl_mgr.verify(self._pid)
        if problems:
            show_warning(self, "Download", "Checksum problems:\n" + "\n".join(problems[:10]))
        elif warnings:
            show_info(
                self, "Download",
                "Downloaded with notes (tabular files — data is intact, see UNFs):\n"
                + "\n".join(warnings[:10]),
            )
        self._refresh_files_placeholder()
        # Belt-and-braces: staged files exist now, so checks are available.
        self._check_btn.setEnabled(self._dl_mgr.files_dir(self._pid).exists())
        self._check_btn.setToolTip("Run the automated curation checks on the staged files")
        self._set_status(f"Downloaded to {staged} — ready to run checks.")
        self._log_action("downloaded", f"Staged to {staged}", {"staged": str(staged), "ok": ok})
        # Staged content may resolve file-content text rules — re-evaluate.
        try:
            if self._metadata is not None:
                self._populate_completeness(self._metadata)
        except Exception:
            pass

    def _on_download_error(self, msg: str) -> None:
        self._progress.setVisible(False)
        self._hide_ring()
        self._dl_btn.setEnabled(True)
        self._set_status("")
        headline, details = describe_error(msg)
        show_critical(self, "Download", headline, details=details,
                     retry=self._on_download)

    def _on_download_cancel_click(self) -> None:
        """Ask the worker to stop; stay disabled until it acknowledges."""
        if self._dl_worker is None:
            return
        self._dl_cancel_btn.setEnabled(False)
        self._set_status("Cancelling — stopping after the current chunk…")
        try:
            self._dl_worker.cancel()
        except Exception:
            pass

    def _on_download_cancelled(self) -> None:
        """Worker acknowledged the cancel: reset the action row quietly."""
        self._dl_worker = None
        self._progress.setVisible(False)
        self._hide_ring()
        self._dl_btn.setEnabled(True)
        self._dl_cancel_btn.setEnabled(True)
        self._dl_cancel_btn.setVisible(False)
        self._refresh_files_placeholder()
        # Staged files (bundle extract or finished originals) stay valid.
        self._check_btn.setEnabled(self._dl_mgr.files_dir(self._pid).exists())
        self._set_status("Download cancelled — files already staged were kept.")
        self._log_action("downloaded", "Cancelled by user", {"cancelled": True})

    # -- checks cache ------------------------------------------------------
    def _cached_report_path(self) -> Path:
        """Return the fixed cache path inside the dataset's curation workspace folder."""
        return self._dl_mgr.dataset_dir(self._pid) / "checks-report.json"

    def _load_cached_report(self):
        """Last auto-saved checks report for this dataset, or None."""
        try:
            path = self._cached_report_path()
            if path.is_file():
                from engine.report import DatasetReport

                return DatasetReport.load(path)
        except Exception:
            pass
        return None

    def _on_run_checks(self) -> None:
        staged = self._dl_mgr.files_dir(self._pid)
        if not staged.exists():
            show_warning(self, "Checks", "Download the dataset first.")
            self._check_btn.setEnabled(True)
            return
        self._check_btn.setEnabled(False)
        self._set_status("Running automated curation checks…")
        self._progress.setVisible(True)
        self._progress.setRange(0, 0)
        self._check_worker = CheckWorker(staged, self._pid, self._title, self)
        self._check_worker.progress.connect(lambda msg: self._set_status(msg))
        self._check_worker.progressFraction.connect(self._on_ring_fraction)
        self._check_worker.finished.connect(self._on_checks_finished)
        self._check_worker.error.connect(self._on_checks_error)
        self._check_worker.finished.connect(self._check_worker.deleteLater)
        self._check_worker.error.connect(self._check_worker.deleteLater)
        self._check_worker.start()

    def _on_checks_finished(self, report) -> None:
        from engine.status import summarize

        self._report = report
        # Auto-cache: always save the JSON report into the dataset's
        # workspace folder (no dialog) so checks survive re-opening the
        # dataset and stay available for the next session.
        cache_path = None
        try:
            cache_path = self._cached_report_path()
            report.save(cache_path)
        except Exception:
            cache_path = None
        self._progress.setVisible(False)
        self._hide_ring()
        self._check_btn.setEnabled(True)
        self._history_btn.setEnabled(True)
        # Update dataset-checks card + manifest tree
        self._refresh_curation_preview()
        self._apply_file_filter_internal()
        all_results = list(report.dataset_checks) + [c for f in report.files for c in f.checks]
        summary = summarize(all_results)
        findings = summary["failed"]
        self._set_status(
            f"Checks complete — {findings} finding(s) "
            f"({summary['failed-error']} errors, {summary['failed-warning']} warnings, "
            f"{summary['skipped']} skipped) across {len(report.files)} files. "
            + (
                f"Report auto-saved to {cache_path.parent.name}"
                if cache_path is not None
                else "Could not auto-save the report (see log)."
            )
            + " Use Export reports… for Markdown."
        )
        self._log_action(
            "checks_run",
            f"{findings} finding(s) across {len(report.files)} files",
            {"findings": findings, "files": len(report.files)},
        )
        if cache_path is not None:
            try:
                self._log_action(
                    "checks_saved",
                    f"Auto-saved to {cache_path.parent.name}/{cache_path.name}",
                    {"path": str(cache_path)},
                )
            except Exception:
                pass
        # File-check findings feed the Response draft — rebuild it.
        try:
            self._refresh_response()
        except Exception:
            pass

    def _on_checks_error(self, msg: str) -> None:
        self._progress.setVisible(False)
        self._hide_ring()
        self._check_btn.setEnabled(True)
        self._set_status("")
        headline, details = describe_error(msg)
        show_critical(self, "Checks", headline, details=details,
                     retry=self._on_run_checks)

    def _on_tree_clicked(self, index) -> None:
        try:
            from ui.checks_tree import node_kind
        except Exception:
            return
        info = node_kind(index)
        kind = info.get("kind", "")
        if kind == "check":
            if not self._report:
                return
            path = info.get("path", "")
            check_id = info.get("check_id", "")
            entry = next((f for f in self._report.files if f.path == path), None)
            if not entry:
                return
            result = next((c for c in entry.checks if c.check_id == check_id), None)
            if result is None:
                return
            import json as _json

            try:
                details = _json.dumps(result.details or {}, indent=1)[:1500]
            except Exception:
                details = str(result.details)[:1500]
            self._set_status(
                f"{path}: [{result.level}] {result.check_id}: {result.message} — {details}"
            )
        elif kind == "file":
            if not self._report:
                return
            path = info.get("path", "")
            entry = next((f for f in self._report.files if f.path == path), None)
            if not entry:
                self._set_status(f"{path}: not in report")
            elif not entry.checks:
                self._set_status(f"{path}: no automated check — manual review required")
            else:
                from engine.status import summarize

                summary = summarize(entry.checks)
                self._set_status(
                    f"{path}: {summary['passed']} passed · "
                    f"{summary['failed-warning']} warn · "
                    f"{summary['failed-error']} errors · "
                    f"{summary['skipped']} skipped"
                )
        else:
            return

    def _on_file_selected(self, row: int, _col: int) -> None:
        # Legacy table slot (pre-tree). Kept so old signal wiring fails
        # loudly in one place instead of scattered AttributeErrors.
        return None

    def _on_export(self) -> None:
        if not self._report:
            show_warning(self, "Export", "Run checks first.")
            return
        from PySide6.QtWidgets import QFileDialog
        try:
            self._dl_mgr.reports_dir(self._pid).mkdir(parents=True, exist_ok=True)
            start_dir = str(
                self._dl_mgr.reports_dir(self._pid)
                / f"{self._pid.replace(':', '_').replace('/', '_')}_report.md"
            )
        except Exception:
            start_dir = f"{self._pid.replace(':', '_').replace('/', '_')}_report.md"
        try:
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Export reports (Markdown + JSON)",
                start_dir,
                "Markdown (*.md)",
                options=QFileDialog.DontUseNativeDialog,
            )
        except Exception as exc:
            show_critical(self, "Export", f"Could not open the save dialog:\n{exc}")
            return
        if not path:
            return
        try:
            md_path = Path(path)
            if md_path.suffix.lower() != ".md":
                md_path = md_path.with_suffix(".md")
            json_path = md_path.with_suffix(".json")
            self._report.save_markdown(md_path)
            self._report.save(json_path)
        except Exception as exc:
            show_critical(self, "Export", f"Could not write the report:\n{exc}")
            return
        # Success needs no modal — the status line + Dataset log record it.
        # Modals are reserved for failures (above).
        self._log_action("exported", f"Reports saved to {md_path} + {json_path}", {"path": str(json_path), "markdown": str(md_path)})
        self._set_status(f"Reports saved: {md_path.name} + {json_path.name} (recorded in Dataset log)")
