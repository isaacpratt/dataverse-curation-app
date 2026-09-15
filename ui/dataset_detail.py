"""Dataset detail — 2-column assessment layout (metadata/files/checks + sticky sidebar).

Left: Auto-Checks + Assessment Action. Right: File Manifest.
Header: persistent ID badge, status pill, title, depositor/date, actions.
Preserves all workers (MetadataWorker, DownloadWorker, CheckWorker) and
metadata completeness (profile selector).
"""

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
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
from metadata_check import DEFAULT_PROFILE, PROFILES, check_metadata_completeness
from ui.dialogs import show_critical, show_info, show_warning
from ui.download_dialog import DownloadApprovalDialog
from ui.theme import (
    ERROR,
    ERROR_CONTAINER,
    ON_ERROR_CONTAINER,
    ON_SURFACE,
    ON_SURFACE_VARIANT,
    OUTLINE_VARIANT,
    PRIMARY,
    PRIMARY_CONTAINER,
    SECONDARY_CONTAINER,
    SURFACE_CONTAINER,
    SURFACE_CONTAINER_LOW,
    SURFACE_CONTAINER_LOWEST,
    SURFACE_VARIANT,
    TERTIARY,
    action_button_style,
    enable_list_copy,
    selectable_labels,
)
from ui.workers import CheckWorker, DownloadWorker, MetadataWorker
from ui.widgets import AppButton, AppTable, make_card, make_combo, make_search_field


def _human_size(n: int) -> str:
    try:
        n = int(n)
    except Exception:
        return str(n)
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / 1024**2:.1f} MB"


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


