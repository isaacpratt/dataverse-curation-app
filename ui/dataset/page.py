"""The dataset detail page: the facade that assembles the sections.

The page owns the layout (the top bar, the stacked review and response
pages, the scrolling main column and the sticky sidebar) and nothing
else; every section's behaviour lives in its own module next door.
"""

from typing import Any, cast

from PySide6.QtCore import (
    QSize,
    Qt,
    QTimer,
)
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from curation.client import DataverseClient
from curation.config import Config
from curation.download_manager import DownloadManager
from curation.metadata_check import DEFAULT_PROFILE
from ui.dataset.actions_section import ActionsSection
from ui.dataset.checks_section import ChecksSection
from ui.dataset.files_section import FilesSection
from ui.dataset.header_section import HeaderSection
from ui.dataset.helpers import _format_metadata
from ui.dataset.log_rail import LogRail
from ui.dataset.metadata_load import MetadataLoadSection
from ui.dataset.metadata_section import MetadataSection
from ui.dataset.response_section import ResponseSection
from ui.dataset.state import DetailState
from ui.dataset.versions_section import VersionsSection
from ui.dataset.workflow_section import WorkflowSection
from ui.i18n import t
from ui.table_layout import TableLayout
from ui.theme import (
    ACTIVE_THEME,
    FONT_CAPTION,
    enable_list_copy,
    page_background_qss,
    selectable_labels,
    transparent_surface_qss,
)
from ui.widgets import (
    AppButton,
    StatusWidget,
    WorkflowRail,
    make_action_button,
    make_badge,
    make_body_label,
    make_multiline_input,
    make_page_heading,
)
from ui.workers import (
    CheckWorker,
    DownloadWorker,
    MetadataWorker,
)


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

    def minimumSizeHint(self) -> QSize:
        """Never let the stacked layout force-grow the main window.

        QStackedWidget's minimum is the max over ALL pages — the tall
        DetailTopBar + Response-page editors would otherwise expand the
        window the first time a dataset opens. Every page scrolls its own
        content, so a modest floor is safe.
        """
        return QSize(720, 480)

    def sizeHint(self) -> QSize:
        return QSize(1200, 760)

    def __init__(  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
        self,
        config: Config,
        persistent_id: str,
        title: str,
        cached_metadata: dict[str, Any] | None = None,
        cached_inventory: list[dict[str, Any]] | None = None,
        dataset_hint: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self._config = config
        self._pid = persistent_id
        self._title = title or persistent_id
        # What the dashboard already knew about this dataset (the search
        # payload's state and access facts). It saves the detail view from
        # asking for versions that cannot exist.
        self._dataset_hint: dict[str, Any] = dataset_hint if isinstance(dataset_hint, dict) else {}
        self._report = None
        self._inventory: list[dict[str, Any]] = cached_inventory or []
        # One declaration for the file-row table (path, size, ext, path);
        # it is filled by _populate_from_inventory and the staged scan.
        self._all_file_rows: list[tuple[str, int, str, str]] = []
        self._metadata: dict[str, Any] | None = cached_metadata
        self._guestbook: dict[str, Any] | None = None
        self._account: dict[str, Any] = {}
        self._curation: dict[str, Any] = {}
        self._version_diff: dict[str, Any] | None = None
        self._versions: list[Any] = []
        self._timestamps: dict[str, Any] = {}
        # Open depositor follow-up for this dataset (dv-5eg), refreshed from
        # storage on load and after a decision commits; None when closed.
        self._follow_up: dict[str, Any] | None = None
        self._review_submissions: list[Any] = []
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
        # Pressing Run checks with nothing staged starts a download first;
        # this flag resumes the check pass when that download finishes.
        self._run_after_download: bool = False
        # Response pane state: full rule results (with rule_id/level/pending),
        # assembled sections, and whether the draft has manual edits.
        self._completeness_full: list[Any] = []
        self._ruleset: dict[str, Any] = {}
        self._response_sections: list[Any] = []
        self._response_dirty = False
        self._response_loading = False
        self._response_save_timer: QTimer | None = None
        # The first metadata load is deferred by a beat (so the view is on
        # screen before the network calls start). It must belong to THIS
        # view: `QTimer.singleShot` keeps a functor, not a connection, so
        # it would still fire after the view was destroyed — calling a
        # method on a deleted QObject aborts the process (dv-n1d).
        self._auto_load_timer = QTimer(self)
        self._auto_load_timer.setSingleShot(True)
        self._auto_load_timer.timeout.connect(self._on_load_metadata)
        # Sensitivity & ethics review (dv-3c2): answers load with the card.
        self._sensitivity_answers: dict[str, Any] = {}

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
                theme=ACTIVE_THEME,
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
        top_lay.setContentsMargins(24, 16, 24, 8)
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

        # ---- Page header (dv-cv3, reordered by dv-gfx.4) -----------------
        # 1) the three-button section rail, directly under the app nav bar
        #    and above everything else in the page;
        # 2) the chips row (DOI link, status, curation label) with the
        #    actions on its right, the sidebar toggle last;
        # 3) the identity row: title + labelled date on the left, the
        #    compact status widget on the right (it reserves no height
        #    while idle).
        #
        # The rail is the first band because it is navigation: it reads as
        # part of the app's own nav stack, and it stays put while the page
        # scrolls under it.
        self._rail = WorkflowRail(
            nav_steps=[
                ("dataset_checks", t("detail.rail.dataset_checks")),
                ("file_checks", t("detail.rail.file_checks")),
                ("response", t("detail.rail.response")),
            ]
        )
        self._rail.stepClicked.connect(self._on_workflow_step)
        top_lay.addWidget(self._rail)

        header_row = QHBoxLayout()
        header_row.setSpacing(16)
        badge_row = QHBoxLayout()
        badge_row.setSpacing(8)
        badge_row.setContentsMargins(0, 0, 0, 0)
        # Full persistent ID, never truncated (DOIs run well past 18 chars).
        # The DOI chip IS the Dataverse link: a chip-faced button with an
        # external-link glyph to the left of the ID, opened by the system
        # browser (dv-gfx.2). _update_header_link rewrites the URL (adding
        # &version=DRAFT) on every metadata load.
        self._id_badge = AppButton(self._pid, kind="chip", size="md")
        self._id_badge.setCursor(Qt.CursorShape.PointingHandCursor)
        self._id_badge.setToolTip(self._pid)
        try:
            from ui.icons import role_icon as _link_icon

            self._id_badge.setIcon(_link_icon("open_external", size=14))
        except Exception:
            pass
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
        header_row.addLayout(badge_row, 1)

        # Actions that stay in the fixed header: the in-flight cancels, the
        # curation record export and the primary button, with the sidebar
        # toggle LAST so the whole set reads left-to-right and the layout
        # control sits at the far right (dv-gfx.2).
        # Download/Verify and Load/Reload metadata live in the File checks and
        # Dataset checks section headers below (user decision 2026-11-20); the
        # Export reports button is gone.
        actions_row = QHBoxLayout()
        actions_row.setSpacing(6)
        # Mid-download Cancel — hidden until a worker starts.
        self._dl_cancel_btn = make_action_button(t("common.cancel"), kind="secondary", size="md")
        self._dl_cancel_btn.setToolTip(t("detail.header.download_cancel_tip"))
        self._dl_cancel_btn.setAccessibleName(t("detail.header.download_cancel_a11y"))
        self._dl_cancel_btn.clicked.connect(self._on_download_cancel_click)
        self._dl_cancel_btn.setVisible(False)
        actions_row.addWidget(self._dl_cancel_btn)
        self._record_btn = make_action_button(
            t("detail.header.export_record"), kind="secondary", size="md"
        )
        self._record_btn.setToolTip(t("detail.header.export_record_tip"))
        self._record_btn.clicked.connect(self._on_export_record)
        try:
            from ui.icons import role_icon as _export_icon

            self._record_btn.setIcon(_export_icon("export", size=14))
        except Exception:
            pass
        actions_row.addWidget(self._record_btn)
        # Primary action, label follows the run state (dv-gs5). Standard
        # button size: it is the row's primary action, not a bigger one.
        self._check_btn = make_action_button(self._check_button_text(), kind="primary", size="md")
        self._check_btn.setToolTip(t("detail.header.run_checks_tip"))
        self._check_btn.clicked.connect(self._on_run_checks)
        try:
            from ui.icons import role_icon as _run_icon

            self._check_btn.setIcon(_run_icon("run", size=14))
        except Exception:
            pass
        actions_row.addWidget(self._check_btn)
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
        actions_row.addWidget(self._checks_cancel_btn)
        # Sidebar show/hide toggle - the rightmost control in the row; the
        # rail is navigation, this is chrome (dv-6wb).
        self._sidebar_toggle_btn = make_action_button("", kind="secondary", size="md")
        try:
            from ui.icons import role_icon as _side_icon

            # Sidebar is open by default (_sidebar_collapsed = False), so the
            # toggle shows the "collapse" icon (sidebar_hide = panel-right-close).
            self._sidebar_toggle_btn.setIcon(_side_icon("sidebar_hide"))
        except Exception:
            self._sidebar_toggle_btn.setText(t("detail.sidebar.collapse_a11y"))
        self._sidebar_toggle_btn.setToolTip(t("detail.sidebar.collapse_tip"))
        self._sidebar_toggle_btn.setAccessibleName(t("detail.sidebar.collapse_a11y"))
        self._sidebar_toggle_btn.clicked.connect(self._toggle_sidebar)
        actions_row.addWidget(self._sidebar_toggle_btn)
        header_row.addLayout(actions_row, 0)
        top_lay.addLayout(header_row)

        # Middle band: identity left, compact status widget right. The widget
        # is hidden while idle, so this band costs the same as the old title
        # row; running/complete/error states use the space that was empty.
        middle_row = QHBoxLayout()
        middle_row.setSpacing(16)
        middle_row.setContentsMargins(0, 2, 0, 0)
        identity_col = QVBoxLayout()
        identity_col.setSpacing(2)
        self._title_lbl, _subtitle = make_page_heading(self._title)
        self._title_lbl.setWordWrap(True)
        identity_col.addWidget(self._title_lbl)
        self._depositor_lbl = make_body_label(t("detail.header.loading_metadata"), wrap=False)
        identity_col.addWidget(self._depositor_lbl)
        middle_row.addLayout(identity_col, 1)
        self._status_widget = StatusWidget()
        middle_row.addWidget(self._status_widget, 0)
        top_lay.addLayout(middle_row)
        # Called last: needs _depositor_lbl/_title_lbl to exist, and cached
        # metadata makes `meta` truthy immediately.
        self._update_header_link(None)

        # The rail shades the view on screen (dv-gfx.4) and takes a shadow
        # once the column scrolls under it (dv-gfx.15).
        self._rail.set_active_step("dataset_checks")
        self._rail_scrolled = False
        try:
            self._scroll.verticalScrollBar().valueChanged.connect(self._sync_rail_shadow)
        except Exception:
            pass

        # ---- Main column content (inside main_scroll canvas) ----
        # Two top-level sections (dv-yg6): Dataset checks (metadata
        # completeness + the automated checks about the dataset itself)
        # above File checks (the renamed manifest, every per-file result).
        main_wrap = QVBoxLayout()
        main_wrap.setSpacing(20)
        main_wrap.setContentsMargins(0, 0, 0, 0)
        self._main_wrap = main_wrap

        # Depositor follow-up banner (dv-5eg): shown while a revisions
        # decision is awaiting the depositor, and again once the draft moves.
        self._follow_up_card = self._build_follow_up_card()
        main_wrap.addWidget(self._follow_up_card)

        self._verdict_card = self._build_verdict_card()
        main_wrap.addWidget(self._verdict_card)

        # Dataset checks section: Load/Reload Metadata sits on the card's
        # own header line, and the metadata checklist and the automated
        # checks share one card (dv-gfx.5, item 9).
        self._load_meta_btn = make_action_button(
            t("detail.header.load_metadata"), kind="secondary", size="sm"
        )
        self._load_meta_btn.setToolTip(t("detail.header.load_metadata_tip"))
        self._load_meta_btn.clicked.connect(self._on_load_metadata)
        self._meta_card = self._build_metadata_card()
        _meta_lay = self._meta_card.layout()
        _meta_bar = _meta_lay.itemAt(0) if _meta_lay is not None else None
        _meta_bar_w = _meta_bar.widget() if _meta_bar is not None else None
        _meta_header = _meta_bar_w.layout() if _meta_bar_w is not None else None
        if isinstance(_meta_header, QHBoxLayout):
            _meta_header.addWidget(self._load_meta_btn)
        main_wrap.addWidget(self._meta_card)

        self._auto_card = self._build_auto_checks_card()
        # The automated checks are a section of the card above, not a
        # second card (dv-3d0.3): appending to the card body puts it under
        # the metadata rows, inside the same edge and tools row.
        self._meta_card_body.addWidget(self._auto_card)

        # File checks section — Verify Files sits on the tools row with
        # the other controls (dv-3d0.5).
        self._dl_btn = make_action_button(
            t("detail.header.download_all"), kind="secondary", size="md"
        )
        self._dl_btn.setToolTip(t("detail.header.download_dataset_tip"))
        self._dl_btn.clicked.connect(self._on_download)
        self._file_card = self._build_file_manifest_card(download_button=self._dl_btn)
        main_wrap.addWidget(self._file_card, 1)

        # The version card lives in the sidebar now (dv-gfx.6).

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
        main_container.setStyleSheet(
            transparent_surface_qss("DetailMainContainer", theme=ACTIVE_THEME)
        )
        canvas_lay.addWidget(main_container)

        # SIDEBAR (right, sticky): the sticky rail is the navigation map;
        # the sidebar keeps only chrome (preview, dataset log) + fold toggle.
        # (Assessment Action moved to the Response page.)
        side_wrap = QVBoxLayout()
        side_wrap.setSpacing(20)
        side_wrap.setContentsMargins(12, 12, 24, 24)
        self._side_wrap = side_wrap

        # In-app file preview (dv-koz): shows the head of the file the
        # curator clicked in the manifest; degrades to Missing-library
        # notices or an Open-folder fallback when it can't render.
        self._preview_card = self._build_preview_card()
        side_wrap.addWidget(self._preview_card)

        # Version log between the preview and the dataset log (dv-gfx.6):
        # the sidebar reads preview → versions → log, most context first.
        self._version_card = self._build_version_card()
        side_wrap.addWidget(self._version_card)

        self._dataset_log_card = self._build_dataset_log_card()
        # Stretch factor 1: the log owns the sidebar's free vertical space
        # so the timeline reads without constant scrolling.
        side_wrap.addWidget(self._dataset_log_card, 1)

        side_container = QWidget()
        side_container.setLayout(side_wrap)
        side_container.setObjectName("DetailSideContainer")
        side_container.setStyleSheet(
            transparent_surface_qss("DetailSideContainer", theme=ACTIVE_THEME)
        )
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
                disk_meta, disk_inv, disk_curation = self._dl_mgr.load_metadata(self._pid)
            except Exception:
                disk_meta, disk_inv, disk_curation = None, None, None
            if disk_meta is not None:
                self._metadata = disk_meta
                self._inventory = disk_inv or []
                self._curation = disk_curation or {}
                from_disk = True
        if self._metadata is not None:
            self._update_header_link(self._metadata)
            self._update_curation_pill()
            self._refresh_header_actions()
            self._refresh_rail_counts()
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
                self._auto_load_timer.start(100)
        else:
            self._refresh_files_placeholder()
            self._refresh_dataset_log()
            self._auto_load_timer.start(100)

        # The general message strip became the compact StatusWidget (dv-3d0.4):
        # the guard asks the chip whether it is already showing something.
        status_widget = getattr(self, "_status_widget", None)
        if self._report is not None and (status_widget is None or not status_widget.isVisible()):
            # Cached checks report (auto-saved on every run): results are
            # already rendered by the refresh calls above; keep the primary
            # label in step with what was restored.
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

        self._install_shortcuts()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._sync_sidebar()
        self._sync_rail_shadow()

    def _sync_rail_shadow(self) -> None:
        """Shadow under the rail once the column has scrolled (dv-gfx.15).

        The rail sits above the scrolling canvas, so it never moves; the
        shadow is the cue that the page has slid under it.
        """
        rail = getattr(self, "_rail", None)
        scroll = getattr(self, "_scroll", None)
        if rail is None or scroll is None:
            return
        try:
            scrolled = scroll.verticalScrollBar().value() > 0
        except Exception:
            scrolled = False
        if scrolled == bool(getattr(self, "_rail_scrolled", False)):
            return
        self._rail_scrolled = scrolled
        try:
            from ui.theme import apply_elevation

            if scrolled:
                apply_elevation(rail, blur=12, dy=3, alpha=26)
            else:
                rail.setGraphicsEffect(None)
        except Exception:
            pass

    def _layout_for(self, name: str, header: QHeaderView) -> "TableLayout":
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

    def _track_table_widths(self, name: str, header: QHeaderView) -> None:
        """Restore the saved layout for a header, then keep it up to date.

        The controller saves on column resize, column move and sort
        changes -- user gestures only. Sort state restores here (the
        indicator is set on the header); populates re-enable sorting
        afterwards, which re-applies that indicator to fresh rows.
        """
        try:
            layout = self._layout_for(name, header)
            if layout.restore():
                tbl = cast(Any, header.parent())
                if hasattr(tbl, "disable_auto_fit"):
                    tbl.disable_auto_fit()
        except Exception:
            pass

    def _reset_table_view(self, name: str, header: QHeaderView) -> bool:
        """Reset a tracked table to its construction view.

        Restores widths/order/visibility/sort. Clears the persisted entry
        so the reset survives restarts. Returns True when a snapshot was
        applied.
        """
        try:
            layout = self._layout_for(name, header)
            ok = layout.reset()
            tbl = cast(Any, header.parent())
            if hasattr(tbl, "enable_auto_fit"):
                tbl.enable_auto_fit()
            return ok
        except Exception:
            return False

    def _sync_sidebar(self) -> None:
        """Fold the sticky sidebar away on a narrow window.

        The user can fold or unfold it by hand; until they do, the width
        decides. The section links move into the top bar's Sections menu.
        The dataset log stays in the sidebar (it is simply hidden with it).
        """
        try:
            if self._sidebar_user_collapsed is None:
                collapsed = self.width() < self._SIDEBAR_COLLAPSE_BELOW
            else:
                collapsed = self._sidebar_user_collapsed
            # Always update the toggle icon/tooltip, even on first paint when
            # the state hasn't changed (dv-3d0.1).
            self._sidebar_collapsed = collapsed
            self._side_scroll.setVisible(not collapsed)
            try:
                from ui.icons import role_icon as _side_icon

                self._sidebar_toggle_btn.setIcon(
                    _side_icon("sidebar_show" if collapsed else "sidebar_hide")
                )
            except Exception:
                pass
            self._sidebar_toggle_btn.setToolTip(
                t("detail.sidebar.collapse_tip")
                if not collapsed
                else t("detail.sidebar.show_action")
            )
            self._sidebar_toggle_btn.setAccessibleName(
                t("detail.sidebar.collapse_a11y")
                if not collapsed
                else t("detail.sidebar.show_action")
            )
            # The dataset log stays in the sidebar - it's hidden/shown with
            # the sidebar scroll area, not moved to the main column.
        except Exception:
            pass

    def _toggle_sidebar(self) -> None:
        """Fold or unfold the sidebar (the user's choice wins over width)."""
        try:
            self._sidebar_user_collapsed = not self._sidebar_collapsed
            self._sync_sidebar()
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
        """Deprecate (dv-3d0.1): the dataset log now stays in the sidebar.

        Keep as a no-op for any external callers; the log is hidden/shown
        with the sidebar scroll area instead of being reparented.
        """
        pass

    def take_running_workers(self) -> list[Any]:
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

    def _install_shortcuts(self) -> None:
        """Power-path accelerators for the per-dataset loop.

        Scoped to this view (WidgetWithChildrenShortcut): the chords fire
        only while focus is inside the detail view, never from the dashboard
        or a pane. Consistent with the app-level shortcuts in main_window.py.
        """
        from PySide6.QtGui import QKeySequence, QShortcut

        def _sc(seq: str, handler: Any) -> QShortcut:
            sc = QShortcut(
                QKeySequence(seq, QKeySequence.SequenceFormat.PortableText), self, handler
            )
            sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            return sc

        self._shortcuts = [
            _sc("Ctrl+Return", self._on_ctrl_enter),
            _sc("Ctrl+Enter", self._on_ctrl_enter),
            _sc("Ctrl+D", self._on_download),
            _sc("Ctrl+Shift+O", self._on_open_folder),
        ]

    def _on_ctrl_enter(self) -> None:
        """One chord, two contexts: Commit on the Response page, else Run checks."""
        try:
            if self._pages.currentIndex() == 1:
                self._on_commit()
                return
        except Exception:
            pass
        self._on_run_checks()

    def cancel_pending_loads(self) -> None:
        """Stop the deferred first load (the view is being replaced).

        The auto-load timer is bound to this view, but the view may be
        replaced before the timer fires: the pending callback would then
        start a worker on a view that is about to be destroyed, and
        destroying a view with a running QThread child aborts the
        process (dv-n1d).
        """
        try:
            self._auto_load_timer.stop()
        except Exception:
            pass
