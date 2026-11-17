"""The dataset detail page: the facade that assembles the sections.

The page owns the layout (the top bar, the stacked review and response
pages, the scrolling main column and the sticky sidebar) and nothing
else; every section's behaviour lives in its own module next door.
"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMenu, QScrollArea, QVBoxLayout, QWidget

from curation.client import DataverseClient
from curation.config import Config
from curation.download_manager import DownloadManager
from curation.metadata_check import DEFAULT_PROFILE
from ui.dataset.actions_section import ActionsSection
from ui.dataset.checks_section import ChecksSection
from ui.dataset.files_section import FilesSection
from ui.dataset.header_section import HeaderSection
from ui.dataset.helpers import _SECTION_LINKS, _format_metadata
from ui.dataset.log_rail import LogRail
from ui.dataset.metadata_load import MetadataLoadSection
from ui.dataset.metadata_section import MetadataSection
from ui.dataset.response_section import ResponseSection
from ui.dataset.state import DetailState
from ui.dataset.versions_section import VersionsSection
from ui.dataset.workflow_section import WorkflowSection
from ui.i18n import t
from ui.ring import RingProgress
from ui.table_layout import TableLayout
from ui.theme import (
    BORDER_SUBTLE,
    FONT_BODY,
    FONT_CAPTION,
    SURFACE_CARD,
    SURFACE_TINT,
    TEXT_MUTED,
    enable_list_copy,
    page_background_qss,
    selectable_labels,
    status_strip_qss,
    transparent_surface_qss,
)
from ui.widgets import (
    WorkflowRail,
    make_action_button,
    make_badge,
    make_body_label,
    make_multiline_input,
    make_page_heading,
    make_progress_bar,
)
from ui.workers import CheckWorker, DownloadWorker, MetadataWorker


class DatasetDetailView(
    WorkflowSection,
    MetadataSection,
    MetadataLoadSection,
    ChecksSection,
    FilesSection,
    VersionsSection,
    LogRail,
    ResponseSection,
    ActionsSection,
    HeaderSection,
    DetailState,
):
    """The dataset detail page: the facade that assembles the sections."""

    _SIDEBAR_COLLAPSE_BELOW = 1100

    def minimumSizeHint(self):
        """Never let the stacked layout force-grow the main window.

        QStackedWidget's minimum is the max over ALL pages — the tall
        DetailTopBar + Response-page editors would otherwise expand the
        window the first time a dataset opens. Every page scrolls its own
        content, so a modest floor is safe.
        """
        from PySide6.QtCore import QSize

        return QSize(720, 480)

    def sizeHint(self):
        from PySide6.QtCore import QSize

        return QSize(1200, 760)

    def __init__(  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
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
        # One declaration for the file-row table (path, size, ext, path);
        # it is filled by _populate_from_inventory and the staged scan.
        self._all_file_rows: list[tuple[str, int, str, str]] = []
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
        main_scroll.setFrameShape(QFrame.Shape.NoFrame)
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
        side_scroll.setFrameShape(QFrame.Shape.NoFrame)
        side_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
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
        self._header_link.setTextFormat(Qt.TextFormat.RichText)
        self._header_link.setOpenExternalLinks(True)
        title_row = QHBoxLayout()
        title_row.setSpacing(12)
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.addWidget(self._title_lbl, 1)
        title_row.addWidget(self._header_link, 0, Qt.AlignmentFlag.AlignBottom)
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
        actions_col.setAlignment(Qt.AlignmentFlag.AlignTop)
        actions_row = QHBoxLayout()
        actions_row.setSpacing(8)
        self._dl_btn = make_action_button(
            t("detail.header.download_all"), kind="secondary", size="md"
        )
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
        self._history_btn = make_action_button(
            t("detail.header.export_reports"), kind="secondary", size="md"
        )
        self._history_btn.setToolTip(t("detail.header.export_reports_tip"))
        self._history_btn.clicked.connect(self._on_export)
        actions_row.addWidget(self._history_btn)
        self._load_meta_btn = make_action_button(
            t("detail.header.load_metadata"), kind="secondary", size="md"
        )
        self._load_meta_btn.setToolTip(t("detail.header.load_metadata_tip"))
        self._load_meta_btn.clicked.connect(self._on_load_metadata)
        actions_row.addWidget(self._load_meta_btn)
        # Sections menu: the sidebar's navigation, reachable even when
        # the sidebar itself is folded away on a narrow window.
        self._sections_btn = make_action_button(t("detail.sections.title"), kind="chip")
        self._sections_btn.setToolTip(t("detail.sidebar.sections_tip"))
        self._sections_menu = QMenu(self._sections_btn)
        self._sections_btn.setMenu(self._sections_menu)
        self._sections_menu.aboutToShow.connect(self._fill_sections_menu)
        self._sections_btn.setVisible(False)
        actions_row.addWidget(self._sections_btn)
        actions_col.addLayout(actions_row)
        # Run checks as primary (always enabled; warns when nothing is staged)
        self._check_btn = make_action_button(
            t("detail.header.run_checks"), kind="primary", size="lg"
        )
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
            status_strip_qss(SURFACE_CARD, BORDER_SUBTLE, TEXT_MUTED, font_size=FONT_BODY)
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
        top_lay.setAlignment(self._ring, Qt.AlignmentFlag.AlignVCenter)

        # Workflow step rail (replaces the old Review/Response tab row):
        # six steps, each navigates only — no step ever runs an action.
        self._rail = WorkflowRail()
        self._rail.stepClicked.connect(self._on_workflow_step)
        top_lay.addWidget(self._rail)

        # ---- Main column content (inside main_scroll canvas) ----
        # MAIN column: completeness → files → auto-checks → version diff
        main_wrap = QVBoxLayout()
        main_wrap.setSpacing(20)
        main_wrap.setContentsMargins(0, 0, 0, 0)
        self._main_wrap = main_wrap

        self._meta_card = self._build_metadata_card()
        main_wrap.addWidget(self._meta_card)

        self._file_card = self._build_file_manifest_card()
        main_wrap.addWidget(self._file_card, 1)

        self._auto_card = self._build_auto_checks_card()
        main_wrap.addWidget(self._auto_card)

        self._version_card = self._build_version_card()
        main_wrap.addWidget(self._version_card)

        # Raw metadata expandable (minimal)
        self._raw_btn = make_action_button(
            t("detail.header.show_raw_metadata"), kind="ghost", size=None
        )
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

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sync_sidebar()
        # The metadata Value column tracks the card width (dv-dmv).
        self._fit_meta_value_column()

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

    def _fill_sections_menu(self) -> None:
        """Rebuild the top bar's Sections menu (the folded sidebar's nav)."""
        try:
            self._sections_menu.clear()
            show = self._sections_menu.addAction(t("detail.sidebar.show_action"))
            show.triggered.connect(self._toggle_sidebar)
            self._sections_menu.addSeparator()
            for key, attr in _SECTION_LINKS:
                action = self._sections_menu.addAction(t(key))
                action.triggered.connect(lambda _checked=False, a=attr: self._goto_section(a))
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