def _pill_state(version_state: str, in_review: bool = False) -> tuple[str, str]:
    """Same words as the dashboard status column (Draft/Published/In Review)."""
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

        self._client = DataverseClient(config.dataverse.base_url, config.dataverse.api_token)
        self._dl_mgr = DownloadManager(self._client, config.app.workspace)
        self.setStyleSheet("background: #faf8ff;")
        self.setAutoFillBackground(False)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- Fixed page header (title, actions, status) ----
        top = QWidget()
        top.setStyleSheet("background: #faf8ff; border: none;")
        top_lay = QVBoxLayout(top)
        top_lay.setContentsMargins(24, 24, 24, 12)
        top_lay.setSpacing(8)
        root.addWidget(top)

        # ---- Content row: scrolling main column + sticky sidebar ----
        content_row = QHBoxLayout()
        content_row.setContentsMargins(0, 0, 0, 0)
        content_row.setSpacing(0)
        root.addLayout(content_row, 1)

        # ---- Main column scroll ----
        main_scroll = QScrollArea()
        main_scroll.setWidgetResizable(True)
        main_scroll.setFrameShape(QFrame.NoFrame)
        main_scroll.setStyleSheet("QScrollArea { background: #faf8ff; border: none; } QWidget#Canvas { background: #faf8ff; }")
        self._scroll = main_scroll
        canvas = QWidget()
        canvas.setObjectName("Canvas")
        self._canvas = canvas
        main_scroll.setWidget(canvas)
        canvas_lay = QVBoxLayout(canvas)
        canvas_lay.setContentsMargins(24, 12, 12, 24)
        canvas_lay.setSpacing(20)
        content_row.addWidget(main_scroll, 2)

        # ---- Sticky sidebar (own scroll so Sections never scrolls away) ----
        side_scroll = QScrollArea()
        side_scroll.setWidgetResizable(True)
        side_scroll.setFrameShape(QFrame.NoFrame)
        side_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        side_scroll.setMinimumWidth(280)
        side_scroll.setMaximumWidth(400)
        side_scroll.setStyleSheet("QScrollArea { background: #faf8ff; border: none; }")
        content_row.addWidget(side_scroll, 1)

        # ---- Page header (ID badge + status, title, depositor, actions) ----
        header_row = QHBoxLayout()
        header_row.setSpacing(16)
        header_left = QVBoxLayout()
        header_left.setSpacing(6)
        badge_row = QHBoxLayout()
        badge_row.setSpacing(8)
        badge_row.setContentsMargins(0, 0, 0, 0)
        self._id_badge = QLabel(self._pid[:18] if len(self._pid) > 18 else self._pid)
        self._id_badge.setStyleSheet(
            "QLabel { background: #eaedff; color: #424656; border: 1px solid #c3c6d8; border-radius: 6px; padding: 3px 8px; font-family: 'JetBrains Mono', Consolas, monospace; font-size: 12px; }"
        )
        badge_row.addWidget(self._id_badge)
        self._status_pill = QLabel("Loading…")
        self._status_pill.setObjectName("PillInReview")
        badge_row.addWidget(self._status_pill)
        self._curation_pill = QLabel("")
        self._curation_pill.setObjectName("PillDraft")
        self._curation_pill.setVisible(False)
        self._curation_pill.setToolTip("Curation label assigned in Dataverse")
        badge_row.addWidget(self._curation_pill)
        badge_row.addStretch()
        header_left.addLayout(badge_row)

        self._title_lbl = QLabel(self._title)
        self._title_lbl.setWordWrap(True)
        self._title_lbl.setStyleSheet("font-size: 22px; font-weight: 600; color: #131b2e; border: none; background: transparent;")

        # Clickable Dataverse link sits next to the title
        self._header_link = QLabel()
        self._header_link.setTextFormat(Qt.RichText)
        self._header_link.setOpenExternalLinks(True)
        self._header_link.setStyleSheet("font-size: 12px; color: #424656; border: none; background: transparent;")
        title_row = QHBoxLayout()
        title_row.setSpacing(12)
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.addWidget(self._title_lbl, 1)
        title_row.addWidget(self._header_link, 0, Qt.AlignBottom)
        header_left.addLayout(title_row)

        self._depositor_lbl = QLabel("Loading metadata…")
        self._depositor_lbl.setStyleSheet("font-size: 13px; color: #57657a; border: none; background: transparent;")
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
        # Inline pill style: app-level QSS fails to paint button faces inside
        # some main-window subtrees, so critical actions carry their own CSS.
        self._dl_btn.setStyleSheet(action_button_style(False))
        self._dl_btn.clicked.connect(self._on_download)
        actions_row.addWidget(self._dl_btn)
        self._history_btn = AppButton("Export report…", kind="secondary", size="md")
        self._history_btn.setStyleSheet(action_button_style(False))
        self._history_btn.setToolTip("Save the DatasetReport JSON (runs after checks complete)")
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
        self._status.setStyleSheet("font-size: 11px; color: #424656; background: #ffffff; border: 1px solid #c3c6d8; border-radius: 8px; padding: 6px 10px;")
        self._status.setWordWrap(True)
        self._status.setVisible(False)
        top_lay.addWidget(self._status)
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._progress.setFixedHeight(6)
        top_lay.addWidget(self._progress)

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
        self._raw_btn = AppButton("Show all metadata fields →", kind="ghost", size=None)
        self._raw_btn.clicked.connect(self._toggle_raw)
        main_wrap.addWidget(self._raw_btn)
        self._raw_view = QTextEdit()
        self._raw_view.setVisible(False)
        self._raw_view.setReadOnly(True)
        self._raw_view.setMinimumHeight(180)
        self._raw_view.setStyleSheet("QTextEdit { background: #ffffff; border: 1px solid #c3c6d8; border-radius: 8px; font-family: 'JetBrains Mono', Consolas, monospace; font-size: 11px; }")
        main_wrap.addWidget(self._raw_view)

        main_container = QWidget()
        main_container.setLayout(main_wrap)
        main_container.setStyleSheet("background: transparent;")
        canvas_lay.addWidget(main_container)

        # SIDEBAR (right, sticky): navigation → dataset log → assessment
        side_wrap = QVBoxLayout()
        side_wrap.setSpacing(20)
        side_wrap.setContentsMargins(12, 12, 24, 24)

        self._nav_card = self._build_nav_card()
        side_wrap.addWidget(self._nav_card)

        self._dataset_log_card = self._build_dataset_log_card()
        # Stretch factor 1: the log owns the sidebar's free vertical space
        # so the timeline reads without constant scrolling.
        side_wrap.addWidget(self._dataset_log_card, 1)

        self._assessment_card = self._build_assessment_card()
        side_wrap.addWidget(self._assessment_card)

        side_container = QWidget()
        side_container.setLayout(side_wrap)
        side_container.setStyleSheet("background: transparent;")
        side_scroll.setWidget(side_container)

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
                self._file_table.setRowCount(0)
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

        # Text selection + table copy support
        enable_list_copy(self._dataset_log)
        selectable_labels(self)

    # ---- Builders ----
    def _build_auto_checks_card(self) -> QFrame:
        card, _body_host, _title, header_lay = make_card("Auto-Checks")
        self._auto_summary = QLabel("—")
        self._auto_summary.setStyleSheet("font-size: 11px; font-weight: 600; color: #424656; background: transparent; border: none;")
        header_lay.addWidget(self._auto_summary)
        # Body: scroll of checks (factory body reused directly)
        self._auto_body = _body_host
        self._auto_body.setContentsMargins(16, 12, 16, 12)
        self._auto_body.setSpacing(8)
        legend = QLabel(
            "✓ check ran and passed · ✕ check ran and found an issue · "
            "PASS planned check · FAIL failed check · "
            "MISSING optional library not installed · — no matching files"
        )
        legend.setWordWrap(True)
        legend.setStyleSheet("font-size: 11px; color: #57657a; border: none; background: transparent;")
        self._auto_body.addWidget(legend)
        self._auto_legend = legend
        # Placeholder
        self._auto_placeholder = QLabel("No file list yet — load metadata to see which checks will run.")
        self._auto_placeholder.setWordWrap(True)
        self._auto_placeholder.setStyleSheet("font-size: 12px; color: #57657a; border: none; background: transparent;")
        self._auto_body.addWidget(self._auto_placeholder)
        return card

    def _build_metadata_card(self) -> QFrame:
        card, body, _title, header_lay = make_card("Metadata completeness")
        self._profile_combo = make_combo(
            [(info["label"], key) for key, info in PROFILES.items()],
            height=28,
            min_width=140,
        )
        idx = list(PROFILES.keys()).index(DEFAULT_PROFILE) if DEFAULT_PROFILE in PROFILES else 0
        self._profile_combo.setCurrentIndex(idx)
        self._profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        header_lay.addWidget(self._profile_combo)
        self._meta_summary = QLabel("Not loaded yet — click “Load metadata from Dataverse”.")
        self._meta_summary.setTextFormat(Qt.RichText)
        self._meta_summary.setWordWrap(True)
        self._meta_summary.setStyleSheet("font-size: 12px; color: #424656; border: none; background: transparent;")
        body.addWidget(self._meta_summary)
        # Every check with its status — visible table (Field | Value | Status).
        # Requirement text lives in the Field cell's tooltip.
        self._meta_check_table = AppTable(
            ["Check", "Value", "Status"],
            widths={0: 150, 1: 150, 2: 90},
            row_height=28,
        )
        self._track_table_widths("dataset_meta", self._meta_check_table.horizontalHeader())
        # No internal scrollbars: the card always fits every row; the page
        # canvas scrolls instead. Height is fitted in _populate_completeness.
        self._meta_check_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._meta_check_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body.addWidget(self._meta_check_table)
        return card

    def _build_assessment_card(self) -> QFrame:
        card, body, _title, _header = make_card("Assessment Action")
        body.setContentsMargins(16, 16, 16, 16)
        body.setSpacing(12)
        # Internal Notes
        lbl = QLabel("Internal Notes (Markdown supported)")
        lbl.setStyleSheet("font-size: 11px; font-weight: 600; color: #424656; letter-spacing: 0.5px; background: transparent; border: none;")
        body.addWidget(lbl)
        self._notes_edit = QTextEdit()
        self._notes_edit.setPlaceholderText("Enter findings, issues, or specific instructions for the author...")
        self._notes_edit.setFixedHeight(110)
        self._notes_edit.setStyleSheet("QTextEdit { background: #ffffff; border: 1px solid #c3c6d8; border-radius: 8px; font-size: 12px; } QTextEdit:focus { border: 1px solid #004ccd; }")
        body.addWidget(self._notes_edit)
        # Decision State
        lbl2 = QLabel("Decision State")
        lbl2.setStyleSheet("font-size: 11px; font-weight: 600; color: #424656; letter-spacing: 0.5px; background: transparent; border: none;")
        body.addWidget(lbl2)
        self._decision_combo = make_combo(
            tip="Curation labels from this Dataverse instance "
            "(falls back to generic states when labels are unavailable)",
        )
        self._refresh_decision_options()
        body.addWidget(self._decision_combo)
        # Commit button row
        row = QHBoxLayout()
        row.addStretch()
        commit = AppButton("Commit Decision", kind="primary", size="md")
        commit.setStyleSheet(action_button_style(True))
        commit.clicked.connect(self._on_commit)
        row.addWidget(commit)
        body.addLayout(row)
        return card

    def _build_nav_card(self) -> QFrame:
        """Sidebar section navigation — jumps the main column to each box."""
        card, body, _title, _header = make_card("Sections")
        body.setSpacing(6)
        self._nav_buttons: list = []
        for label, attr in [
            ("Metadata completeness", "_meta_card"),
            ("File Manifest", "_file_card"),
            ("Auto-Checks", "_auto_card"),
            ("Version log", "_version_card"),
        ]:
            btn = AppButton(f"  →  {label}", kind="ghost", size=None)
            btn.setStyleSheet(
                "QPushButton { text-align: left; padding: 7px 8px; font-size: 12px; "
                "color: #004ccd; background: transparent; border: none; border-radius: 6px; }"
                "QPushButton:hover { background: #eaedff; }"
            )
            btn.clicked.connect(lambda _c, a=attr: self._goto_section(a))
            body.addWidget(btn)
            self._nav_buttons.append(btn)
        return card

    def _track_table_widths(self, name: str, header) -> None:
        """Restore saved column widths once, then persist on every manual resize."""
        try:
            from storage import restore_table_state, save_table_state

            ws = self._config.app.workspace
            restore_table_state(ws, name, header)
            header.sectionResized.connect(
                lambda _li, _old, _new, _n=name, _h=header: save_table_state(
                    self._config.app.workspace, _n, _h
                )
            )
        except Exception:
            pass

    def _goto_section(self, attr: str) -> None:
        """Scroll so the section's top sits at the main column's top (+ margin)."""
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
            "QListWidget { background: #ffffff; border: 1px solid #e2e7ff; border-radius: 8px; "
            "font-size: 11px; color: #424656; }"
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
        try:
            st = self._state()
            if st is None:
                return
            st.log_action(self._pid, action, notes=notes, details=details or {})
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

        def _add(ts: Any, text: str) -> None:
            raw = str(ts or "").strip()
            if raw:
                disp = raw[:10].replace("T", " ")
                events.append((raw, f"{disp} — {text}"))
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
            events.append((first, f"{first[:10]} — Dataset first created"))

        # Lifecycle timestamps endpoint (dataset-level record dates).
        ts = self._timestamps if isinstance(self._timestamps, dict) else {}
        ts_created = str(ts.get("createTime") or "")
        if not dated_creations and ts_created:
            # No version dates at all — timestamps are the only source.
            events.append((ts_created, f"{ts_created[:10]} — Dataset first created"))
        ts_published = str(ts.get("publicationTime") or "")
        if (
            ts_published
            and ts_published[:10] != ts_created[:10]
            and ts_published[:10] not in version_published_days
        ):
            # Only shown when it differs from creation (per curator request)
            # and no version event already covers that day.
            events.append((ts_published, f"{ts_published[:10]} — Dataset first published"))
        ts_doi = str(ts.get("globalIdCreateTime") or "")
        if ts_doi:
            events.append((ts_doi, f"{ts_doi[:10]} — DOI minted"))
        ts_touched = str(ts.get("lastUpdateTime") or "")
        if ts_touched:
            events.append((ts_touched, f"{ts_touched[:10]} — Draft last updated"))

        # Review submissions (SUBMITTEDDS inbox notes, PID-matched).
        for sub in self._review_submissions if isinstance(self._review_submissions, list) else []:
            if not isinstance(sub, dict):
                continue
            when = str(sub.get("time") or "")
            dv = str(sub.get("dataverse") or "").strip()
            who = str(sub.get("requestor") or "").strip()
            text = f"Submitted for review{(' to be published in ' + dv) if dv else ''}{(' by ' + who) if who else ''}"
            if when:
                events.append((when, f"{when[:10]} — {text}"))
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

        try:
            st = self._state()
            actions = st.list_actions(self._pid, limit=50) if st is not None else []
            if st is not None:
                st.close()
        except Exception:
            actions = []
        _local_text = {
            "downloaded": "Dataset downloaded for curation",
            "checks_run": "Automated checks run",
            "decision": "Decision recorded",
            "exported": "Curation report exported",
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
        self._version_summary = QLabel("—")
        self._version_summary.setStyleSheet("font-size: 11px; font-weight: 600; color: #424656; background: transparent; border: none;")
        header_lay.addWidget(self._version_summary)
        self._version_body = _body_host
        return card

    def _version_placeholder(self, text: str) -> None:
        ph = QLabel(text)
        ph.setWordWrap(True)
        ph.setStyleSheet("font-size: 12px; color: #57657a; background: transparent; border: none;")
        self._version_body.addWidget(ph)

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

        def _version_line(v: dict) -> tuple[str, str]:
            num = v.get("number", "") or ""
            state = (v.get("state", "") or "").upper()
            ct, rt = v.get("create_time", ""), v.get("release_time", "")
            if state == "DRAFT":
                return f"Draft — created {ct[:10] or 'date unknown'} (current)", PRIMARY
            if state == "DEACCESSIONED":
                return f"v{num} — deaccessioned {(rt or ct)[:10] or 'date unknown'}", ERROR
            if rt:
                return f"v{num} — published {rt[:10]}", "#16a34a"
            return f"v{num} — created {ct[:10] or 'date unknown'}", "#57657a"

        # Version list first (current + all previous)
        if versions:
            vlist = QListWidget()
            vlist.setMaximumHeight(min(150, 30 + 26 * len(versions)))
            vlist.setStyleSheet(
                "QListWidget { background: #ffffff; border: 1px solid #e2e7ff; border-radius: 8px; "
                "font-size: 12px; }"
            )
            enable_list_copy(vlist)
            for v in versions:
                text, color = _version_line(v)
                entry = QListWidgetItem(text)
                entry.setToolTip(text)
                entry.setForeground(QColor(color))
                vlist.addItem(entry)
            self._version_body.addWidget(vlist)
        elif self._metadata is None:
            self._version_summary.setText("—")
            self._version_placeholder("Version comparison appears after loading metadata from Dataverse.")
            return
        else:
            # Metadata loaded but no version history came back: first version.
            initial = QListWidgetItem("Initial draft — no previous versions")
            initial.setToolTip("This looks like the dataset's first version")
            initial.setForeground(QColor(PRIMARY))
            vlist = QListWidget()
            vlist.setMaximumHeight(56)
            vlist.setStyleSheet(
                "QListWidget { background: #ffffff; border: 1px solid #e2e7ff; border-radius: 8px; "
                "font-size: 12px; }"
            )
            vlist.addItem(initial)
            self._version_body.addWidget(vlist)

        n_versions = len(versions) if versions else 1
        if not diff:
            self._version_summary.setText(f"{n_versions} version(s)")
            return
        old_num = (diff.get("old") or {}).get("number") or "published"
        total = int(diff.get("total_changes") or 0)
        meta = diff.get("metadata_changes") or []
        terms = diff.get("terms_changes") or []
        n_files = (
            len(diff.get("files_added") or [])
            + len(diff.get("files_removed") or [])
            + len(diff.get("files_replaced") or [])
            + len(diff.get("file_changes") or [])
        )
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
            self._version_body.addWidget(table)
        # File changes
        from PySide6.QtWidgets import QListWidget, QListWidgetItem

        def _fname(f: dict) -> str:
            path, name = (f.get("path") or "").strip(), (f.get("name") or "").strip()
            if path and name:
                return f"{path}/{name}"
            return name or path or "(unnamed file)"

        entries: list[tuple[str, str]] = []
        for f in diff.get("files_added") or []:
            entries.append((f"+ {_fname(f)} — added", "#16a34a"))
        for f in diff.get("files_removed") or []:
            entries.append((f"− {_fname(f)} — removed", ERROR))
        for pair in diff.get("files_replaced") or []:
            old_f, new_f = pair.get("old") or {}, pair.get("new") or {}
            entries.append((f"⇄ {_fname(old_f)} → {_fname(new_f)} — replaced", "#d97706"))
        for fc in diff.get("file_changes") or []:
            for ch in fc.get("changes") or []:
                entries.append(
                    (f"~ {fc.get('file', '')}: {ch.get('field', '')} changed", PRIMARY)
                )
        if entries:
            flist = QListWidget()
            flist.setMaximumHeight(min(140, 28 + 24 * len(entries)))
            flist.setStyleSheet(
                "QListWidget { background: #ffffff; border: 1px solid #e2e7ff; border-radius: 8px; "
                "font-size: 11px; color: #424656; }"
            )
            for text, color in entries:
                item = QListWidgetItem(text)
                item.setToolTip(text)
                item.setForeground(QColor(color))
                flist.addItem(item)
            self._version_body.addWidget(flist)

    def _build_file_manifest_card(self) -> QFrame:
        card, _body_unused, _title, header_lay = make_card("File Manifest")
        _body_unused.setContentsMargins(0, 0, 0, 0)
        _body_unused.setSpacing(0)
        self._open_folder_btn = AppButton("Open folder", kind="secondary", size="md")
        self._open_folder_btn.setStyleSheet(action_button_style(False))
        self._open_folder_btn.setToolTip("Open the staged download folder in the file explorer")
        self._open_folder_btn.clicked.connect(self._on_open_folder)
        header_lay.addWidget(self._open_folder_btn)
        self._file_filter = make_search_field("Filter files...", height=36, min_width=180)
        self._file_filter.textChanged.connect(self._on_file_filter)
        header_lay.addWidget(self._file_filter)
        lay = QVBoxLayout()
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        # NOTE: table + footer live in a flush sub-layout so the header keeps
        # its top radius and the footer keeps its bottom radius.
        card.layout().addLayout(lay)

        # Table: leading checkbox column shows whether the file is staged locally
        self._file_table = AppTable(
            ["✓", "Filename", "Size", "Format", "Scan Status"],
            widths={0: 40, 1: 300, 2: 80, 3: 80, 4: 110},
            row_height=44,
        )
        self._track_table_widths("dataset_files", self._file_table.horizontalHeader())
        self._file_table.cellClicked.connect(self._on_file_selected)
        lay.addWidget(self._file_table, 1)

        # Footer: showing X of Y + total size
        footer = QFrame()
        footer.setStyleSheet(f"QFrame {{ background: #faf8ff; border-top: 1px solid {SURFACE_CONTAINER_LOW}; border-bottom-left-radius: 12px; border-bottom-right-radius: 12px; }}")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(16, 10, 16, 10)
        self._file_footer_left = QLabel("No files yet")
        self._file_footer_left.setStyleSheet("font-size: 12px; color: #424656; background: transparent; border: none;")
        fl.addWidget(self._file_footer_left)
        fl.addStretch()
        self._file_footer_right = QLabel("")
        self._file_footer_right.setStyleSheet("font-size: 12px; color: #424656; background: transparent; border: none;")
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
        # Pill (words match the dashboard status column)
        pill_name, pill_text = _pill_state(version_state, getattr(self, "_in_review", False))
        status_pill = getattr(self, "_status_pill", None)
        if status_pill is not None:
            status_pill.setObjectName(pill_name)
            status_pill.setText(pill_text.upper())
            status_pill.style().unpolish(status_pill)
            status_pill.style().polish(status_pill)
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
            header_link.setText(f"<a href='{url}' style='color:#004ccd; text-decoration:none;'>Open in Dataverse{' — DRAFT' if version_state=='DRAFT' else ''} ↗</a>")
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
                self._curation_pill.setVisible(True)
            else:
                self._curation_pill.setVisible(False)
        except Exception:
            pass

    def _refresh_curation_preview(self) -> None:
        """Populate Auto-Checks card with planned checks + lib availability."""
        try:
            from engine.runner import list_planned_checks
            staged = self._dl_mgr.files_dir(self._pid)
            if staged.exists():
                files = sorted(p for p in staged.rglob("*") if p.is_file())
            elif self._inventory:
                files = [Path(e.get("path", "")) for e in self._inventory]
            else:
                files = []
            planned = list_planned_checks(files)
            # Clear existing rows but keep the legend child
            legend = getattr(self, "_auto_legend", None)
            for i in reversed(range(self._auto_body.count())):
                item = self._auto_body.takeAt(i)
                w = item.widget() if item is not None else None
                if w is None or w is legend:
                    if w is not None:
                        self._auto_body.insertWidget(i, w)
                    continue
                w.deleteLater()
            if not files:
                if self._inventory is not None and len(self._inventory) == 0 and self._metadata is not None:
                    ph = QLabel("This dataset contains no files in Dataverse — file checks do not apply. Metadata checks above still apply.")
                else:
                    ph = QLabel("No file list yet — load metadata to see which checks will run.")
                ph.setWordWrap(True)
                ph.setStyleSheet("font-size: 12px; color: #57657a; background: transparent; border: none;")
                self._auto_body.addWidget(ph)
                self._auto_summary.setText("—")
                return
            # Count will_run
            will = sum(1 for p in planned if p.get("will_run"))
            self._auto_summary.setText(f"{will}/{len(planned)} will run")
            if self._report is not None:
                # Show actual results
                for c in self._report.dataset_checks:
                    row = self._auto_row(c.check_id, c.message[:90], c.passed, c.level)
                    self._auto_body.addWidget(row)
                for f in self._report.files:
                    for c in f.checks:
                        row = self._auto_row(c.check_id, f"{f.path}: {c.message[:70]}", c.passed, c.level)
                        self._auto_body.addWidget(row)
                if not self._report.dataset_checks and not any(f.checks for f in self._report.files):
                    ok = QLabel("All checks passed — no findings.")
                    ok.setStyleSheet("font-size: 12px; color: #004ccd; background: transparent; border: none;")
                    self._auto_body.addWidget(ok)
            else:
                for p in planned:
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
                    status = missing or ("Will run" if p["will_run"] else "No matching files")
                    # Interpret for row styling: missing = warn, will_run = pass, else neutral
                    if missing:
                        row = self._auto_row(p["check_id"], p["description"], False, "warning", badge="MISSING")
                    elif p["will_run"]:
                        row = self._auto_row(p["check_id"], p["description"], True, "info", badge="PASS")
                    else:
                        row = self._auto_row(p["check_id"], p["description"], True, "info", badge="—")
                        row.setStyleSheet("QFrame { background: #f2f3ff; border: 1px solid #e2e7ff; border-radius: 8px; }")
                    # Add subtitle with file_types + status
                    self._auto_body.addWidget(row)
        except Exception:
            pass
        try:
            selectable_labels(self._auto_card)
        except Exception:
            pass

    def _auto_row(self, check_id: str, desc: str, passed: bool, level: str, badge: str | None = None) -> QFrame:
        frame = QFrame()
        # Pick styling per level/passed
        if not passed and level in ("error", "warning"):
            frame.setStyleSheet("QFrame { background: #ffdad6; border: 1px solid #ffb4ab; border-radius: 8px; }")
            icon = "✕"
            icon_color = ERROR
            badge_text = badge or "FAIL"
            badge_bg = ERROR_CONTAINER
            badge_fg = ON_ERROR_CONTAINER
        elif passed and level == "warning" and "Missing" in (badge or desc):
            frame.setStyleSheet(f"QFrame {{ background: #fff0ef; border: 1px solid #ffb4ab; border-radius: 8px; }}")
            icon = "⚠"
            icon_color = ERROR
            badge_text = badge or "WARN"
            badge_bg = ERROR_CONTAINER
            badge_fg = ON_ERROR_CONTAINER
        elif passed:
            frame.setStyleSheet(f"QFrame {{ background: {SURFACE_CONTAINER}; border: 1px solid {OUTLINE_VARIANT}; border-radius: 8px; }}")
            icon = "✓"
            icon_color = PRIMARY
            badge_text = badge or "PASS"
            badge_bg = PRIMARY
            badge_fg = "#ffffff"
        else:
            frame.setStyleSheet(f"QFrame {{ background: {SURFACE_CONTAINER}; border: 1px solid {OUTLINE_VARIANT}; border-radius: 8px; }}")
            icon = "•"
            icon_color = ON_SURFACE_VARIANT
            badge_text = badge or "—"
            badge_bg = SURFACE_VARIANT
            badge_fg = ON_SURFACE_VARIANT
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(8)
        ic = QLabel(icon)
        ic.setFixedSize(20, 20)
        ic.setAlignment(Qt.AlignCenter)
        ic.setStyleSheet(f"QLabel {{ background: transparent; border: none; color: {icon_color}; font-weight: 700; font-size: 12px; }}")
        lay.addWidget(ic)
        txt = QVBoxLayout()
        txt.setSpacing(1)
        cid = QLabel(check_id)
        cid.setStyleSheet("font-size: 11px; font-weight: 600; color: #131b2e; background: transparent; border: none;")
        txt.addWidget(cid)
        d = QLabel(desc)
        d.setWordWrap(True)
        d.setStyleSheet("font-size: 11px; color: #424656; background: transparent; border: none;")
        txt.addWidget(d)
        lay.addLayout(txt, 1)
        badge_lbl = QLabel(badge_text)
        badge_lbl.setAlignment(Qt.AlignCenter)
        badge_lbl.setFixedHeight(20)
        badge_lbl.setMinimumWidth(56)
        badge_lbl.setStyleSheet(f"QLabel {{ background: {badge_bg}; color: {badge_fg}; border: 1px solid {OUTLINE_VARIANT}; border-radius: 6px; font-size: 10px; font-weight: 700; padding: 0 6px; }}")
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
            self._file_table.setRowCount(0)
            self._file_footer_left.setText("No files yet — load metadata to see the Dataverse file list.")
            self._file_footer_right.setText("")
        self._refresh_curation_preview()

    def _populate_file_table_staged(self, files: list[Path]) -> None:
        import mimetypes
        # Same sorting guard as the inventory path: inserting with sorting
        # on scrambles rows (empty cells, duplicated text).
        _was = self._file_table.isSortingEnabled()
        self._file_table.setSortingEnabled(False)
        try:
            self._file_table.setRowCount(len(files))
            self._staged_files = files
            total = 0
            for row, path in enumerate(files):
                rel = path.relative_to(self._dl_mgr.files_dir(self._pid)).as_posix() if path.is_relative_to(self._dl_mgr.files_dir(self._pid)) else path.name
                mime = mimetypes.guess_type(path.name)[0] or ""
                size = path.stat().st_size
                total += size
                ext = Path(rel).suffix.lower().lstrip(".").upper() or mime.split("/")[-1].upper() or "FILE"
                self._set_file_row(row, rel, size, ext, "staged", downloaded=True)
        finally:
            self._file_table.setSortingEnabled(_was)
        self._file_footer_left.setText(f"Showing {len(files)} of {len(files)} files")
        self._file_footer_right.setText(f"Total Size: {_human_size(total)}")
        # Staged fallback: every listed file is on disk by construction.
        try:
            self._dl_btn.setText(f"Downloaded ✓ ({len(files)})")
            self._dl_btn.setToolTip("All staged files are on disk — clicking verifies instead of re-downloading")
        except Exception:
            pass

    def _populate_from_inventory(self) -> None:
        self._all_file_rows: list[tuple[str, int, str, str]] = []
        total = 0
        for e in self._inventory:
            path = e.get("path", "")
            size = int(e.get("size_bytes", 0) or 0)
            total += size
            mime = e.get("mime_type", "")
            ext = Path(path).suffix.lower().lstrip(".").upper() or mime.split("/")[-1].upper() or "FILE"
            self._all_file_rows.append((path, size, ext, e.get("path", "")))
        self._apply_file_filter_internal()

    def _set_file_row(self, row: int, path: str, size: int, fmt: str, scan: str, downloaded: bool = False) -> None:
        # Read-only downloaded indicator (display only — clicks do nothing)
        dl_item = QTableWidgetItem()
        dl_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        dl_item.setCheckState(Qt.Checked if downloaded else Qt.Unchecked)
        dl_item.setTextAlignment(Qt.AlignCenter)
        dl_item.setToolTip(
            "Downloaded — staged locally" if downloaded else "Not downloaded yet"
        )
        self._file_table.setItem(row, 0, dl_item)
        # Filename cell (table font inherited; no per-cell override)
        name_item = QTableWidgetItem(f"  {path}")
        name_item.setToolTip(path)
        self._file_table.setItem(row, 1, name_item)
        size_item = QTableWidgetItem(_human_size(size))
        size_item.setFont(QFont("JetBrains Mono", 8))
        size_item.setForeground(QColor(ON_SURFACE_VARIANT))
        self._file_table.setItem(row, 2, size_item)
        fmt_item = QTableWidgetItem(fmt)
        fmt_item.setForeground(QColor(ON_SURFACE_VARIANT))
        self._file_table.setItem(row, 3, fmt_item)
        # Scan Status: pill-like label as text. "staged" means only that the
        # bytes are on disk — never report Clean before checks actually ran.
        if scan == "staged":
            scan = "Not checked"
        if scan in ("clean", "Clean"):
            scan_item = QTableWidgetItem("  Clean")
            scan_item.setForeground(QColor(PRIMARY))
        elif "Flagged" in scan or "issue" in scan.lower() or "error" in scan.lower():
            scan_item = QTableWidgetItem("  Flagged")
            scan_item.setForeground(QColor(ERROR))
        else:
            scan_item = QTableWidgetItem(f"  {scan}")
            scan_item.setForeground(QColor(ON_SURFACE_VARIANT))
        self._file_table.setItem(row, 4, scan_item)

    def _is_staged(self, path: str) -> bool:
        """True when the inventory path is staged locally.

        Checks the exact directoryLabel path first, then falls back to a
        basename match anywhere under files_dir: server bundles have not
        always preserved subfolders, and without the fallback every file
        reads as "not downloaded" (and Download All re-prompts forever).
        """
        try:
            root = self._dl_mgr.files_dir(self._pid)
            if not path:
                return False
            direct = self._dl_mgr._contained(root, path)
            if direct is not None and direct.is_file():
                return True
            base = Path(path).name
            if not base or not root.exists():
                return False
            for candidate in root.rglob(base):
                try:
                    if candidate.is_file() and candidate.name == base:
                        return True
                except Exception:
                    continue
            return False
        except Exception:
            return False

    def _refresh_download_state(self) -> None:
        """Reflect staged state on the Download button so it never surprises.

        Fully-staged inventories read "Downloaded ✓ (N)" with a tooltip
        saying the approval dialog will be skipped; partial stages show
        "Download All (k/N staged)". No inventory → plain "Download All".
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
                                except Exception:
                                    pass
                        except Exception:
                            continue
            except Exception:
                pass
            n_staged = sum(
                1 for (path, _s, _f, _o) in rows
                if (path in staged_paths) or (Path(path).name in staged_names)
            )
            total = len(rows)
            if total and n_staged >= total:
                btn.setText(f"Downloaded ✓ ({total})")
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
        filt = (self._file_filter.text() or "").lower().strip()
        rows = [r for r in getattr(self, "_all_file_rows", []) if not filt or filt in r[0].lower()]
        # Guard sorting while inserting (see _populate_completeness): with
        # sorting on, rows resort mid-insert and text lands in the wrong
        # rows — the "some rows are empty" bug.
        _was = self._file_table.isSortingEnabled()
        self._file_table.setSortingEnabled(False)
        try:
            self._file_table.setRowCount(len(rows))
            total = sum(r[1] for r in getattr(self, "_all_file_rows", []))
            for row, (path, size, fmt, _) in enumerate(rows):
                scan = "— run checks after download"
                # If report exists, reflect findings
                if self._report:
                    entry = next((f for f in self._report.files if f.path == path), None)
                    if entry:
                        fails = [c for c in entry.checks if not c.passed]
                        if fails:
                            scan = "Flagged"
                        elif entry.checks:
                            scan = "Clean"
                self._set_file_row(row, path, size, fmt, scan, self._is_staged(path))
        finally:
            self._file_table.setSortingEnabled(_was)
        self._file_footer_left.setText(f"Showing {len(rows)} of {len(getattr(self, '_all_file_rows', []))} files")
        self._file_footer_right.setText(f"Total Size: {_human_size(total)}" if total else "")
        self._refresh_download_state()

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

    # -- metadata loading -------------------------------------------------
    def _on_load_metadata(self) -> None:
        if self._meta_worker is not None and self._meta_worker.isRunning():
            self._set_status("Metadata load already running — please wait…")
            return
        self._load_meta_btn.setEnabled(False)
        self._set_status("Loading metadata from Dataverse…")
        self._progress.setVisible(True)
        self._progress.setRange(0, 0)
        self._meta_worker = MetadataWorker(self._config.dataverse.base_url, self._config.dataverse.api_token, self._pid, self)
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
            self._set_status("Could not load the file list (network or auth error) — metadata above may be partial. Check the log, then press Load metadata to retry.")
            self._file_table.setRowCount(0)
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
            self._file_table.setRowCount(0)
            self._all_file_rows = []
            self._file_footer_left.setText("This dataset contains no files.")
            self._file_footer_right.setText("")

    def _on_profile_changed(self) -> None:
        key = self._profile_combo.currentData()
        if isinstance(key, str):
            self._profile = key
        if self._metadata is not None:
            self._populate_completeness(self._metadata)

    def _populate_completeness(self, metadata: dict) -> None:
        results = check_metadata_completeness(metadata, profile=self._profile, inventory=self._inventory)
        complete = sum(1 for r in results if r["status"] == "complete")
        total = len(results)
        profile_label = PROFILES.get(self._profile, {}).get("label", self._profile)
        color = "#16a34a" if complete == total else "#d97706" if complete > total / 2 else "#ba1a1a"
        self._meta_summary.setText(
            f"<span style='font-weight:700;color:{color}'>{complete}/{total} fields complete</span> "
            f"<span style='color:{color}'>({'ready for review' if complete == total else 'needs attention'})</span> — "
            f"{profile_label}<br><span style='color:#57657a;font-size:11px'>Value shows what the depositor entered; Requirement describes what is expected.</span>"
        )
        # Also reflect in auto-checks header
        self._auto_summary.setText(f"{complete}/{total} metadata fields")
        # Full per-check table: Check | Value | Status (requirement in tooltip).
        # Sorting stays OFF while rows are inserted: with sorting on, each
        # setItem re-sorts immediately and later writes land in the wrong
        # visual rows (duplicated text in some rows, empty cells in others).
        _was_sorting = self._meta_check_table.isSortingEnabled()
        self._meta_check_table.setSortingEnabled(False)
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
                status_item = QTableWidgetItem("✓ Complete" if ok else "✗ Incomplete")
                status_item.setToolTip(r["requirement"])
                status_item.setForeground(QColor("#16a34a" if ok else ERROR))
                _bf = status_item.font()
                _bf.setBold(True)
                status_item.setFont(_bf)
                self._meta_check_table.setItem(row, 0, field_item)
                self._meta_check_table.setItem(row, 1, value_item)
                self._meta_check_table.setItem(row, 2, status_item)
        finally:
            self._meta_check_table.setSortingEnabled(_was_sorting)
        self._meta_check_table.resizeRowsToContents()
        # Fit the card to every row: header + rows, no internal scrollbar.
        try:
            header_h = self._meta_check_table.horizontalHeader().height() or 30
            row_h = self._meta_check_table.verticalHeader().defaultSectionSize() or 28
            self._meta_check_table.setFixedHeight(header_h + total * row_h + 4)
        except Exception:
            pass

    def _toggle_raw(self) -> None:
        vis = not self._raw_view.isVisible()
        self._raw_view.setVisible(vis)
        self._raw_btn.setText("Hide raw metadata ↑" if vis else "Show all metadata fields →")

    def _on_metadata_error(self, msg: str) -> None:
        self._progress.setVisible(False)
        self._load_meta_btn.setEnabled(True)
        self._set_status("")
        show_critical(self, "Metadata", f"Could not load metadata:\n{msg}")

    def _decision_choices(self) -> tuple[list[str], bool]:
        """(options, from_labels): instance curation labels when known."""
        try:
            allowed = [str(l).strip() for l in ((self._curation or {}).get("allowed") or []) if str(l).strip()]
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
        dlg = DownloadApprovalDialog(quote, self)
        if dlg.exec() != QDialog.Accepted:
            return
        self._dl_btn.setEnabled(False)
        self._set_status("Downloading bundle…")
        self._progress.setVisible(True)
        self._progress.setRange(0, 0)
        self._dl_worker = DownloadWorker(self._client, self._config.app.workspace, self._pid, self)
        self._dl_worker.progress.connect(lambda n: self._progress.setFormat(f"{n / 1024**2:.1f} MB"))
        self._dl_worker.finished.connect(self._on_download_finished)
        self._dl_worker.error.connect(self._on_download_error)
        self._dl_worker.finished.connect(self._dl_worker.deleteLater)
        self._dl_worker.error.connect(self._dl_worker.deleteLater)
        self._dl_worker.start()

    def _on_download_finished(self, staged: Path) -> None:
        self._progress.setVisible(False)
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

    def _on_download_error(self, msg: str) -> None:
        self._progress.setVisible(False)
        self._dl_btn.setEnabled(True)
        self._set_status("")
        show_critical(self, "Download", f"Download failed:\n{msg}")

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
        self._check_worker.finished.connect(self._on_checks_finished)
        self._check_worker.error.connect(self._on_checks_error)
        self._check_worker.finished.connect(self._check_worker.deleteLater)
        self._check_worker.error.connect(self._check_worker.deleteLater)
        self._check_worker.start()

    def _on_checks_finished(self, report) -> None:
        self._report = report
        self._progress.setVisible(False)
        self._check_btn.setEnabled(True)
        self._history_btn.setEnabled(True)
        # Update auto-checks to show results
        self._refresh_curation_preview()
        # Update file table scan status
        self._apply_file_filter_internal()
        findings = sum(1 for f in report.files for c in f.checks if not c.passed)
        self._set_status(f"Checks complete — {findings} finding(s) across {len(report.files)} files. Use Export report… to save.")
        self._log_action("checks_run", f"{findings} finding(s) across {len(report.files)} files", {"findings": findings, "files": len(report.files)})

    def _on_checks_error(self, msg: str) -> None:
        self._progress.setVisible(False)
        self._check_btn.setEnabled(True)
        self._set_status("")
        show_critical(self, "Checks", f"Checks failed:\n{msg}")

    def _on_file_selected(self, row: int, _col: int) -> None:
        if not self._report:
            return
        # Filename lives in column 1 (column 0 is the downloaded checkbox)
        item = self._file_table.item(row, 1)
        if not item:
            return
        path = item.text().strip()
        entry = next((f for f in self._report.files if f.path == path), None)
        if not entry:
            # Try inventory mapping
            return
        # Show details in status temporarily
        if entry.checks:
            first = entry.checks[0]
            self._set_status(f"{entry.path}: [{first.level}] {first.check_id}: {first.message} — {first.details}")
        else:
            self._set_status(f"{entry.path}: no findings (clean)")

    def _on_export(self) -> None:
        if not self._report:
            show_warning(self, "Export", "Run checks first.")
            return
        from PySide6.QtWidgets import QFileDialog
        try:
            self._dl_mgr.reports_dir(self._pid).mkdir(parents=True, exist_ok=True)
            start_dir = str(
                self._dl_mgr.reports_dir(self._pid)
                / f"{self._pid.replace(':', '_').replace('/', '_')}_report.json"
            )
        except Exception:
            start_dir = f"{self._pid.replace(':', '_').replace('/', '_')}_report.json"
        try:
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Export report",
                start_dir,
                "JSON (*.json)",
                options=QFileDialog.DontUseNativeDialog,
            )
        except Exception as exc:
            show_critical(self, "Export", f"Could not open the save dialog:\n{exc}")
            return
        if not path:
            return
        try:
            self._report.save(Path(path))
        except Exception as exc:
            show_critical(self, "Export", f"Could not write the report:\n{exc}")
            return
        self._log_action("exported", f"Report saved to {path}", {"path": str(path)})
        show_info(self, "Export", f"Report saved to {path}\n\n(Recorded in Dataset log.)")
