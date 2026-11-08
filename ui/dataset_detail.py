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
    QAbstractItemView,
    QDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from config import Config
from dataverse_client import DataverseClient
from download_manager import DownloadManager
from metadata_check import DEFAULT_PROFILE, PROFILES
from storage import RESOLVED_DISPOSITIONS, finding_key

# Verdict reason/level keys (dv-6nv): stable engine tokens mapped to
# catalogue copy. Module-level so the string guard sees the keys.
_VERDICT_REASON_KEYS = {
    "required-missing": "detail.verdict.reason_required",
    "optional-missing": "detail.verdict.reason_optional",
    "errors": "detail.verdict.reason_errors",
    "warnings": "detail.verdict.reason_warnings",
    "sensitivity": "detail.verdict.reason_sensitivity",
}
_VERDICT_LEVEL_KEYS = {
    "ready": "detail.verdict.level_ready",
    "revisions": "detail.verdict.level_revisions",
    "blocked": "detail.verdict.level_blocked",
    "unreviewed": "detail.verdict.level_unreviewed",
}
from ui.dialogs import confirm, describe_error, show_critical, show_info, show_warning
from ui.download_dialog import DownloadApprovalDialog
from ui.i18n import t
from ui.ring import RingProgress
from ui.status_text import status_text
from ui.table_layout import TableLayout
from ui.theme import (
    ACCENT_PRIMARY,
    BORDER_SUBTLE,
    FONT_BODY,
    FONT_CAPTION,
    FONT_SMALL,
    STATE_ERROR_BG,
    STATE_ERROR_BORDER,
    STATE_ERROR_GRAPHIC,
    STATE_ERROR_SURFACE,
    STATE_ERROR_TEXT,
    STATE_SUCCESS_GRAPHIC,
    STATE_WARNING_GRAPHIC,
    SURFACE_ALT,
    SURFACE_CARD,
    SURFACE_PAGE,
    SURFACE_SUBTLE,
    SURFACE_TINT,
    TEXT_AMBER,
    TEXT_DANGER,
    TEXT_MUTED,
    TEXT_ON_ACCENT,
    TEXT_PRIMARY,
    TEXT_SUBTLE,
    TEXT_SUCCESS,
    band_qss,
    enable_list_copy,
    page_background_qss,
    selectable_labels,
    status_strip_qss,
    surface_frame_qss,
    transparent_surface_qss,
)
from ui.widgets import (
    AppTable,
    AppTree,
    WorkflowRail,
    add_info_tip,
    disposition_label,
    flush_list_style,
    flush_table_style,
    make_action_button,
    make_badge,
    make_body_label,
    make_caption_label,
    make_card,
    make_combo,
    make_disposition_combo,
    make_elided_label,
    make_field_label,
    make_list,
    make_multiline_input,
    make_page_heading,
    make_progress_bar,
    make_reset_columns_button,
    make_search_field,
    make_small_body_label,
    set_badge_label,
)
from ui.workers import CheckWorker, DownloadWorker, MetadataWorker

# The sections the sidebar (and the folded sidebar's menu) can jump to.
# The catalogue key is literal here so the string guard sees it.
_SECTION_LINKS: tuple[tuple[str, str], ...] = (
    ("detail.sections.metadata_check", "_meta_card"),
    ("detail.sections.file_manifest", "_file_card"),
    ("detail.sections.auto_checks", "_auto_card"),
    ("detail.sections.version_log", "_version_card"),
)


def _human_size(n: int) -> str:
    # Re-exported from the shared helper (dv-005): labels are decimal (KB/MB).
    from ui.widgets import human_size as _shared

    return _shared(n)


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
            return ("PillInReview", t("dashboard.display_state.review"))
        return ("PillDraft", t("dashboard.display_state.draft"))
    if s in ("RELEASED", "PUBLISHED"):
        return ("PillReady", t("dashboard.display_state.published"))
    if s == "DEACCESSIONED":
        return ("PillDraft", t("dashboard.display_state.deaccessioned"))
    if "REVIEW" in s:
        return ("PillInReview", t("dashboard.display_state.review"))
    if not s:
        return ("PillDraft", t("dashboard.display_state.draft"))
    return ("PillDraft", s.title())


def _format_metadata(metadata: dict) -> str:
    if not metadata:
        return t("detail.meta.no_metadata")
    try:
        lines = []
        latest = metadata.get("latestVersion") or {}
        blocks = latest.get("metadataBlocks") or metadata.get("metadataBlocks") or {}
        if blocks:
            for block_name, block in blocks.items():
                lines.append(
                    t(
                        "detail.meta.block_format",
                        block=block_name,
                        name=block.get("displayName", ""),
                    )
                )
                for field in block.get("fields", []):
                    type_name = field.get("typeName", "")
                    v = field.get("value", "")
                    if isinstance(v, list):
                        v = t("detail.meta.value_separator").join(
                            str(x.get("value") if isinstance(x, dict) and "value" in x else x)
                            for x in v[:5]
                        )
                    lines.append(
                        t("detail.meta.field_format", type=type_name, value=v)
                    )
                lines.append("")
        lines.append(t("detail.meta.full_json"))
        lines.append(json.dumps(metadata, indent=2, ensure_ascii=False)[:12000])
        return "\n".join(lines)
    except Exception as exc:
        return (
            json.dumps(metadata, indent=2, ensure_ascii=False)[:12000]
            + t("detail.meta.format_error", exc=exc)
        )


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
        # Workflow-rail state (all cheap flags/counts; the rail never stats
        # files or touches the network, see ui/workflow.py).
        self._changes_loaded: bool = False
        self._inventory_ok: bool = True
        self._staged_n: int = 0
        self._staged_total: int = 0
        self._last_export_path: str | None = None
        self._decision_committed: bool = False
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
        # One page-background rule for the view and every page surface it
        # hosts (top bar, stacked pages, canvases); the scroll areas that
        # carry them come with the rule.
        self.setStyleSheet(
            page_background_qss(
                "DetailView",
                "DetailTopBar",
                "DetailPages",
                "DetailReviewPage",
                "DetailResponsePage",
                "DetailResponseInner",
                "Canvas",
            )
        )
        self.setAutoFillBackground(False)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- Fixed page header (title, actions, status) ----
        top = QWidget()
        top.setObjectName("DetailTopBar")
        top_lay = QVBoxLayout(top)
        top_lay.setContentsMargins(24, 24, 24, 12)
        top_lay.setSpacing(8)
        root.addWidget(top)

        # ---- Pages: Review (existing assessment layout) + Response (draft) ----
        from PySide6.QtWidgets import QStackedWidget as _QStackedWidget

        self._pages = _QStackedWidget()
        self._pages.setObjectName("DetailPages")
        root.addWidget(self._pages, 1)
        review_page = QWidget()
        review_page.setObjectName("DetailReviewPage")

        # ---- Content row: scrolling main column + sticky sidebar ----
        content_row = QHBoxLayout(review_page)
        content_row.setContentsMargins(0, 0, 0, 0)
        content_row.setSpacing(0)

        # ---- Main column scroll ----
        main_scroll = QScrollArea()
        main_scroll.setWidgetResizable(True)
        main_scroll.setFrameShape(QFrame.NoFrame)
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
        content_row.addWidget(side_scroll, 2)
        self._side_scroll = side_scroll
        # None = the width decides (the sidebar folds away below
        # _SIDEBAR_COLLAPSE_BELOW); True/False = the user decided.
        self._sidebar_user_collapsed: bool | None = None
        self._sidebar_collapsed = False

        # ---- Page header (ID badge + status, title, depositor, actions) ----
        header_row = QHBoxLayout()
        header_row.setSpacing(16)
        header_left = QVBoxLayout()
        header_left.setSpacing(6)
        badge_row = QHBoxLayout()
        badge_row.setSpacing(8)
        badge_row.setContentsMargins(0, 0, 0, 0)
        # Full persistent ID, never truncated (DOIs run well past 18 chars).
        # Same sans face and badge metrics as the status pills beside it —
        # the old mono face made the ID read like code instead of a chip.
        self._id_badge = make_badge(
            self._pid,
            background=SURFACE_TINT,
            foreground=TEXT_MUTED,
            border=BORDER_SUBTLE,
            font_size=FONT_CAPTION,
            padding="2px 8px",
        )
        self._id_badge.setToolTip(self._pid)
        badge_row.addWidget(self._id_badge)
        self._status_pill = make_badge(t("detail.header.loading"), label="loading")
        self._status_pill.setObjectName("PillInReview")
        badge_row.addWidget(self._status_pill)
        self._curation_pill = make_badge("", label="draft")
        self._curation_pill.setObjectName("PillDraft")
        self._curation_pill.setVisible(False)
        self._curation_pill.setToolTip(t("detail.header.curation_label_tooltip"))
        badge_row.addWidget(self._curation_pill)
        badge_row.addStretch()
        header_left.addLayout(badge_row)

        # Same page-heading contract as Settings / Review configuration /
        # Log / About (HeadlineLG theme token).
        self._title_lbl, _subtitle = make_page_heading(self._title)
        self._title_lbl.setWordWrap(True)

        # Clickable Dataverse link sits next to the title
        self._header_link = QLabel()
        self._header_link.setObjectName("BodySM")
        self._header_link.setTextFormat(Qt.RichText)
        self._header_link.setOpenExternalLinks(True)
        title_row = QHBoxLayout()
        title_row.setSpacing(12)
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.addWidget(self._title_lbl, 1)
        title_row.addWidget(self._header_link, 0, Qt.AlignBottom)
        header_left.addLayout(title_row)

        self._depositor_lbl = make_body_label(t("detail.header.loading_metadata"), wrap=False)
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
        self._dl_btn = make_action_button(t("detail.header.download_all"), kind="secondary", size="md")
        # Inline button style: app-level QSS fails to paint button faces inside
        # some main-window subtrees, so critical actions carry their own CSS.
        self._dl_btn.clicked.connect(self._on_download)
        actions_row.addWidget(self._dl_btn)
        # Mid-download Cancel — hidden until a worker starts, so the action
        # row keeps its idle layout (critique P3: no silent 15-min wait).
        self._dl_cancel_btn = make_action_button(t("common.cancel"), kind="secondary", size="md")
        self._dl_cancel_btn.setToolTip(t("detail.header.download_cancel_tip"))
        self._dl_cancel_btn.setAccessibleName(t("detail.header.download_cancel_a11y"))
        self._dl_cancel_btn.clicked.connect(self._on_download_cancel_click)
        self._dl_cancel_btn.setVisible(False)
        actions_row.addWidget(self._dl_cancel_btn)
        self._history_btn = make_action_button(t("detail.header.export_reports"), kind="secondary", size="md")
        self._history_btn.setToolTip(t("detail.header.export_reports_tip"))
        self._history_btn.clicked.connect(self._on_export)
        actions_row.addWidget(self._history_btn)
        self._load_meta_btn = make_action_button(t("detail.header.load_metadata"), kind="secondary", size="md")
        self._load_meta_btn.setToolTip(t("detail.header.load_metadata_tip"))
        self._load_meta_btn.clicked.connect(self._on_load_metadata)
        actions_row.addWidget(self._load_meta_btn)
        # Sections menu: the sidebar's navigation, reachable even when
        # the sidebar itself is folded away on a narrow window.
        self._sections_btn = make_action_button(
            t("detail.sections.title"), kind="chip"
        )
        self._sections_btn.setToolTip(t("detail.sidebar.sections_tip"))
        self._sections_menu = QMenu(self._sections_btn)
        self._sections_btn.setMenu(self._sections_menu)
        self._sections_menu.aboutToShow.connect(self._fill_sections_menu)
        self._sections_btn.setVisible(False)
        actions_row.addWidget(self._sections_btn)
        actions_col.addLayout(actions_row)
        # Run checks as primary (always enabled; warns when nothing is staged)
        self._check_btn = make_action_button(t("detail.header.run_checks"), kind="primary", size="lg")
        self._check_btn.setToolTip(t("detail.header.run_checks_tip"))
        self._check_btn.clicked.connect(self._on_run_checks)
        actions_col.addWidget(self._check_btn)
        # Cancel checks - hidden until a run starts, so the idle header
        # keeps its layout. A check pass over a large dataset can run for
        # minutes; without a way out the only option is to wait.
        self._checks_cancel_btn = make_action_button(
            t("detail.header.cancel_checks"), kind="secondary", size="md"
        )
        self._checks_cancel_btn.setToolTip(t("detail.header.cancel_checks_tip"))
        self._checks_cancel_btn.setAccessibleName(t("detail.header.cancel_checks_a11y"))
        self._checks_cancel_btn.clicked.connect(self._on_cancel_checks_click)
        self._checks_cancel_btn.setVisible(False)
        actions_col.addWidget(self._checks_cancel_btn)
        header_row.addLayout(actions_col, 0)
        top_lay.addLayout(header_row)

        # Status + progress (subtle). The strip carries body-size text
        # (13px): it is the page's only running commentary - "Checks
        # complete - 3 findings across 42 files" - and at caption size it
        # was the smallest, least readable line in the app.
        self._status = QLabel("")
        self._status.setStyleSheet(
            status_strip_qss(
                SURFACE_CARD, BORDER_SUBTLE, TEXT_MUTED, font_size=FONT_BODY
            )
        )
        self._status.setWordWrap(True)
        self._status.setVisible(False)
        top_lay.addWidget(self._status)
        self._progress = make_progress_bar(height=6)
        self._progress.setVisible(False)
        top_lay.addWidget(self._progress)
        # Circular ring for download/check progress (W-12): a determinate
        # arc beside the linear bar, since the bar is indeterminate for
        # streamed bundles.
        self._ring = RingProgress(diameter=28)
        self._ring.hide()
        top_lay.addWidget(self._ring)
        top_lay.setAlignment(self._ring, Qt.AlignVCenter)

        # Workflow step rail (replaces the old Review/Response tab row):
        # six steps, each navigates only — no step ever runs an action.
        self._rail = WorkflowRail()
        self._rail.stepClicked.connect(self._on_workflow_step)
        top_lay.addWidget(self._rail)

        # ---- Main column content (inside main_scroll canvas) ----
        # MAIN column: verdict → completeness → files → auto-checks → version diff
        main_wrap = QVBoxLayout()
        main_wrap.setSpacing(20)
        main_wrap.setContentsMargins(0, 0, 0, 0)
        self._main_wrap = main_wrap

        self._verdict_card = self._build_verdict_card()
        main_wrap.addWidget(self._verdict_card)

        self._meta_card = self._build_metadata_card()
        main_wrap.addWidget(self._meta_card)

        self._file_card = self._build_file_manifest_card()
        main_wrap.addWidget(self._file_card, 1)

        self._auto_card = self._build_auto_checks_card()
        main_wrap.addWidget(self._auto_card)

        self._version_card = self._build_version_card()
        main_wrap.addWidget(self._version_card)

        # Raw metadata expandable (minimal)
        self._raw_btn = make_action_button(t("detail.header.show_raw_metadata"), kind="ghost", size=None)
        self._raw_btn.clicked.connect(self._toggle_raw)
        try:
            from ui.icons import icon as _rw_icon

            self._raw_btn.setIcon(_rw_icon("chevron-right"))
        except Exception:
            pass
        main_wrap.addWidget(self._raw_btn)
        self._raw_view = make_multiline_input(
            read_only=True,
            mono=True,
            min_height=180,
            font_size=FONT_CAPTION,
        )
        self._raw_view.setVisible(False)
        main_wrap.addWidget(self._raw_view)

        main_container = QWidget()
        main_container.setLayout(main_wrap)
        main_container.setObjectName("DetailMainContainer")
        main_container.setStyleSheet(transparent_surface_qss("DetailMainContainer"))
        canvas_lay.addWidget(main_container)

        # SIDEBAR (right, sticky): navigation → dataset log
        # (Assessment Action moved to the Response page.)
        side_wrap = QVBoxLayout()
        side_wrap.setSpacing(20)
        side_wrap.setContentsMargins(12, 12, 24, 24)
        self._side_wrap = side_wrap

        self._nav_card = self._build_nav_card()
        side_wrap.addWidget(self._nav_card)

        self._dataset_log_card = self._build_dataset_log_card()
        # Stretch factor 1: the log owns the sidebar's free vertical space
        # so the timeline reads without constant scrolling.
        side_wrap.addWidget(self._dataset_log_card, 1)

        side_container = QWidget()
        side_container.setLayout(side_wrap)
        side_container.setObjectName("DetailSideContainer")
        side_container.setStyleSheet(transparent_surface_qss("DetailSideContainer"))
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
                        t(
                            "detail.status.saved_metadata_refreshing",
                            count=len(self._inventory),
                        )
                    )
                else:
                    self._set_status(
                        t(
                            "detail.status.metadata_cached",
                            count=len(self._inventory),
                        )
                    )
            elif isinstance(self._inventory, list) and len(self._inventory) == 0:
                # Cached, and genuinely zero files — say so plainly
                from ui.checks_tree import build_tree_model

                self._file_tree.setModel(build_tree_model([], None))
                self._all_file_rows = []
                self._file_footer_left.setText(t("detail.files.no_files_in_dataverse"))
                self._file_footer_right.setText("")
                self._set_status(t("detail.status.no_files"))
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
                        t(
                            "detail.status.saved_checks_report",
                            stamp=stamp,
                        )
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
    def _build_verdict_card(self) -> QFrame:
        """Readiness banner (dv-6nv): one synthesized answer, top of page."""
        from ui.icons import icon as _icon

        card = QFrame()
        card.setObjectName("VerdictCard")
        lay = QHBoxLayout(card)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(10)
        self._verdict_icon = QLabel()
        try:
            self._verdict_icon.setPixmap(_icon("circle-dashed", color=TEXT_MUTED).pixmap(18, 18))
        except Exception:
            pass
        lay.addWidget(self._verdict_icon)
        self._verdict_label = QLabel(t("detail.verdict.level_unreviewed"))
        self._verdict_label.setObjectName("LabelStrongSM")
        self._verdict_label.setTextFormat(Qt.RichText)
        self._verdict_label.setWordWrap(True)
        lay.addWidget(self._verdict_label)
        lay.addStretch(1)
        self._verdict_chips = QHBoxLayout()
        self._verdict_chips.setSpacing(6)
        lay.addLayout(self._verdict_chips)
        card.setToolTip(t("detail.verdict.banner_tip"))
        return card

    def _refresh_verdict(self) -> None:
        """Recompute + paint the readiness banner from in-memory state."""
        try:
            from engine.verdict import assess
            from ui.icons import icon as _icon

            verdict = assess(
                self._report,
                self._completeness_full,
                self._dispositions_map(),
            )
            faces = {
                "ready": (SURFACE_TINT, STATE_SUCCESS_GRAPHIC, TEXT_SUCCESS, "check"),
                "revisions": (SURFACE_TINT, STATE_WARNING_GRAPHIC, TEXT_AMBER, "octagon-alert"),
                "blocked": (STATE_ERROR_BG, STATE_ERROR_BORDER, TEXT_DANGER, "octagon-x"),
                "unreviewed": (SURFACE_SUBTLE, BORDER_SUBTLE, TEXT_MUTED, "circle-dashed"),
            }
            bg, border, ink, icon_name = faces.get(
                verdict.level, faces["unreviewed"]
            )
            self._verdict_card.setStyleSheet(
                surface_frame_qss(bg, border, selector="QFrame#VerdictCard")
            )
            try:
                self._verdict_icon.setPixmap(_icon(icon_name, color=ink).pixmap(18, 18))
            except Exception:
                pass
            self._verdict_label.setText(
                f"<span style='color: {ink};'>"
                + t(_VERDICT_LEVEL_KEYS.get(verdict.level, "detail.verdict.level_unreviewed"))
                + "</span>"
            )
            while self._verdict_chips.count():
                item = self._verdict_chips.takeAt(0)
                w = item.widget() if item is not None else None
                if w is not None:
                    w.setParent(None)  # unparent now; deleteLater is async
                    w.deleteLater()
            for reason in verdict.reasons:
                key = _VERDICT_REASON_KEYS.get(reason.key)
                if not key:
                    continue
                chip = make_action_button(
                    t(key, count=reason.count), kind="chip", size="sm"
                )
                chip.setToolTip(t("detail.verdict.banner_tip"))
                chip.clicked.connect(
                    lambda _c=False, tgt=reason.target: self._on_verdict_chip(tgt)
                )
                self._verdict_chips.addWidget(chip)
        except Exception:
            pass

    def _on_verdict_chip(self, target: str) -> None:
        """A reason chip navigates to the card that owns the reason."""
        try:
            if target == "respond":
                self._show_response_page()
            elif target:
                self._goto_section(target)
        except Exception:
            pass

    def _build_auto_checks_card(self) -> QFrame:
        card, _body_host, _title, header_lay = make_card(t("detail.sections.auto_checks"))
        add_info_tip(
            header_lay,
            t("detail.auto_checks.intro"),
            t("detail.auto_checks.legend"),
            name=t("detail.sections.auto_checks"),
        )
        # Named pre-run state, never "—" (2026-10-02 P2); refreshed to
        # "N check(s) will run"/counts/"No file checks" as data lands.
        self._auto_summary = make_field_label(t("detail.auto_checks.not_run"))
        header_lay.addWidget(self._auto_summary)
        # Body: scroll of checks (factory body reused directly)
        self._auto_body = _body_host
        self._auto_body.setContentsMargins(16, 12, 16, 12)
        self._auto_body.setSpacing(8)
        # Placeholder
        self._auto_placeholder = make_small_body_label(t("detail.auto_checks.no_file_list"))
        self._auto_body.addWidget(self._auto_placeholder)
        return card

    def _build_metadata_card(self) -> QFrame:
        card, body, _title, header_lay = make_card(t("detail.sections.metadata_check"))
        add_info_tip(
            header_lay,
            t("detail.metadata_check.tip"),
            name=t("detail.sections.metadata_check"),
        )
        # Flush card (manifest-tree pattern): zero body margins; the table
        # bleeds edge-to-edge.
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        # x/xx summary lives in the header, right next to the title (the
        # old in-body summary line was removed).
        self._meta_summary = QLabel(t("detail.metadata_check.not_loaded"))
        self._meta_summary.setObjectName("StateMD")
        self._meta_summary.setTextFormat(Qt.RichText)
        self._meta_summary.setToolTip(t("detail.metadata_check.not_loaded_tip"))
        header_lay.insertWidget(2, self._meta_summary)
        # The two menus and the reset button live on their own row under
        # the title bar, like the File Manifest's filter row. In the title
        # row the card needed 791px - wider than the column it sits in -
        # so the page scrolled sideways at the app's own minimum width.
        meta_tools = QWidget()
        meta_tools.setObjectName("MetadataCheckTools")
        meta_tools.setStyleSheet(transparent_surface_qss("MetadataCheckTools"))
        meta_tools_lay = QHBoxLayout(meta_tools)
        meta_tools_lay.setContentsMargins(16, 8, 16, 8)
        meta_tools_lay.setSpacing(8)
        # Complete/incomplete filter for the checklist table.
        self._meta_filter = make_combo(
            [
                (t("detail.metadata_check.filter_all"), "all"),
                (t("detail.metadata_check.filter_complete"), "complete"),
                (t("detail.metadata_check.filter_incomplete"), "incomplete"),
            ],
            min_width=110,
            tip=t("detail.metadata_check.filter_tip"),
        )
        self._meta_filter.currentIndexChanged.connect(lambda _i: self._apply_meta_filter())
        meta_tools_lay.addWidget(self._meta_filter)
        # Standard 36px field like every other combo (a shorter button here
        # made this menu's rows read differently-sized vs the rest).
        self._profile_combo = make_combo(
            [(info["label"], key) for key, info in PROFILES.items()],
            min_width=140,
        )
        idx = list(PROFILES.keys()).index(DEFAULT_PROFILE) if DEFAULT_PROFILE in PROFILES else 0
        self._profile_combo.setCurrentIndex(idx)
        self._profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        meta_tools_lay.addWidget(self._profile_combo)
        self._meta_reset_btn = make_reset_columns_button(
            "",
            tip=t("detail.metadata_check.reset_columns_tip"),
            accessible_name=t("detail.metadata_check.reset_columns_a11y"),
            fallback_text=t("common.reset"),
        )
        self._meta_reset_btn.clicked.connect(self._on_reset_meta_view)
        meta_tools_lay.addWidget(self._meta_reset_btn)
        meta_tools_lay.addStretch()
        body.addWidget(meta_tools)
        # Every check with its status — an expandable tree
        # (Check | Block | Value | Status). Requirement text lives in the
        # Check cell's tooltip. A repeatable field expands into one child
        # per entry (Author 1, Author 2, …) and one grandchild per
        # subfield (Name, Affiliation, Identifier, …), so a compound value
        # is readable instead of being flattened into one line.
        from PySide6.QtGui import QStandardItemModel as _QStandardItemModel
        from PySide6.QtWidgets import QHeaderView as _QHV

        self._meta_check_tree = AppTree(row_height=30, flush=True)
        self._meta_model = _QStandardItemModel(0, 4, self)
        self._meta_model.setHorizontalHeaderLabels(
            ["Check", "Block", "Value", "Status"]
        )
        self._meta_check_tree.setModel(self._meta_model)
        _meta_hdr = self._meta_check_tree.header()
        # Value absorbs the slack and elides long text; Status only needs
        # its word + icon. Stretching the last section instead let a long
        # value push Status off the (scrollbar-less) card.
        _meta_hdr.setStretchLastSection(False)
        _meta_hdr.setSectionResizeMode(0, _QHV.Interactive)
        _meta_hdr.setSectionResizeMode(1, _QHV.Interactive)
        _meta_hdr.setSectionResizeMode(2, _QHV.Stretch)
        _meta_hdr.setSectionResizeMode(3, _QHV.ResizeToContents)
        self._meta_check_tree.setColumnWidth(0, 170)
        self._meta_check_tree.setColumnWidth(1, 120)
        self._meta_check_tree.expanded.connect(self._on_meta_tree_expansion_changed)
        self._meta_check_tree.collapsed.connect(self._on_meta_tree_expansion_changed)
        self._track_table_widths("dataset_meta", _meta_hdr)
        # No internal scrollbars: the card always fits every row; the page
        # canvas scrolls instead. Height is fitted in _fit_meta_tree_height.
        self._meta_check_tree.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._meta_check_tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._meta_check_tree.setFixedHeight(80)
        # Right-click a top-level check row to set its disposition
        # (dv-32x): the metadata card's tree rows map 1:1 to rule results.
        self._meta_check_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self._meta_check_tree.customContextMenuRequested.connect(
            self._on_meta_context_menu
        )
        body.addWidget(self._meta_check_tree)
        return card

    def _apply_meta_filter(self) -> None:
        """Apply the Complete/Incomplete filter by rebuilding the tree.

        The tree is small and model-driven, so rebuilding is simpler and
        safer than hiding rows: a hidden parent would keep its children
        orphaned in the model. The card then refits its height.
        """
        if not hasattr(self, "_meta_check_tree"):
            return
        try:
            mode = self._meta_filter.currentData() or "all"
        except Exception:
            mode = "all"
        results = list(getattr(self, "_meta_results", []))
        if mode == "complete":
            results = [r for r in results if r.get("status") == "complete"]
        elif mode == "incomplete":
            results = [r for r in results if r.get("status") != "complete"]
        self._build_meta_tree(results)

    # -- metadata check tree -------------------------------------------------
    # Acronyms that survive the generic camel-case split ("ID number", not
    # "Id number"). Field labels come from the schema keys themselves, so a
    # new compound field needs no hand-maintained label table.
    _META_ACRONYMS = {"id", "url", "uri", "doi", "orcid", "api", "html", "pdf"}
    # Dataverse prefixes that read as noise once the entry is nested.
    _META_KEY_OVERRIDES = {
        "dsDescription": "Description",
        "dsDescriptionValue": "Description",
        "dsDescriptionDate": "Date",
        "keywordValue": "Keyword",
    }

    def _pretty_meta_key(self, key: str) -> str:
        """Human label for a metadata key (``authorAffiliation`` → Affiliation)."""
        raw = str(key or "").strip()
        if not raw:
            return ""
        mapped = self._META_KEY_OVERRIDES.get(raw)
        if mapped:
            return mapped
        import re as _re

        words = _re.sub(
            r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", raw
        ).split()
        cleaned = [
            w.upper() if w.lower() in self._META_ACRONYMS else w.lower() for w in words
        ]
        text = " ".join(cleaned).strip()
        return text[:1].upper() + text[1:] if text else raw

    @staticmethod
    def _meta_display(value) -> str:
        """Compact display text for any metadata value (never raises)."""
        try:
            from metadata_check import _display_value as _dv

            return _dv(value, max_len=1000)
        except Exception:
            try:
                return str(value)
            except Exception:
                return t("common.em_dash")

    @staticmethod
    def _meta_is_compound(value) -> bool:
        """Return True when a dict has real subfields (not just a wrapped ``value``)."""
        if not isinstance(value, dict):
            return False
        keys = [k for k in value.keys() if k != "typeName"]
        return any(k != "value" for k in keys)

    def _meta_subfields(
        self, entry: dict, prefix: str = ""
    ) -> list[tuple[str, str]]:
        """(label, display) pairs for one compound metadata entry.

        The entry's own noun is stripped from each subfield label, so an
        author entry reads Name / Affiliation / Identifier rather than
        Author name / Author affiliation / …
        """
        rows: list[tuple[str, str]] = []
        for key, value in entry.items():
            if key == "typeName":
                continue
            if isinstance(value, dict) and "value" in value and not self._meta_is_compound(value):
                shown = self._meta_display(value.get("value"))
            else:
                shown = self._meta_display(value)
            label = self._pretty_meta_key(key)
            if prefix and label.lower().startswith(prefix.lower() + " "):
                trimmed = label[len(prefix) + 1:]
                if trimmed:
                    label = trimmed[:1].upper() + trimmed[1:]
            rows.append((label, shown))
        return rows

    def _meta_value_entries(self, result: dict) -> list[tuple[str, str, list]]:
        """Child entries for a check: [(label, summary, subfields)]."""
        block = str(result.get("block") or "")
        name = str(result.get("name") or "")
        if not block or not name or self._metadata is None:
            return []
        try:
            from metadata_check import _field

            meta = self._metadata or {}
            latest = meta.get("latestVersion") or {}
            blocks = latest.get("metadataBlocks") or meta.get("metadataBlocks") or {}
            raw = _field(blocks, block, name)
        except Exception:
            return []
        if isinstance(raw, list):
            seq = raw
        elif self._meta_is_compound(raw):
            seq = [raw]
        else:
            return []
        if not seq:
            return []
        noun = self._pretty_meta_key(name) or str(result.get("field") or "Entry")
        entries: list[tuple[str, str, list]] = []
        for i, item in enumerate(seq):
            label = f"{noun} {i + 1}"
            if isinstance(item, dict):
                subs = self._meta_subfields(item, noun)
                summary = next(
                    (text for _lbl, text in subs if text and text != t("common.em_dash")),
                    t("common.em_dash"),
                )
                entries.append((label, summary, subs))
            else:
                entries.append((label, self._meta_display(item), []))
        return entries

    def _build_meta_tree(self, results: list[dict]) -> None:
        """Rebuild the Check | Block | Value | Status tree from results."""
        from PySide6.QtGui import QBrush, QStandardItem

        tree = self._meta_check_tree
        model = self._meta_model
        model.removeRows(0, model.rowCount())
        # Row -> result mapping for the disposition context menu (the
        # filtered list the tree was built from, in row order).
        self._meta_tree_results = list(results)

        def _item(
            text: str,
            *,
            tooltip: str = "",
            bold: bool = False,
            color: str | None = None,
            italic: bool = False,
        ) -> QStandardItem:
            item = QStandardItem(str(text))
            item.setEditable(False)
            if tooltip:
                item.setToolTip(tooltip)
            if color:
                item.setForeground(QBrush(QColor(color)))
            font = item.font()
            if bold:
                font.setBold(True)
            if italic:
                font.setItalic(True)
            item.setFont(font)
            return item

        from ui.icons import icon as _icon

        for result in results:
            ok = result.get("status") == "complete"
            status_text = (
                t("detail.metadata_check.status_complete")
                if ok
                else t("detail.metadata_check.status_incomplete")
            )
            requirement = str(result.get("requirement") or "")
            value_text = str(result.get("value", t("common.em_dash")))
            field_item = _item(
                str(result.get("field") or ""),
                tooltip=requirement,
                bold=True,
                color=TEXT_PRIMARY if ok else TEXT_DANGER,
            )
            block_item = _item(
                self._meta_block_label(str(result.get("block") or "")),
                tooltip=(
                    self._meta_block_label(str(result.get("block") or ""))
                    + (f"\n\n{requirement}" if requirement else "")
                ),
            )
            value_item = _item(
                value_text,
                tooltip=requirement
                + t("detail.metadata_check.value_tooltip", value=value_text),
            )
            status_item = _item(status_text, tooltip=requirement, bold=True,
                                color=TEXT_SUCCESS if ok else TEXT_DANGER)
            try:
                status_item.setIcon(
                    _icon("check", color=STATE_SUCCESS_GRAPHIC)
                    if ok
                    else _icon("x", color=STATE_ERROR_GRAPHIC)
                )
            except Exception:
                pass
            parent = [field_item, block_item, value_item, status_item]
            for label, summary, subs in self._meta_value_entries(result):
                child = [
                    _item(label, color=TEXT_MUTED, bold=True),
                    _item(""),
                    _item(summary, tooltip=summary),
                    _item(""),
                ]
                parent[0].appendRow(child)
                for sub_label, sub_value in subs:
                    grand = [
                        _item(sub_label, color=TEXT_MUTED),
                        _item(""),
                        _item(
                            sub_value,
                            tooltip=sub_value,
                            italic=sub_value == t("common.em_dash"),
                            color=TEXT_SUBTLE
                            if sub_value == t("common.em_dash")
                            else None,
                        ),
                        _item(""),
                    ]
                    child[0].appendRow(grand)
            model.appendRow(parent)

        try:
            tree.blockSignals(True)
            tree.expandAll()
        finally:
            tree.blockSignals(False)
        self._fit_meta_tree_height()
        # Size the fixed columns to their content (with sane caps) and let
        # the stretched Value column take the rest.
        try:
            for col, floor, ceiling in ((0, 170, 320), (1, 100, 220), (3, 90, 160)):
                tree.resizeColumnToContents(col)
                tree.setColumnWidth(
                    col, max(floor, min(ceiling, tree.columnWidth(col)))
                )
        except Exception:
            pass

    def _on_meta_tree_expansion_changed(self, _index=None) -> None:
        self._fit_meta_tree_height()

    def _fit_meta_tree_height(self) -> None:
        """Grow the checks tree to its visible rows (no inner scrollbar)."""
        try:
            tree = self._meta_check_tree
            model = tree.model()
            visible_rows = 0
            if model is not None:
                stack = [tree.rootIndex()]
                while stack:
                    parent = stack.pop()
                    count = model.rowCount(parent)
                    visible_rows += count
                    for r in range(count):
                        idx = model.index(r, 0, parent)
                        if model.hasChildren(idx) and tree.isExpanded(idx):
                            stack.append(idx)
            header_h = tree.header().height() or 30
            tree.setFixedHeight(max(80, header_h + visible_rows * 30 + 2))
        except Exception:
            pass

    def _build_assessment_card(self) -> QFrame:
        card, body, _title, _header = make_card(t("detail.sections.assessment_action"))
        add_info_tip(
            _header,
            t("detail.assessment.tip"),
            name=t("detail.sections.assessment_action"),
        )
        body.setContentsMargins(16, 16, 16, 16)
        body.setSpacing(12)
        # Internal Notes
        lbl = make_field_label(t("detail.assessment.notes_label"))
        body.addWidget(lbl)
        self._notes_edit = make_multiline_input(
            t("detail.assessment.notes_placeholder"),
            height=110,
            font_size=FONT_SMALL,
        )
        body.addWidget(self._notes_edit)
        # Decision State
        lbl2 = make_field_label(t("detail.assessment.decision_label"))
        body.addWidget(lbl2)
        self._decision_combo = make_combo(
            tip=t("detail.assessment.decision_tip"),
        )
        self._refresh_decision_options()
        body.addWidget(self._decision_combo)
        # One-line consequence helper: names what recording the choice will
        # actually do BEFORE the commit, and Commit stays disabled while the
        # combo sits on the non-answer placeholder (2026-10-02 P3 — the
        # widest decision point had neither).
        self._decision_help = make_caption_label("")
        body.addWidget(self._decision_help)
        # Commit button row
        row = QHBoxLayout()
        row.addStretch()
        commit = make_action_button(t("detail.assessment.commit"), kind="primary", size="md")
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

        card, body, _title, header = make_card(t("detail.sections.title"))
        body.setSpacing(6)
        # Collapse the sidebar. On a narrow window the 280px it holds
        # squeezes the main column (the File Manifest tree) below a
        # usable width, so the sidebar folds away and its links move
        # into the top bar's Sections menu.
        self._sidebar_collapse_btn = make_action_button("", kind="ghost", size="sm")
        try:
            self._sidebar_collapse_btn.setIcon(
                _nav_icon("chevron-right", color=ACCENT_PRIMARY)
            )
        except Exception:
            pass
        self._sidebar_collapse_btn.setToolTip(t("detail.sidebar.collapse_tip"))
        self._sidebar_collapse_btn.setAccessibleName(t("detail.sidebar.collapse_a11y"))
        self._sidebar_collapse_btn.clicked.connect(self._toggle_sidebar)
        header.addWidget(self._sidebar_collapse_btn)
        self._nav_buttons: list = []
        for key, attr in _SECTION_LINKS:
            label = t(key)
            btn = make_action_button(label, kind="link", size=None)
            try:
                btn.setIcon(_nav_icon("arrow-right", color=ACCENT_PRIMARY))
            except Exception:
                pass
            btn.clicked.connect(lambda _c, a=attr: self._goto_section(a))
            body.addWidget(btn)
            self._nav_buttons.append(btn)
        return card

    # ---- Response page (second page per dataset) ---------------------------
    def _build_response_page(self) -> QWidget:
        # Scroll-wrapped so the page's own minimum stays small: the stacked
        # layout takes the max of all page minimums, and the editors below
        # (240 + 280 px) used to force the main window taller on first open.
        outer = QWidget()
        outer.setObjectName("DetailResponsePage")
        outer_lay = QVBoxLayout(outer)
        outer_lay.setContentsMargins(0, 0, 0, 0)
        outer_lay.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer_lay.addWidget(scroll)
        page = QWidget()
        page.setObjectName("DetailResponseInner")
        scroll.setWidget(page)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(24, 12, 24, 24)
        lay.setSpacing(12)

        intro = make_small_body_label(t("detail.response.intro"))
        lay.addWidget(intro)

        self._response_summary = QLabel(t("detail.response.load_to_build"))
        self._response_summary.setObjectName("StateMD")
        lay.addWidget(self._response_summary)
        # Moved off the old tab row: the response-specific nudge belongs on
        # the Response page, not next to global navigation.
        self._response_hint = QLabel("")
        self._response_hint.setWordWrap(True)
        self._response_hint.setObjectName("HintSM")
        lay.addWidget(self._response_hint)

        # Two columns: findings checklist (left) | editable draft (right).
        cols = QHBoxLayout()
        cols.setSpacing(12)

        findings_card, findings_body, _t, _h = make_card(t("detail.response.findings_card"))
        add_info_tip(
            _h,
            t("detail.response.findings_tip"),
            name=t("detail.response.findings_card"),
        )
        self._response_list = make_list()
        self._response_list.setMinimumHeight(240)
        self._response_list.itemChanged.connect(self._on_response_item_changed)
        findings_body.addWidget(self._response_list, 1)
        cols.addWidget(findings_card, 1)

        draft_card, draft_body, _t2, _h2 = make_card(t("detail.response.draft_card"))
        add_info_tip(
            _h2,
            t("detail.response.draft_tip"),
            name=t("detail.response.draft_a11y"),
        )
        self._response_edit = make_multiline_input(
            t("detail.response.draft_placeholder"),
            min_height=280,
            font_size=FONT_BODY,
        )
        self._response_edit.textChanged.connect(self._on_response_text_edited)
        draft_body.addWidget(self._response_edit, 1)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        # One primary, the rest ghost — equal-weight secondaries read as
        # three peers with no obvious next step (2026-10-02 minor).
        regen = make_action_button(t("detail.response.regenerate"), kind="ghost", size="sm")
        regen.setToolTip(t("detail.response.regenerate_tip"))
        regen.clicked.connect(lambda: self._refresh_response(force=True))
        btn_row.addWidget(regen)
        copy_btn = make_action_button(t("detail.response.copy"), kind="ghost", size="sm")
        copy_btn.clicked.connect(self._on_response_copy)
        btn_row.addWidget(copy_btn)
        export_btn = make_action_button(t("detail.response.export"), kind="primary", size="sm")
        export_btn.setToolTip(t("detail.response.export_tip"))
        export_btn.clicked.connect(self._on_response_export)
        btn_row.addWidget(export_btn)
        btn_row.addStretch(1)
        self._response_dirty_lbl = make_caption_label("", wrap=False)
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
        except Exception:
            pass
        self._refresh_workflow()

    def _show_response_page(self) -> None:
        try:
            self._pages.setCurrentIndex(1)
            self._in_response = True
            self._refresh_response()
        except Exception:
            pass
        self._refresh_workflow()

    def _on_workflow_step(self, key: str) -> None:
        """Navigate the rail only — never run a download, check or export."""
        try:
            if key == "respond":
                self._show_response_page()
                return

            # Review steps: return to the review page first, then scroll.
            self._show_review_page()
            if key == "metadata":
                self._goto_section("_meta_card")
            elif key == "changes":
                self._goto_section("_version_card")
            elif key == "download":
                self._goto_section("_file_card")
                if self._dl_btn is not None:
                    self._dl_btn.setFocus()
            elif key == "checks":
                self._goto_section("_auto_card")
                if self._check_btn is not None:
                    self._check_btn.setFocus()
            elif key == "export":
                if self._report is None:
                    self._set_status(t("detail.workflow.run_checks_first"))
                else:
                    self._set_status(t("detail.workflow.export_hint"))
                if self._history_btn is not None:
                    self._history_btn.setFocus()
        except Exception:
            pass

    def _refresh_workflow(self) -> None:
        """Repaint the rail from flags/counts already in memory (no I/O)."""
        try:
            from ui.workflow import WorkflowInput, derive_workflow

            state = WorkflowInput(
                metadata_loaded=self._metadata is not None,
                changes_loaded=bool(getattr(self, "_changes_loaded", False)),
                inventory_ok=bool(getattr(self, "_inventory_ok", True)),
                staged=int(getattr(self, "_staged_n", 0) or 0),
                total_files=int(getattr(self, "_staged_total", 0) or 0),
                report_ready=self._report is not None,
                exported=bool(getattr(self, "_last_export_path", None)),
                response_open=bool(getattr(self, "_in_response", False)),
                decision_committed=bool(getattr(self, "_decision_committed", False))
                or bool((self._curation or {}).get("label")),
            )
            self._rail.set_workflow(derive_workflow(state))
        except Exception:
            pass
        try:
            self._refresh_verdict()
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
                self._response_summary.setText(t("detail.response.load_to_build"))
            except Exception:
                pass
            return
        if self._response_dirty and not force:
            # Findings may have changed; keep the editor, nudge to regenerate.
            try:
                n = sum(1 for s in (self._response_sections or []) if s.get("included"))
                self._response_hint.setText(
                    t("detail.response.findings_changed", count=n)
                )
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
                dispositions=self._dispositions_map(),
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
                kind = (
                    t("detail.response.kind_metadata")
                    if s.get("kind") == "metadata"
                    else t("detail.response.kind_file_check")
                )
                # Severity raised in the label + colour: errors red,
                # warnings amber (file-check levels from the run, metadata
                # levels from the active ruleset).
                level = str(s.get("level") or "").lower()
                tag = {
                    "error": t("detail.response.level_error"),
                    "warning": t("detail.response.level_warning"),
                    "required": t("detail.response.level_required"),
                    "optional": t("detail.response.level_recommended"),
                }.get(level, level)
                label = t(
                    "detail.response.label_format",
                    kind=kind,
                    tag=t("detail.response.label_tag", tag=tag) if tag else "",
                    label=s.get("label", ""),
                )
                item = QListWidgetItem(label)
                if level == "error":
                    item.setForeground(QColor(TEXT_DANGER))
                elif level == "warning":
                    item.setForeground(QColor(TEXT_AMBER))
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
                self._response_summary.setText(t("detail.response.no_outstanding"))
                self._response_hint.setText("")
            else:
                errors = sum(1 for s in sections if str(s.get("level") or "").lower() == "error")
                warns = sum(1 for s in sections if str(s.get("level") or "").lower() == "warning")
                severity = (
                    t(
                        "detail.response.severity",
                        warnings=warns,
                        errors=errors,
                    )
                    if warns or errors
                    else ""
                )
                self._response_summary.setText(
                    t(
                        "detail.response.included_count",
                        included=n,
                        total=total,
                        severity=severity,
                    )
                )
                self._response_hint.setText(
                    t("detail.response.in_draft", count=n)
                    if n
                    else t("detail.response.excludes_all")
                )
            self._response_dirty_lbl.setText(
                t("detail.response.edited") if self._response_dirty else ""
            )
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
            self._set_status(t("detail.status.response_copied"))
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
            show_warning(
                self,
                t("detail.header.response_tab"),
                t("detail.response.empty_export"),
            )
            return
        try:
            from PySide6.QtWidgets import QFileDialog

            try:
                self._dl_mgr.reports_dir(self._pid).mkdir(parents=True, exist_ok=True)
                start = str(self._dl_mgr.reports_dir(self._pid) / "depositor_response.md")
            except Exception:
                start = "depositor_response.md"
            path, _ = QFileDialog.getSaveFileName(
                self,
                t("detail.response.export_title"),
                start,
                t("detail.response.markdown_filter"),
                options=QFileDialog.DontUseNativeDialog,
            )
        except Exception as exc:
            show_critical(
                self,
                t("detail.header.response_tab"),
                t("detail.response.save_dialog_failed", exc=exc),
            )
            return
        if not path:
            return
        try:
            out = _P(path)
            if out.suffix.lower() != ".md":
                out = out.with_suffix(".md")
            out.write_text(text, encoding="utf-8")
        except Exception as exc:
            show_critical(
                self,
                t("detail.header.response_tab"),
                t("detail.response.write_failed", exc=exc),
            )
            return
        self._save_working_draft()
        self._log_action(
            "response_exported",
            t("detail.status.response_saved_log", name=out.name),
            {"path": str(out)},
        )
        self._set_status(t("detail.status.response_saved", name=out.name))

    def _layout_for(self, name: str, header) -> "TableLayout":
        """Return the persisted-layout controller for a header (one per header).

        TableLayout owns the save/restore/reset contract: it persists
        *user* gestures only, and ignores programmatic changes made inside
        its suppressed() scope (the content fits below).
        """
        layouts = getattr(self, "_table_layouts", None)
        if layouts is None:
            self._table_layouts = layouts = {}
        layout = layouts.get(name)
        if layout is None or layout.header is not header:
            layout = TableLayout(
                self._config.app.workspace,
                name,
                header,
                view=header.parentWidget(),
            )
            layouts[name] = layout
        return layout

    def _track_table_widths(self, name: str, header) -> None:
        """Restore the saved layout for a header, then keep it up to date.

        The controller saves on column resize, column move and sort
        changes -- user gestures only. Sort state restores here (the
        indicator is set on the header); populates re-enable sorting
        afterwards, which re-applies that indicator to fresh rows.
        """
        try:
            layout = self._layout_for(name, header)
            if layout.restore():
                tbl = header.parent()
                if hasattr(tbl, "disable_auto_fit"):
                    tbl.disable_auto_fit()
        except Exception:
            pass

    def _reset_table_view(self, name: str, header) -> bool:
        """Reset a tracked table to its construction view.

        Restores widths/order/visibility/sort. Clears the persisted entry
        so the reset survives restarts. Returns True when a snapshot was
        applied.
        """
        try:
            layout = self._layout_for(name, header)
            ok = layout.reset()
            tbl = header.parent()
            if hasattr(tbl, "enable_auto_fit"):
                tbl.enable_auto_fit()
            return ok
        except Exception:
            return False

    # -- responsive sidebar ------------------------------------------------
    # Below this width the sidebar's 280px squeezes the main column (the
    # File Manifest tree) below a usable width, so it folds away.
    _SIDEBAR_COLLAPSE_BELOW = 1100

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().resizeEvent(event)
        self._sync_sidebar()

    def _sync_sidebar(self) -> None:
        """Fold the sticky sidebar away on a narrow window.

        The user can fold or unfold it by hand; until they do, the width
        decides. The section links move into the top bar's Sections menu
        and the dataset log moves to the bottom of the main column, so
        nothing disappears.
        """
        try:
            if self._sidebar_user_collapsed is None:
                collapsed = self.width() < self._SIDEBAR_COLLAPSE_BELOW
            else:
                collapsed = self._sidebar_user_collapsed
            if collapsed == self._sidebar_collapsed:
                return
            self._sidebar_collapsed = collapsed
            self._side_scroll.setVisible(not collapsed)
            self._sections_btn.setVisible(collapsed)
            self._move_dataset_log(to_sidebar=not collapsed)
        except Exception:
            pass

    def _toggle_sidebar(self) -> None:
        """Fold or unfold the sidebar (the user's choice wins over width)."""
        try:
            self._sidebar_user_collapsed = not self._sidebar_collapsed
            self._sync_sidebar()
        except Exception:
            pass

    def _move_dataset_log(self, to_sidebar: bool) -> None:
        """Park the dataset log in the sidebar, or at the page's foot."""
        card = getattr(self, "_dataset_log_card", None)
        if card is None:
            return
        try:
            if to_sidebar:
                self._main_wrap.removeWidget(card)
                self._side_wrap.addWidget(card, 1)
            else:
                self._side_wrap.removeWidget(card)
                self._main_wrap.addWidget(card)
        except Exception:
            pass

    def _fill_sections_menu(self) -> None:
        """Rebuild the top bar's Sections menu (the folded sidebar's nav)."""
        try:
            self._sections_menu.clear()
            show = self._sections_menu.addAction(t("detail.sidebar.show_action"))
            show.triggered.connect(self._toggle_sidebar)
            self._sections_menu.addSeparator()
            for key, attr in _SECTION_LINKS:
                action = self._sections_menu.addAction(t(key))
                action.triggered.connect(
                    lambda _checked=False, a=attr: self._goto_section(a)
                )
        except Exception:
            pass

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
        card, body, _title, _header = make_card(t("detail.sections.dataset_log"))
        add_info_tip(
            _header,
            t("detail.dataset_log.tip"),
            name=t("detail.sections.dataset_log"),
        )
        self._dataset_log = make_list()
        # Tall timeline: minimum keeps it readable on short screens, the
        # higher maximum + Expanding policy lets it claim the sidebar's
        # free space (the card carries stretch 1 in the sidebar layout).
        self._dataset_log.setMinimumHeight(320)
        self._dataset_log.setMaximumHeight(650)
        self._dataset_log.setSizeAdjustPolicy(QAbstractItemView.AdjustToContentsOnFirstShow)
        self._dataset_log.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self._dataset_log.setWordWrap(True)
        self._dataset_log.setToolTip(t("detail.dataset_log.tip"))
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

    # -- finding dispositions (dv-32x) -------------------------------------

    def _dispositions_map(self) -> dict:
        """{finding_key: {disposition, note}} for this dataset (cached)."""
        cached = getattr(self, "_dispositions_cache", None)
        if isinstance(cached, dict):
            return cached
        out: dict = {}
        try:
            st = self._state()
            if st is not None:
                out = st.list_finding_dispositions(self._pid)
        except Exception:
            out = {}
        self._dispositions_cache = out
        return out

    def _set_disposition(self, key: str, token: str, note: str = "",
                         refresh: bool = False) -> None:
        """Persist one disposition, update the cache, the log, and views."""
        try:
            st = self._state()
            if st is not None:
                st.set_finding_disposition(self._pid, key, token, note or "")
        except Exception:
            return
        cache = getattr(self, "_dispositions_cache", None)
        if isinstance(cache, dict):
            if token:
                cache[key] = {"disposition": token, "note": note or "", "updated_at": ""}
            else:
                cache.pop(key, None)
        self._refresh_finding_summary()
        self._log_action(
            "disposition",
            (disposition_label(token) if token else t("detail.disposition.cleared"))
            + (t("detail.dataset_log.action_notes", notes=(note or "")[:120]) if note else ""),
            {"finding_key": key, "disposition": token},
        )
        if refresh:
            # Reflection surfaces: manifest tint + response exclusion.
            try:
                self._apply_file_filter_internal()
            except Exception:
                pass
            try:
                self._refresh_response(force=False)
            except Exception:
                pass

    def _on_disposition_changed(self, key: str, token: str) -> None:
        """Combo change on an Auto-Checks row: keep the existing note."""
        current = self._dispositions_map().get(key, {})
        self._set_disposition(key, str(token or ""), str(current.get("note") or ""))

    def _on_edit_disposition_note(self, key: str, token: str = "") -> None:
        """Edit (or add) the note stored with one finding's disposition."""
        current = self._dispositions_map().get(key, {})
        existing = str(current.get("note") or "")
        if not token:
            token = str(current.get("disposition") or "")
        text, ok = QInputDialog.getMultiLineText(
            self,
            t("detail.disposition.note_title"),
            t("detail.disposition.note_label"),
            existing,
        )
        if ok:
            self._set_disposition(key, token, text, refresh=True)

    def _show_disposition_menu(self, key: str, global_pos) -> None:
        """Right-click menu for one finding: mark, note, or clear."""
        current = str(self._dispositions_map().get(key, {}).get("disposition") or "")
        menu = QMenu(self)
        for token in ("acknowledged", "fix-requested", "wontfix", "blocked"):
            action = menu.addAction(disposition_label(token))
            action.setCheckable(True)
            action.setChecked(token == current)
            action.triggered.connect(
                lambda _c=False, tok=token: self._set_disposition(key, tok, refresh=True)
            )
        menu.addSeparator()
        note_action = menu.addAction(t("detail.disposition.note_action"))
        note_action.triggered.connect(
            lambda: self._on_edit_disposition_note(key, current)
        )
        clear_action = menu.addAction(t("detail.disposition.clear"))
        clear_action.triggered.connect(lambda: self._set_disposition(key, "", refresh=True))
        menu.exec(global_pos)

    def _on_meta_context_menu(self, pos) -> None:
        """Disposition menu for one metadata rule row (top-level rows only)."""
        tree = self._meta_check_tree
        index = tree.indexAt(pos)
        if not index.isValid():
            return
        while index.parent().isValid():
            index = index.parent()
        results = getattr(self, "_meta_tree_results", [])
        row = index.row()
        if row < 0 or row >= len(results):
            return
        result = results[row]
        if result.get("status") == "complete":
            return
        rule_id = str(result.get("rule_id") or result.get("field") or "")
        requirement = str(result.get("requirement") or "")
        key = finding_key(rule_id, "", requirement or str(result.get("field") or ""))
        self._show_disposition_menu(key, tree.viewport().mapToGlobal(pos))

    def _on_file_context_menu(self, pos) -> None:
        """Disposition menu for one check node in the file manifest tree."""
        tree = self._file_tree
        index = tree.indexAt(pos)
        if not index.isValid():
            return
        model = tree.model()
        item = model.itemFromIndex(index.siblingAtColumn(0)) if model is not None else None
        data = item.data(Qt.UserRole + 1) if item is not None else None
        if not isinstance(data, dict) or data.get("kind") != "check":
            return
        key = finding_key(
            str(data.get("check_id") or ""),
            str(data.get("path") or ""),
            str(data.get("msg") or ""),
        )
        self._show_disposition_menu(key, tree.viewport().mapToGlobal(pos))

    def _set_auto_summary(self, text: str) -> None:
        """Set the Auto-Checks header text, re-applying the roll-up suffix."""
        self._auto_summary_base = text
        self._auto_summary.setText(text + self._disposition_suffix())

    def _disposition_suffix(self) -> str:
        keys = getattr(self, "_finding_keys", [])
        if not keys:
            return ""
        disp = self._dispositions_map()
        tokens = [str(disp.get(k, {}).get("disposition") or "") for k in keys]
        resolved = sum(1 for tok in tokens if tok in RESOLVED_DISPOSITIONS)
        return t("detail.disposition.summary_suffix", resolved=resolved, total=len(tokens))

    def _refresh_finding_summary(self) -> None:
        base = getattr(self, "_auto_summary_base", None)
        if base is None:
            return
        self._auto_summary.setText(base + self._disposition_suffix())

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
                return t("common.em_dash")
            normalized = s.replace("T", " ").replace("Z", "").strip()
            # Drop seconds + fractional/timezone suffixes, keep HH:MM.
            parts = normalized.split()
            if len(parts) >= 2 and len(parts[0]) == 10 and parts[1][:2].isdigit():
                return f"{parts[0]} {parts[1][:5]}"
            if len(s) > 10 and (s[10] in ("T", " ")):
                return s[:16].replace("T", " ")
            return s[:10]

        def _add(ts: Any, text: str) -> None:
            raw = str(ts or "").strip()
            if raw:
                events.append(
                    (
                        raw,
                        t("detail.dataset_log.timeline_format", stamp=_fmt_ts(raw), text=text),
                    )
                )
            else:
                events.append(("0000", t("common.em_dash") + " " + text))

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
                _add(ct, t("detail.dataset_log.version_draft_created", num=num))
            elif state == "DEACCESSIONED":
                _add(rt or ct, t("detail.dataset_log.version_deaccessioned", num=num))
            else:
                if rt:
                    _add(rt, t("detail.dataset_log.version_published", num=num))
                    version_published_days.add(rt[:10])
                if ct and ct[:10] != (rt or "")[:10]:
                    _add(ct, t("detail.dataset_log.version_created", num=num))
        if dated_creations:
            first = sorted(dated_creations)[0]
            events.append(
                (
                    first,
                    t(
                        "detail.dataset_log.timeline_format",
                        stamp=_fmt_ts(first),
                        text=t("detail.dataset_log.first_created"),
                    ),
                )
            )

        # Lifecycle timestamps endpoint (dataset-level record dates).
        ts = self._timestamps if isinstance(self._timestamps, dict) else {}
        ts_created = str(ts.get("createTime") or "")
        if not dated_creations and ts_created:
            # No version dates at all — timestamps are the only source.
            events.append(
                (
                    ts_created,
                    t(
                        "detail.dataset_log.timeline_format",
                        stamp=_fmt_ts(ts_created),
                        text=t("detail.dataset_log.first_created"),
                    ),
                )
            )
        ts_published = str(ts.get("publicationTime") or "")
        if (
            ts_published
            and ts_published[:10] != ts_created[:10]
            and ts_published[:10] not in version_published_days
        ):
            # Only shown when it differs from creation (per curator request)
            # and no version event already covers that day.
            events.append(
                (
                    ts_published,
                    t(
                        "detail.dataset_log.timeline_format",
                        stamp=_fmt_ts(ts_published),
                        text=t("detail.dataset_log.first_published"),
                    ),
                )
            )
        ts_doi = str(ts.get("globalIdCreateTime") or "")
        if ts_doi:
            events.append(
                (
                    ts_doi,
                    t(
                        "detail.dataset_log.timeline_format",
                        stamp=_fmt_ts(ts_doi),
                        text=t("detail.dataset_log.doi_minted"),
                    ),
                )
            )
        ts_touched = str(ts.get("lastUpdateTime") or "")
        if ts_touched:
            events.append(
                (
                    ts_touched,
                    t(
                        "detail.dataset_log.timeline_format",
                        stamp=_fmt_ts(ts_touched),
                        text=t("detail.dataset_log.draft_updated"),
                    ),
                )
            )

        # Review submissions (SUBMITTEDDS inbox notes, PID-matched).
        for sub in self._review_submissions if isinstance(self._review_submissions, list) else []:
            if not isinstance(sub, dict):
                continue
            when = str(sub.get("time") or "")
            dv = str(sub.get("dataverse") or "").strip()
            who = str(sub.get("requestor") or "").strip()
            text = t("detail.dataset_log.submitted_for_review")
            if dv:
                text += t("detail.dataset_log.publish_in", dataset=dv)
            if who:
                text += t("detail.dataset_log.by", who=who)
            if when:
                events.append(
                    (
                        when,
                        t(
                            "detail.dataset_log.timeline_format",
                            stamp=_fmt_ts(when),
                            text=text,
                        ),
                    )
                )
            else:
                events.append(("0000", t("common.em_dash") + " " + text))

        for h in ((self._curation or {}).get("history") or []):
            if not isinstance(h, dict):
                continue
            label = str(h.get("label") or "").strip()
            if not label:
                continue
            who = str(h.get("assigner") or "").strip()
            text = t("detail.dataset_log.curation_label_assigned", label=label)
            if who:
                text += t("detail.dataset_log.by", who=who)
            _add(h.get("time", ""), text)

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
            "downloaded": t("detail.dataset_log.action_downloaded"),
            "checks_run": t("detail.dataset_log.action_checks_run"),
            "checks_saved": t("detail.dataset_log.action_checks_saved"),
            "decision": t("detail.dataset_log.action_decision"),
            "exported": t("detail.dataset_log.action_exported"),
            "response_exported": t("detail.dataset_log.action_response_exported"),
            "disposition": t("detail.dataset_log.action_disposition"),
        }
        for a in actions:
            act = a.get("action") or ""
            if act not in _local_text:
                continue
            notes = (a.get("notes") or "").strip()
            text = _local_text[act] + (
                t("detail.dataset_log.action_notes", notes=notes[:90]) if notes else ""
            )
            _add(a.get("timestamp", ""), text)

        # Embargo / retention dates from the file inventory (as applicable).
        for entry in self._inventory if isinstance(self._inventory, list) else []:
            if not isinstance(entry, dict):
                continue
            path = str(entry.get("path") or "").strip() or t("detail.dataset_log.unnamed_file")
            embargo = str(entry.get("embargo_date") or "").strip()
            if embargo:
                _add(
                    embargo,
                    t(
                        "detail.dataset_log.embargoed",
                        path=path,
                        date=embargo[:10],
                    ),
                )
            retention = str(entry.get("retention") or "").strip()
            if retention:
                _add(
                    retention,
                    t(
                        "detail.dataset_log.retention",
                        path=path,
                        value=retention[:60],
                    ),
                )

        try:
            self._dataset_log.clear()
            if not events:
                self._dataset_log.addItem(t("detail.dataset_log.no_history"))
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
        card, _body_host, _title, header_lay = make_card(t("detail.sections.version_log"))
        add_info_tip(
            header_lay,
            t("detail.version_log.tip"),
            name=t("detail.sections.version_log"),
        )
        # Flush card (manifest-tree pattern): dynamic children are edge to
        # edge and paint their own corners in _populate_version_diff.
        _body_host.setContentsMargins(0, 0, 0, 0)
        _body_host.setSpacing(0)
        # Named not-loaded state, never "—" (2026-10-02 P2).
        self._version_summary = make_field_label(t("detail.version_log.not_loaded"))
        header_lay.addWidget(self._version_summary)
        self._version_reset_btn = make_reset_columns_button(
            "",
            tip=t("detail.version_log.reset_columns_tip"),
            accessible_name=t("detail.version_log.reset_columns_a11y"),
            fallback_text=t("common.reset"),
        )
        self._version_reset_btn.clicked.connect(self._on_reset_version_view)
        header_lay.addWidget(self._version_reset_btn)
        self._version_body = _body_host
        return card

    def _version_placeholder(self, text: str) -> None:
        wrap = QWidget()
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(16, 12, 16, 12)
        ph = make_small_body_label(text)
        lay.addWidget(ph)
        self._version_body.addWidget(wrap)

    @staticmethod
    def _short(value: str, limit: int = 150) -> str:
        s = (value or "").strip()
        return (s[:limit] + "…") if len(s) > limit else (s or t("common.em_dash"))

    def _populate_version_diff(self) -> None:
        """Render the version list plus the published→draft diff."""
        from PySide6.QtWidgets import QListWidgetItem

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
            unknown = t("detail.version_log.date_unknown")
            if state == "DRAFT":
                return (
                    t("detail.version_log.draft_current", date=ct[:10] or unknown),
                    ACCENT_PRIMARY,
                )
            if state == "DEACCESSIONED":
                return (
                    t(
                        "detail.version_log.deaccessioned",
                        num=num,
                        date=(rt or ct)[:10] or unknown,
                    ),
                    TEXT_DANGER,
                )
            if rt:
                return (
                    t("detail.version_log.published", num=num, date=rt[:10]),
                    TEXT_SUCCESS,
                )
            return (
                t("detail.version_log.created", num=num, date=ct[:10] or unknown),
                TEXT_SUBTLE,
            )

        # Version list first (current + all previous)
        if versions:
            vlist = make_list(flush=True, last=True)
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
            self._version_summary.setText(t("detail.version_log.not_loaded"))
            self._version_placeholder(t("detail.version_log.comparison_placeholder"))
            return
        else:
            # Metadata loaded but no version history came back: first version.
            initial = QListWidgetItem(t("detail.version_log.initial_draft"))
            initial.setToolTip(t("detail.version_log.initial_draft_tip"))
            initial.setForeground(QColor(ACCENT_PRIMARY))
            vlist = make_list(flush=True, last=True)
            vlist.setMaximumHeight(56)
            vlist.addItem(initial)
            self._version_body.addWidget(vlist)
            flush_widgets.append((vlist, "list"))

        n_versions = len(versions) if versions else 1
        if not diff:
            self._version_summary.setText(
                t("detail.version_log.version_count", count=n_versions)
            )
            _apply_flush_corners()
            return
        old_num = (diff.get("old") or {}).get("number") or "published"
        total = int(diff.get("total_changes") or 0)
        meta = diff.get("metadata_changes") or []
        terms = diff.get("terms_changes") or []
        self._version_summary.setText(
            t(
                "detail.version_log.version_count_changes",
                count=n_versions,
                old=old_num,
                changes=total,
            )
        )
        if total == 0:
            self._version_placeholder(
                t("detail.version_log.no_changes", num=old_num)
            )
            return
        # Metadata + terms field changes
        rows = [(c.get("field", ""), c.get("block", ""), c.get("old", ""), c.get("new", "")) for c in meta]
        rows += [
            (
                t("detail.version_log.terms_row", field=c.get("field", "")),
                t("detail.version_log.terms_of_access"),
                c.get("old", ""),
                c.get("new", ""),
            )
            for c in terms
        ]
        if rows:
            table = AppTable(
                [
                    t("detail.version_log.col_field"),
                    t("detail.version_log.col_previous", num=old_num),
                    t("detail.version_log.col_new"),
                ],
                widths={0: 190, 1: 220, 2: 220},
                row_height=30,
            )
            table.setSortingEnabled(False)
            table.setRowCount(len(rows))
            self._track_table_widths("dataset_version", table.horizontalHeader())
            table.setMaximumHeight(260)
            for r, (field, block, old_v, new_v) in enumerate(rows):
                f_item = QTableWidgetItem(field)
                f_item.setToolTip(
                    t("detail.version_log.field_tooltip", block=block, field=field)
                    if block
                    else field
                )
                o_item = QTableWidgetItem(self._short(old_v))
                o_item.setToolTip(old_v or t("common.em_dash"))
                n_item = QTableWidgetItem(self._short(new_v))
                n_item.setToolTip(new_v or t("common.em_dash"))
                n_item.setForeground(QColor(ACCENT_PRIMARY))
                table.setItem(r, 0, f_item)
                table.setItem(r, 1, o_item)
                table.setItem(r, 2, n_item)
            table.setSortingEnabled(True)
            table.fit_columns_to_content()
            self._version_body.addWidget(table)
            flush_widgets.append((table, "table"))
        # File changes
        def _fname(f: dict) -> str:
            path, name = (f.get("path") or "").strip(), (f.get("name") or "").strip()
            if path and name:
                return f"{path}/{name}"
            return name or path or t("detail.dataset_log.unnamed_file")

        from ui.icons import icon as _ver_icon

        entries: list[tuple[str, str, str, str]] = []
        for f in diff.get("files_added") or []:
            entries.append(
                (t("detail.version_log.file_added", file=_fname(f)), TEXT_SUCCESS, STATE_SUCCESS_GRAPHIC, "plus")
            )
        for f in diff.get("files_removed") or []:
            entries.append(
                (t("detail.version_log.file_removed", file=_fname(f)), TEXT_DANGER, STATE_ERROR_GRAPHIC, "minus")
            )
        for pair in diff.get("files_replaced") or []:
            old_f, new_f = pair.get("old") or {}, pair.get("new") or {}
            entries.append(
                (
                    t(
                        "detail.version_log.file_replaced",
                        old=_fname(old_f),
                        new=_fname(new_f),
                    ),
                    TEXT_AMBER,
                    STATE_WARNING_GRAPHIC,
                    "arrow-right-left",
                )
            )
        for fc in diff.get("file_changes") or []:
            for ch in fc.get("changes") or []:
                entries.append(
                    (
                        t(
                            "detail.version_log.file_changed",
                            file=fc.get("file", ""),
                            field=ch.get("field", ""),
                        ),
                        ACCENT_PRIMARY,
                        ACCENT_PRIMARY,
                        "pencil",
                    )
                )
        if entries:
            flist = make_list(flush=True, last=True)
            flist.setMaximumHeight(min(140, 28 + 24 * len(entries)))
            for text, color, icon_color, icon_name in entries:
                item = QListWidgetItem(text)
                item.setToolTip(text)
                item.setForeground(QColor(color))
                try:
                    item.setIcon(_ver_icon(icon_name, color=icon_color))
                except Exception:
                    pass
                flist.addItem(item)
            self._version_body.addWidget(flist)
            flush_widgets.append((flist, "list"))
        _apply_flush_corners()

    def _build_file_manifest_card(self) -> QFrame:
        card, _body_unused, _title, header_lay = make_card(t("detail.sections.file_manifest"))
        add_info_tip(
            header_lay,
            t("detail.files.tip"),
            name=t("detail.sections.file_manifest"),
        )
        _body_unused.setContentsMargins(0, 0, 0, 0)
        _body_unused.setSpacing(0)
        self._open_folder_btn = make_action_button(t("detail.files.open_folder"), kind="secondary", size="md")
        self._open_folder_btn.setToolTip(t("detail.files.open_folder_tip"))
        self._open_folder_btn.clicked.connect(self._on_open_folder)
        header_lay.addWidget(self._open_folder_btn)
        # Expand/Collapse all toggle for the folder > file > check tree.
        self._expand_btn = make_action_button(t("detail.files.expand_all"), kind="secondary", size="md")
        self._expand_btn.setToolTip(t("detail.files.expand_tip"))
        self._expand_btn.clicked.connect(self._on_toggle_expand_all)
        header_lay.addWidget(self._expand_btn)
        lay = QVBoxLayout()
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # The filters live on their own row under the card's title bar.
        # Packed into the title row - title, tip, Open folder, Expand all,
        # the filter box, the status combo and the reset button - the card
        # needed 742px, wider than the column it sits in, so the page
        # scrolled sideways at the app's own 960px minimum width.
        tools = QWidget()
        tools.setObjectName("FileManifestTools")
        tools.setStyleSheet(transparent_surface_qss("FileManifestTools"))
        tools_lay = QHBoxLayout(tools)
        tools_lay.setContentsMargins(16, 8, 16, 8)
        tools_lay.setSpacing(8)
        self._file_filter = make_search_field(
            t("detail.files.filter_placeholder"), height=36, min_width=140
        )
        self._file_filter.setAccessibleName(t("detail.files.filter_placeholder"))
        self._file_filter.textChanged.connect(self._on_file_filter)
        tools_lay.addWidget(self._file_filter, 1)
        self._scan_filter = make_combo(
            [(label, key) for label, key in [
                (t("detail.files.filter_all"), "all"),
                (t("detail.files.filter_issues"), "issues"),
                (t("detail.files.filter_errors"), "errors"),
                (t("detail.files.filter_warnings"), "warnings"),
                (t("detail.files.filter_skipped"), "skipped"),
                (t("detail.files.filter_clean"), "clean"),
                (t("detail.files.filter_no_check"), "unchecked"),
            ]],
            height=36,
            min_width=130,
        )
        self._scan_filter.currentIndexChanged.connect(lambda _i: self._apply_file_filter_internal())
        tools_lay.addWidget(self._scan_filter)
        # Reset columns button - restores default widths/order
        self._file_reset_btn = make_reset_columns_button(
            "",
            tip=t("detail.files.reset_columns_tip"),
            accessible_name=t("detail.files.reset_columns_a11y"),
            fallback_text=t("common.reset"),
        )
        self._file_reset_btn.clicked.connect(self._on_reset_file_view)
        tools_lay.addWidget(self._file_reset_btn)
        lay.addWidget(tools)
        # NOTE: tree + footer live in a flush sub-layout so the header keeps
        # its top radius and the footer keeps its bottom radius.
        card.layout().addLayout(lay)

        # Tree: folder > file > check hierarchy (Carbon-inspired, native QTreeView).
        # Column 0 carries the tree (caret + indent + icons); Size/Format/Scan
        # mirror the old table columns. Check nodes show the full untruncated
        # message; details live in the tooltip.
        # AppTree: the standard header chrome (square top-left flush with the
        # card's top bar, transparent scrollbar lanes so the vertical
        # scrollbar starts below the header row, themed header sections).
        self._file_tree = AppTree(row_height=30, flush=True)
        self._file_tree.clicked.connect(self._on_tree_clicked)
        self._file_tree.expanded.connect(self._on_tree_expansion_changed)
        self._file_tree.collapsed.connect(self._on_tree_expansion_changed)
        # Right-click a check node to set its disposition (dv-32x).
        self._file_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self._file_tree.customContextMenuRequested.connect(
            self._on_file_context_menu
        )
        # No internal scrollbars: the manifest card grows to fit every
        # visible row and the page canvas scrolls instead.
        self._file_tree.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._file_tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        lay.addWidget(self._file_tree, 1)
        # Compat alias: old code paths referenced _file_table; keep a None
        # placeholder so stray attribute access fails loudly, not silently.
        self._file_table = None

        # Footer: showing X of Y + total size
        footer = QFrame()
        footer.setStyleSheet(band_qss(SURFACE_PAGE, SURFACE_SUBTLE, edge="top"))
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(16, 10, 16, 10)
        # Both footer labels elide: "No files yet - load metadata to see
        # the Dataverse file list." is a long sentence, and a label that
        # cannot wrap would set the card's minimum width for the whole
        # card (the page then scrolls sideways).
        self._file_footer_left = make_elided_label(
            t("detail.files.no_files"), object_name="BodySM"
        )
        fl.addWidget(self._file_footer_left, 1)
        fl.addStretch()
        self._file_footer_right = make_small_body_label("", wrap=False)
        fl.addWidget(self._file_footer_right, 0)
        lay.addWidget(footer)

        # Hidden checks list for compatibility (was QListWidget; now we show inline)
        # Keep _file_checks as simple list for optional advanced view
        self._file_checks_data: dict[str, list] = {}
        return card

    # ---- Helpers ----
    def _set_status(self, msg: str) -> None:
        self._status.setText(msg)
        self._status.setVisible(bool(msg))

    @staticmethod
    def _dress_pill(pill: QLabel, text: str, label: str) -> None:
        """Re-dress a status pill in the badge face its label wears.

        The kit builds the badge; when the words change, the face comes
        from the kit too - so the pill cannot end up wearing a
        different face from the one it started with.
        """
        set_badge_label(pill, text, label=label)

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
        # label via the kit's badge face, DOI-badge chrome)
        _pill_name, pill_text = _pill_state(version_state, getattr(self, "_in_review", False))
        status_pill = getattr(self, "_status_pill", None)
        if status_pill is not None:
            self._dress_pill(status_pill, pill_text, pill_text)
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
                        depositor = name or t("common.em_dash")
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
            depositor_lbl.setText(
                t("detail.header.submitted_by", depositor=depositor)
                if depositor
                else f"{self._pid}"
            )
            date = (latest.get("createTime") or latest.get("lastUpdateTime") or "")[:10]
            if date:
                depositor_lbl.setText(
                    depositor_lbl.text()
                    + t("detail.header.depositor_date", date=date)
                )
        url = f"{self._config.dataverse.base_url}/dataset.xhtml?persistentId={self._pid}" + ("&version=DRAFT" if version_state == "DRAFT" else "")
        header_link = getattr(self, "_header_link", None)
        if header_link is not None:
            link_text = (
                t("detail.header.open_link_draft")
                if version_state == "DRAFT"
                else t("detail.header.open_link")
            )
            header_link.setText(
                f"<a href='{url}' style='color:{ACCENT_PRIMARY}; text-decoration:none;'>{link_text}</a>"
            )
        title_lbl = getattr(self, "_title_lbl", None)
        if title_lbl is not None:
            title_lbl.setText(self._title)

    def _update_curation_pill(self) -> None:
        """Show the Dataverse curation label (if any) next to the status pill."""
        label = ""
        tip = t("detail.header.curation_label_tooltip")
        try:
            label = str((self._curation or {}).get("label") or "").strip()
            when = str((self._curation or {}).get("time") or "")[:16].replace("T", " ")
            who = str((self._curation or {}).get("assigner") or "").strip()
            if label and (when or who):
                tip = t(
                    "detail.header.curation_label_set_by",
                    label=label,
                    when=when,
                    who=who,
                ).strip()
        except Exception:
            label = ""
        try:
            if label:
                self._dress_pill(self._curation_pill, label, label)
                self._curation_pill.setToolTip(tip)
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
                self._finding_keys = []
                if self._inventory is not None and len(self._inventory) == 0 and self._metadata is not None:
                    ph = make_small_body_label(t("detail.auto_checks.no_files_in_dataverse"))
                    # A measured zero, not a placeholder — name it (2026-10-02 P2).
                    self._set_auto_summary(t("detail.auto_checks.no_file_checks"))
                else:
                    ph = make_small_body_label(t("detail.auto_checks.no_file_list"))
                    self._set_auto_summary(t("detail.auto_checks.not_run"))
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
                self._set_auto_summary(
                    t(
                        "detail.auto_checks.summary_counts",
                        passed=summary["passed"],
                        warnings=summary["failed-warning"],
                        errors=summary["failed-error"],
                        skipped=summary["skipped"],
                    )
                )
                from engine.status import classify

                # Findings carry a stable disposition key (dv-32x): failed
                # rows get an inline disposition combo; passes/skips don't.
                finding_keys: list[str] = []
                for c in self._report.dataset_checks:
                    kind = classify(c)
                    key = (
                        finding_key(c.check_id, "", c.message)
                        if kind in ("failed-error", "failed-warning")
                        else ""
                    )
                    if key:
                        finding_keys.append(key)
                    row = self._auto_row(
                        c.check_id, c.message, c.passed, c.level, disposition_key=key
                    )
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
                file_findings = [
                    (f, c)
                    for f in self._report.files
                    for c in f.checks
                    if classify(c) in ("failed-error", "failed-warning", "skipped")
                ]
                for f, c in file_findings:
                    kind = classify(c)
                    desc = t(
                        "detail.auto_checks.file_result_format",
                        path=f.path,
                        message=c.message,
                    )
                    if kind == "skipped":
                        row = self._auto_row(
                            c.check_id,
                            desc,
                            True,
                            "warning",
                            badge=t("status.badges.skipped"),
                        )
                    else:
                        key = finding_key(c.check_id, f.path, c.message)
                        finding_keys.append(key)
                        row = self._auto_row(
                            c.check_id, desc, c.passed, c.level, disposition_key=key
                        )
                    try:
                        from ui.checks_tree import format_details_tooltip

                        row.setToolTip(format_details_tooltip(c))
                    except Exception:
                        pass
                    self._auto_body.addWidget(row)
                self._finding_keys = finding_keys
                self._refresh_finding_summary()
                if (
                    not self._report.dataset_checks
                    and not file_findings
                    and not any(f.checks for f in self._report.files)
                ):
                    ok = QLabel(t("detail.auto_checks.all_passed"))
                    ok.setObjectName("AccentSM")
                    self._auto_body.addWidget(ok)
            else:
                # Only checks that will actually run for this dataset's
                # files (checks with no matching files are not listed).
                self._finding_keys = []
                self._set_auto_summary(t("detail.auto_checks.will_run", count=will))
                if not will:
                    ph = make_small_body_label(t("detail.auto_checks.no_matching_checks"))
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
                            missing = t("detail.auto_checks.missing_pip", package=pip_pkg)
                    status = missing or t("detail.auto_checks.will_run_badge")
                    # Interpret for row styling: missing = warn, else pass tone
                    if missing:
                        row = self._auto_row(
                            p["check_id"],
                            p["description"],
                            False,
                            "warning",
                            badge=t("detail.auto_checks.badge_missing"),
                        )
                    else:
                        row = self._auto_row(
                            p["check_id"],
                            p["description"],
                            True,
                            "info",
                            badge=t("detail.auto_checks.badge_pass"),
                        )
                    # Add subtitle with file_types + status
                    row.setToolTip(f"{p['description']}\n\n{status}")
                    self._auto_body.addWidget(row)
        except Exception:
            pass
        try:
            selectable_labels(self._auto_card)
        except Exception:
            pass

    def _auto_row(self, check_id: str, desc: str, passed: bool, level: str, badge: str | None = None,
                  disposition_key: str = "") -> QFrame:
        frame = QFrame()
        # Scope the row face to the row itself. A bare `QFrame` selector
        # would also style every QLabel inside it (QLabel subclasses
        # QFrame), drawing a rounded box around each line of text.
        frame.setObjectName("AutoCheckRow")
        # Explicit SKIPPED (warning+passed with "Missing"/"skipped" wording)
        # renders grey so it is never confused with a real pass.
        from ui.icons import icon_label as _icon_label

        if passed and level == "warning" and (
            (badge or "").upper() in ("SKIPPED", "MISSING")
            or "skipped" in (badge or desc).lower()
            or "not executed" in desc.lower()
            or "Missing" in (badge or desc)
        ):
            frame.setStyleSheet(surface_frame_qss(SURFACE_SUBTLE, BORDER_SUBTLE, selector="QFrame#AutoCheckRow"))
            icon_name, icon_color = "circle-dashed", TEXT_MUTED
            badge_text = (
                t("status.badges.skipped")
                if "SKIP" in (badge or "").upper() or "skipped" in desc.lower()
                else (badge or t("status.badges.warning"))
            )
            badge_bg = SURFACE_ALT
            badge_fg = TEXT_MUTED
        elif not passed and level in ("error", "warning"):
            frame.setStyleSheet(surface_frame_qss(STATE_ERROR_BG, STATE_ERROR_BORDER, selector="QFrame#AutoCheckRow"))
            icon_name, icon_color = (
                ("octagon-x", STATE_ERROR_GRAPHIC) if level == "error"
                else ("octagon-alert", STATE_WARNING_GRAPHIC)
            )
            badge_text = badge or t("status.badges.error")
            badge_bg = STATE_ERROR_BG
            badge_fg = STATE_ERROR_TEXT
        elif passed and level == "warning" and "Missing" in (badge or desc):
            frame.setStyleSheet(surface_frame_qss(STATE_ERROR_SURFACE, STATE_ERROR_BORDER, selector="QFrame#AutoCheckRow"))
            icon_name, icon_color = "octagon-alert", STATE_WARNING_GRAPHIC
            badge_text = badge or t("status.badges.warning")
            badge_bg = STATE_ERROR_BG
            badge_fg = STATE_ERROR_TEXT
        elif passed:
            frame.setStyleSheet(surface_frame_qss(SURFACE_TINT, BORDER_SUBTLE, selector="QFrame#AutoCheckRow"))
            icon_name, icon_color = "check", ACCENT_PRIMARY
            badge_text = badge or t("status.badges.passed")
            badge_bg = ACCENT_PRIMARY
            badge_fg = TEXT_ON_ACCENT
        else:
            frame.setStyleSheet(surface_frame_qss(SURFACE_TINT, BORDER_SUBTLE, selector="QFrame#AutoCheckRow"))
            icon_name, icon_color = "minus", TEXT_MUTED
            badge_text = badge or t("common.em_dash")
            badge_bg = SURFACE_ALT
            badge_fg = TEXT_MUTED
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(8)
        lay.addWidget(_icon_label(icon_name, size=16, color=icon_color))
        txt = QVBoxLayout()
        txt.setSpacing(1)
        cid = QLabel(check_id)
        cid.setObjectName("LabelStrongSM")
        txt.addWidget(cid)
        d = make_caption_label(desc)
        txt.addWidget(d)
        lay.addLayout(txt, 1)
        # Inline disposition controls for findings (dv-32x): the combo
        # writes through _on_disposition_changed; Note… edits the stored
        # note (tooltip carries it once one exists).
        if disposition_key:
            current = self._dispositions_map().get(disposition_key, {})
            token = str(current.get("disposition") or "")
            note = str(current.get("note") or "")
            combo = make_disposition_combo(
                token,
                on_change=lambda tok, k=disposition_key: self._on_disposition_changed(k, tok),
            )
            lay.addWidget(combo)
            note_btn = make_action_button(
                t("detail.disposition.note_action"), kind="ghost", size="sm"
            )
            if note:
                note_btn.setToolTip(note)
            note_btn.clicked.connect(
                lambda _c=False, k=disposition_key: self._on_edit_disposition_note(k)
            )
            lay.addWidget(note_btn)
        badge_lbl = make_badge(
            badge_text,
            background=badge_bg,
            foreground=badge_fg,
            border=BORDER_SUBTLE,
        )
        badge_lbl.setAlignment(Qt.AlignCenter)
        badge_lbl.setFixedHeight(20)
        badge_lbl.setMinimumWidth(56)
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
                        t(
                            "detail.status.inventory_summary",
                            count=len(self._all_file_rows),
                            staged=n_staged,
                            path=staged,
                        )
                    )
            except Exception:
                pass
        elif staged.exists():
            files = sorted(p for p in staged.rglob("*") if p.is_file())
            self._populate_file_table_staged(files)
            self._set_status(
                t("detail.status.staged", count=len(files), path=staged)
            )
        else:
            from ui.checks_tree import build_tree_model

            self._file_tree.setModel(build_tree_model([], None))
            self._file_footer_left.setText(t("detail.files.no_files_hint"))
            self._file_footer_right.setText("")
        self._refresh_curation_preview()
        self._refresh_workflow()

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
            self._dl_btn.setText(t("detail.files.downloaded", count=len(files)))
            self._dl_btn.setToolTip(t("detail.files.downloaded_tip"))
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
        # Rail inputs: counts are captured here (the single place that
        # already walks the staged folder) so _refresh_workflow never stats.
        self._staged_n = 0
        self._staged_total = 0
        try:
            btn = getattr(self, "_dl_btn", None)
            if btn is None:
                self._refresh_workflow()
                return
            rows = getattr(self, "_all_file_rows", []) or []
            if not rows:
                btn.setText(t("detail.header.download_all"))
                btn.setToolTip(t("detail.files.download_tip"))
                self._refresh_workflow()
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
            self._staged_n = n_staged
            self._staged_total = total
            # Header grammar: text-only major action in every state; the
            # count in the label ("Downloaded (N)") is the status cue.
            if total and n_staged >= total:
                btn.setText(t("detail.files.downloaded", count=total))
                btn.setToolTip(t("detail.files.all_staged_tip"))
            elif n_staged:
                btn.setText(
                    t(
                        "detail.files.download_all_staged",
                        staged=n_staged,
                        total=total,
                    )
                )
                btn.setToolTip(
                    t(
                        "detail.files.staged_tip",
                        staged=n_staged,
                        total=total,
                    )
                )
            else:
                btn.setText(t("detail.header.download_all"))
                btn.setToolTip(t("detail.files.download_tip"))
        except Exception:
            pass
        self._refresh_workflow()

    def _on_open_folder(self) -> None:
        """Open the staged download folder in the desktop file explorer."""
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        staged = self._dl_mgr.files_dir(self._pid)
        target = staged if staged.exists() else self._dl_mgr.dataset_dir(self._pid)
        if not target.exists():
            show_info(
                self,
                t("detail.files.open_folder"),
                t("detail.files.open_folder_nothing"),
            )
            return
        try:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target.resolve())))
        except Exception as exc:
            show_warning(
                self,
                t("detail.files.open_folder"),
                t("detail.files.could_not_open", path=target, exc=exc),
            )

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
                return t("detail.files.not_in_report")
            if not entry.checks:
                return t("detail.files.no_automated_check")

            return status_text(entry.checks)

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
            dispositions=self._dispositions_map(),
        )
        # The header's signals are blocked while the tree is rebuilt and
        # the columns are fitted to their content: sectionResized persists
        # the layout, so an auto-fit would overwrite the widths the user
        # saved before the restore below can apply them.
        layout = self._layout_for("dataset_files", self._file_tree.header())
        with layout.suppressed():
            try:
                self._file_tree.setModel(model)
                self._file_tree.expandToDepth(0)
                # Auto-expand files with issues so findings are visible.
                issue_prefixes = (t("status.error"), t("status.warning"))
                for r in range(model.rowCount()):
                    folder = model.item(r, 0)
                    if folder is not None and folder.hasChildren():
                        for i in range(folder.rowCount()):
                            scan = folder.child(i, 3).text() if folder.child(i, 3) else ""
                            if scan.startswith(issue_prefixes):
                                idx = model.index(i, 0, model.index(r, 0))
                                self._file_tree.expand(idx)
                    else:
                        scan = model.item(r, 3).text() if model.item(r, 3) else ""
                        if scan.startswith(issue_prefixes):
                            self._file_tree.expand(model.index(r, 0))
                # Size every column to its content (Name keeps a 260px
                # floor; Size/Format/Scan need real width too, or long
                # formats like application/x-spss-sav get truncated).
                self._file_tree.fit_columns_to_contents(floors={0: 260})
                self._sync_tree_carets()
            except Exception:
                pass
        total = sum(r[1] for r in all_rows)
        self._file_footer_left.setText(
            t(
                "detail.files.showing",
                shown=len(rows),
                total=len(all_rows),
            )
        )
        self._file_footer_right.setText(
            t("detail.files.total_size", size=_human_size(total)) if total else ""
        )
        self._refresh_download_state()
        self._update_expand_btn()
        # Re-apply the saved layout (the user's widths win over the fit).
        self._track_table_widths("dataset_files", self._file_tree.header())
        self._fit_file_tree_height()

    def _on_tree_expansion_changed(self, _index=None) -> None:
        self._sync_tree_carets()
        self._update_expand_btn()
        self._fit_file_tree_height()

    def _fit_file_tree_height(self) -> None:
        """Grow the manifest tree to its visible rows (no inner scroll).

        The tree lives on the page's scroll canvas, so an inner scrollbar
        only traps the wheel. Every expanded row contributes its 30px
        row height plus the header band.
        """
        try:
            tree = self._file_tree
            model = tree.model()
            visible_rows = 0
            if model is not None:
                stack = [tree.rootIndex()]
                while stack:
                    parent = stack.pop()
                    count = model.rowCount(parent)
                    visible_rows += count
                    for r in range(count):
                        idx = model.index(r, 0, parent)
                        if model.hasChildren(idx) and tree.isExpanded(idx):
                            stack.append(idx)
            row_h = 30
            header_h = tree.header().height() or 30
            tree.setFixedHeight(max(80, header_h + visible_rows * row_h + 2))
        except Exception:
            pass

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
                t("detail.files.collapse_all")
                if not self._tree_has_collapsed()
                else t("detail.files.expand_all")
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
            self._fit_file_tree_height()
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
        # The worker deletes itself (deleteLater) when it finishes or
        # errors, which can leave a stale Python reference to a dead C++
        # object; calling isRunning() on it raised
        # "Internal C++ object already deleted". Drop the stub instead.
        worker = self._meta_worker
        if worker is not None:
            try:
                if worker.isRunning():
                    self._set_status(t("detail.status.metadata_load_running"))
                    return
            except RuntimeError:
                self._meta_worker = None
        self._load_meta_btn.setEnabled(False)
        self._set_status(t("detail.status.loading_metadata"))
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
        # Drop the reference before the worker's deleteLater runs; a stale
        # reference made the next Load metadata click crash with
        # "Internal C++ object (MetadataWorker) already deleted".
        self._meta_worker = None
        self._progress.setVisible(False)
        self._load_meta_btn.setEnabled(True)
        self._inventory = inventory if isinstance(inventory, list) else []
        self._metadata = metadata
        self._curation = curation if isinstance(curation, dict) else {}
        self._version_diff = version_diff if isinstance(version_diff, dict) else {}
        self._changes_loaded = True
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
        self._inventory_ok = not inv_failed
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
            t("detail.status.inventory_count", count=len(self._inventory))
            if not inv_failed
            else t("detail.status.file_list_failed_short"),
            {"file_count": len(self._inventory)},
        )
        if inv_failed:
            # Network/auth failure is not an empty dataset — say so plainly
            # and offer the retry instead of implying zero files.
            from ui.checks_tree import build_tree_model as _btm

            self._set_status(t("detail.status.file_list_failed"))
            self._file_tree.setModel(_btm([], None))
            self._all_file_rows = []
            self._file_footer_left.setText(t("detail.status.file_list_failed_footer"))
            self._file_footer_right.setText("")
        elif self._inventory:
            self._populate_from_inventory()
            self._set_status(
                t(
                    "detail.status.metadata_loaded",
                    count=len(self._inventory),
                )
            )
        else:
            # Metadata loaded fine but the version genuinely has zero files —
            # say so plainly instead of implying a fetch failure.
            version_state = ""
            try:
                version_state = ((metadata.get("latestVersion") or {}).get("versionState") or "").upper()
            except Exception:
                pass
            ver_note = (
                t("detail.status.version_note", version=version_state.title())
                if version_state
                else ""
            )
            self._set_status(t("detail.status.no_files_version", version=ver_note))
            from ui.checks_tree import build_tree_model as _btm2

            self._file_tree.setModel(_btm2([], None))
            self._all_file_rows = []
            self._file_footer_left.setText(t("detail.files.no_files_in_dataverse"))
            self._file_footer_right.setText("")
        self._refresh_workflow()

    def _on_profile_changed(self) -> None:
        key = self._profile_combo.currentData()
        if isinstance(key, str):
            self._profile = key
        if self._metadata is not None:
            self._populate_completeness(self._metadata)

    def _on_reset_meta_view(self) -> None:
        try:
            self._reset_table_view(
                "dataset_meta", self._meta_check_tree.header()
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
                 "value": r.get("value", t("common.em_dash")), "status": r["status"],
                 "block": r.get("block", "") or "",
                 "name": r.get("name", "") or "",
                 "rule_id": r.get("rule_id", "") or r["field"]}
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
        color = TEXT_SUCCESS if complete == total else TEXT_AMBER if complete > total / 2 else TEXT_DANGER
        # Header carries just the count (profile name is already visible in
        # the header combo; the old in-body summary line was removed).
        self._meta_summary.setText(
            t(
                "detail.metadata_check.fields_complete_html",
                color=color,
                complete=complete,
                total=total,
            )
        )
        # Auto-checks header belongs to the checks summary (see
        # _refresh_curation_preview); leave it alone once a report exists.
        if self._report is None:
            self._set_auto_summary(
                t(
                    "detail.metadata_check.fields_complete",
                    complete=complete,
                    total=total,
                )
            )
        # Full per-check tree: Check | Block | Value | Status (requirement
        # in the Check cell's tooltip). Repeatable fields grow child rows
        # per entry and grandchild rows per subfield.
        self._meta_results = results
        # Apply the active Complete/Incomplete filter; it rebuilds the tree
        # and refits the card height to the visible rows (no inner scroll).
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
        self._raw_btn.setText(
            t("detail.header.hide_raw_metadata")
            if vis
            else t("detail.header.show_raw_metadata")
        )
        try:
            self._raw_btn.setIcon(
                _icon("chevron-up" if vis else "chevron-right")
            )
        except Exception:
            pass

    def _on_metadata_error(self, msg: str) -> None:
        self._meta_worker = None
        self._progress.setVisible(False)
        self._load_meta_btn.setEnabled(True)
        self._set_status("")
        headline, details = describe_error(msg)
        show_critical(self, t("detail.metadata_load.title"), headline, details=details,
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
        return [
            t("detail.decision.option_approve"),
            t("detail.decision.option_revisions"),
            t("detail.decision.option_reject"),
            t("detail.decision.option_hold"),
        ], False

    def _refresh_decision_options(self) -> None:
        try:
            current = self._decision_combo.currentText()
        except Exception:
            current = ""
        try:
            self._decision_combo.blockSignals(True)
            self._decision_combo.clear()
            options, from_labels = self._decision_choices()
            self._decision_combo.addItem(t("detail.decision.placeholder"), None)
            for opt in options:
                self._decision_combo.addItem(opt, opt)
            idx = self._decision_combo.findText(current)
            self._decision_combo.setCurrentIndex(idx if idx > 0 else 0)
            tip = (
                t("detail.decision.instance_labels_tip")
                if from_labels
                else t("detail.decision.generic_states_tip")
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
            t("detail.decision.option_approve"): t("detail.decision.consequence_approve"),
            t("detail.decision.option_revisions"): t("detail.decision.consequence_revisions"),
            t("detail.decision.option_reject"): t("detail.decision.consequence_reject"),
            t("detail.decision.option_hold"): t("detail.decision.consequence_hold"),
        }
        text = known.get(
            choice,
            t("detail.decision.consequence_generic", choice=choice),
        )
        if from_labels:
            text += t("detail.decision.also_set_label")
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
                    help_lbl.setText(t("detail.decision.pick_action"))
            commit = getattr(self, "_commit_btn", None)
            if commit is not None:
                commit.setEnabled(bool(choice))
        except Exception:
            pass

    # -- assessment commit --
    def _confirm_remote_write(self, decision: str) -> bool:
        """Ask before writing the decision to Dataverse. Defaults to No.

        A decision drawn from the instance's curation labels is not a
        local note: it changes the dataset on the server, for everyone.
        The curator confirms that explicitly before anything is written
        or logged.
        """
        try:
            return confirm(
                self,
                t("detail.decision.confirm_remote_title"),
                t(
                    "detail.decision.confirm_remote_body",
                    decision=decision,
                    pid=self._pid,
                ),
                confirm_label=t("detail.decision.confirm_remote_yes"),
            )
        except Exception:
            return False

    def _on_commit(self) -> None:
        decision = self._decision_combo.currentData()
        if not isinstance(decision, str) or not decision:
            show_warning(
                self,
                t("detail.decision.title"),
                t("detail.decision.select_state"),
            )
            return
        _options, from_labels = self._decision_choices()
        # The gate: a remote write asks first, and the answer decides
        # whether anything at all happens - no log entry, no workflow
        # step, no push.
        if from_labels and not self._confirm_remote_write(decision):
            return
        notes = self._notes_edit.toPlainText().strip()
        msg = t("detail.decision.decision_prefix", decision=decision)
        if notes:
            msg += t("detail.decision.notes", notes=notes)
        if self._report is not None:
            msg += t(
                "detail.decision.report_findings",
                count=len(self._report.files),
            )
        self._log_action(
            "decision",
            f"{decision}"
            + (t("detail.decision.log_notes", notes=notes[:200]) if notes else ""),
            {"decision": decision, "notes": notes[:2000]},
        )
        # A recorded decision closes the last workflow step (the Dataverse
        # push may still fail; that is surfaced by the dialog below).
        self._decision_committed = True
        self._refresh_workflow()
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
                    push_error = t("detail.decision.label_rejected")
            except Exception as exc:
                push_error = str(exc)[:200]
        if from_labels and not pushed:
            show_warning(
                self,
                t("detail.decision.committed_local_only"),
                msg
                + "\n\n"
                + (push_error or t("detail.decision.label_not_set"))
                + t("detail.decision.recorded_in_log"),
            )
        else:
            tail = (
                t("detail.decision.label_set_and_logged")
                if pushed
                else t("detail.decision.recorded_in_log_para")
            )
            show_info(self, t("detail.decision.committed"), msg + tail)

    # -- download / checks -------------------------------------------------
    def _on_download(self) -> None:
        try:
            inventory = self._dl_mgr.inventory(self._pid)
        except Exception as exc:
            show_warning(
                self,
                t("detail.download.title"),
                t("detail.download.inventory_failed", exc=exc),
            )
            return
        quote = DownloadManager.quote_from(inventory, self._pid)
        # Skip the bundle entirely when everything is already staged.
        try:
            missing = self._dl_mgr.missing_files(self._pid, inventory)
        except Exception:
            missing = [t("detail.download.inventory_check_failed")]
        if inventory and not missing:
            ok, problems, warnings = self._dl_mgr.verify(self._pid)
            self._refresh_files_placeholder()
            self._check_btn.setEnabled(True)
            self._check_btn.setToolTip(t("detail.header.run_checks_tip_staged"))
            self._set_status(
                t("detail.download.all_verified_skip", count=len(inventory))
            )
            self._log_action(
                "downloaded",
                t("detail.download.already_staged", count=len(inventory)),
                {"skipped": True},
            )
            if problems or warnings:
                show_warning(
                    self,
                    t("detail.download.title"),
                    t(
                        "detail.download.staged_notes",
                        notes="\n".join((problems + warnings)[:10]),
                    ),
                )
            else:
                show_info(
                    self,
                    t("detail.download.title"),
                    t("detail.download.all_verified_nothing", count=len(inventory)),
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
                        t("detail.download.title"),
                        t("detail.download.guestbook_failed", exc=exc),
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
        self._set_status(t("detail.download.downloading"))
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
        self._dl_worker = None
        self._progress.setVisible(False)
        self._hide_ring()
        self._dl_btn.setEnabled(True)
        ok, problems, warnings = self._dl_mgr.verify(self._pid)
        if problems:
            show_warning(
                self,
                t("detail.download.title"),
                t("detail.download.checksum_problems", problems="\n".join(problems[:10])),
            )
        elif warnings:
            show_info(
                self,
                t("detail.download.title"),
                t("detail.download.downloaded_notes", notes="\n".join(warnings[:10])),
            )
        self._refresh_files_placeholder()
        # Belt-and-braces: staged files exist now, so checks are available.
        self._check_btn.setEnabled(self._dl_mgr.files_dir(self._pid).exists())
        self._check_btn.setToolTip(t("detail.header.run_checks_tip_staged"))
        self._set_status(t("detail.status.downloaded_to", path=staged))
        self._log_action("downloaded", t("detail.status.staged_to", path=staged), {"staged": str(staged), "ok": ok})
        # Staged content may resolve file-content text rules — re-evaluate.
        try:
            if self._metadata is not None:
                self._populate_completeness(self._metadata)
        except Exception:
            pass

    def _on_download_error(self, msg: str) -> None:
        self._dl_worker = None
        self._progress.setVisible(False)
        self._hide_ring()
        self._dl_btn.setEnabled(True)
        self._set_status("")
        headline, details = describe_error(msg)
        show_critical(self, t("detail.download.title"), headline, details=details,
                     retry=self._on_download)

    def _on_download_cancel_click(self) -> None:
        """Ask the worker to stop; stay disabled until it acknowledges."""
        if self._dl_worker is None:
            return
        self._dl_cancel_btn.setEnabled(False)
        self._set_status(t("detail.status.cancelling"))
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
        self._set_status(t("detail.status.download_cancelled"))
        self._log_action("downloaded", t("detail.download.cancelled_by_user"), {"cancelled": True})

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
            show_warning(
                self,
                t("detail.checks.title"),
                t("detail.checks.download_first"),
            )
            self._check_btn.setEnabled(True)
            return
        self._check_btn.setEnabled(False)
        self._checks_cancel_btn.setVisible(True)
        self._set_status(t("detail.status.running_checks"))
        self._progress.setVisible(True)
        self._progress.setRange(0, 0)
        self._check_worker = CheckWorker(
            staged,
            self._pid,
            self._title,
            inventory=self._inventory if isinstance(self._inventory, list) else None,
            metadata=self._metadata if isinstance(self._metadata, dict) else None,
            parent=self,
        )
        self._check_worker.progress.connect(lambda msg: self._set_status(msg))
        self._check_worker.progressFraction.connect(self._on_ring_fraction)
        self._check_worker.finished.connect(self._on_checks_finished)
        self._check_worker.error.connect(self._on_checks_error)
        self._check_worker.cancelled.connect(self._on_checks_cancelled)
        self._check_worker.finished.connect(self._check_worker.deleteLater)
        self._check_worker.error.connect(self._check_worker.deleteLater)
        self._check_worker.cancelled.connect(self._check_worker.deleteLater)
        self._check_worker.start()

    def _on_cancel_checks_click(self) -> None:
        """Ask the running check pass to stop at the next checkpoint."""
        worker = self._check_worker
        if worker is None:
            return
        try:
            worker.cancel()
        except Exception:
            try:
                worker.requestInterruption()
            except Exception:
                pass
        self._set_status(t("detail.status.cancelling"))
        self._checks_cancel_btn.setEnabled(False)

    def _on_checks_cancelled(self) -> None:
        """Reset the header after a cancelled check pass (no report)."""
        self._progress.setVisible(False)
        self._hide_ring()
        self._check_btn.setEnabled(True)
        self._checks_cancel_btn.setVisible(False)
        self._checks_cancel_btn.setEnabled(True)
        self._set_status(t("detail.status.checks_cancelled"))

    def _on_checks_finished(self, report) -> None:
        from engine.status import summarize

        self._check_worker = None
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
        self._checks_cancel_btn.setVisible(False)
        self._checks_cancel_btn.setEnabled(True)
        self._history_btn.setEnabled(True)
        # Update dataset-checks card + manifest tree
        self._refresh_curation_preview()
        self._apply_file_filter_internal()
        all_results = list(report.dataset_checks) + [c for f in report.files for c in f.checks]
        summary = summarize(all_results)
        findings = summary["failed"]
        self._set_status(
            t(
                "detail.status.checks_complete",
                findings=findings,
                errors=summary["failed-error"],
                warnings=summary["failed-warning"],
                skipped=summary["skipped"],
                files=len(report.files),
            )
            + " "
            + (
                t("detail.status.report_auto_saved", name=cache_path.parent.name)
                if cache_path is not None
                else t("detail.status.report_auto_save_failed")
            )
            + t("detail.status.use_export_for_markdown")
        )
        self._log_action(
            "checks_run",
            t(
                "detail.status.report_summary",
                findings=findings,
                files=len(report.files),
            ),
            {"findings": findings, "files": len(report.files)},
        )
        if cache_path is not None:
            try:
                self._log_action(
                    "checks_saved",
                    t(
                        "detail.status.auto_saved_to",
                        folder=cache_path.parent.name,
                        name=cache_path.name,
                    ),
                    {"path": str(cache_path)},
                )
            except Exception:
                pass
        # File-check findings feed the Response draft — rebuild it.
        try:
            self._refresh_response()
        except Exception:
            pass
        self._refresh_workflow()

    def _on_checks_error(self, msg: str) -> None:
        self._check_worker = None
        self._progress.setVisible(False)
        self._hide_ring()
        self._check_btn.setEnabled(True)
        self._checks_cancel_btn.setVisible(False)
        self._checks_cancel_btn.setEnabled(True)
        headline, details = describe_error(msg)
        # The failure stays on the page: an empty status strip read as
        # "nothing happened" once the dialog was closed. The strip now
        # carries the reason and stays until the next run replaces it.
        self._set_status(t("detail.status.checks_failed", reason=headline))
        show_critical(self, t("detail.checks.title"), headline, details=details,
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
                t(
                    "detail.checks.result_detail",
                    path=path,
                    level=result.level,
                    check_id=result.check_id,
                    message=result.message,
                    details=details,
                )
            )
        elif kind == "file":
            if not self._report:
                return
            path = info.get("path", "")
            entry = next((f for f in self._report.files if f.path == path), None)
            if not entry:
                self._set_status(t("detail.status.path_not_in_report", path=path))
            elif not entry.checks:
                self._set_status(t("detail.status.path_no_check", path=path))
            else:
                from engine.status import summarize

                summary = summarize(entry.checks)
                self._set_status(
                    t(
                        "detail.status.path_summary",
                        path=path,
                        passed=summary["passed"],
                        warnings=summary["failed-warning"],
                        errors=summary["failed-error"],
                        skipped=summary["skipped"],
                    )
                )
        else:
            return

    def _on_file_selected(self, row: int, _col: int) -> None:
        # Legacy table slot (pre-tree). Kept so old signal wiring fails
        # loudly in one place instead of scattered AttributeErrors.
        return None

    def _on_export(self) -> None:
        if not self._report:
            show_warning(
                self,
                t("detail.export.title"),
                t("detail.export.run_checks_first"),
            )
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
                t("detail.export.reports_title"),
                start_dir,
                t("detail.export.markdown_filter"),
                options=QFileDialog.DontUseNativeDialog,
            )
        except Exception as exc:
            show_critical(
                self,
                t("detail.export.title"),
                t("detail.export.save_dialog_failed", exc=exc),
            )
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
            show_critical(
                self,
                t("detail.export.title"),
                t("detail.export.write_failed", exc=exc),
            )
            return
        # Success needs no modal — the status line + Dataset log record it.
        # Modals are reserved for failures (above).
        self._last_export_path = str(json_path)
        self._log_action(
            "exported",
            t("detail.export.saved_log", markdown=md_path, json=json_path),
            {"path": str(json_path), "markdown": str(md_path)},
        )
        self._set_status(
            t(
                "detail.status.reports_saved",
                markdown=md_path.name,
                json=json_path.name,
            )
        )
        self._refresh_workflow()
