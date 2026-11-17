"""The state the dataset detail page and its sections share.

Every section of the dataset detail page is a mixin over this contract:
it declares the attributes the page owns — the dataset, its metadata,
and the widgets each section builds — so the type checker can see them
from any section.  The page itself (`ui/dataset/page.py`) assigns them;
the sections only read them and refresh what they own.

The contract also declares the calls the sections make *across* each
other (the workflow rail asks the header for a status line, the files
card asks the checks card to refresh, and so on).  Those methods are
implemented by the section that owns them; the declarations here are
the promise that the assembled page keeps them.  `ui/tests/
test_dataset_sections.py` checks that every one of them really is
implemented by a section, so a stub can never quietly swallow a call.

Keeping the contract in one place is what lets the 4,000-line page
become a dozen focused modules without any of them losing sight of the
state they share.
"""

from pathlib import Path
from typing import Any

from PySide6.QtCore import QTimer, Signal
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QLabel,
    QLineEdit,
    QListWidget,
    QMenu,
    QPlainTextEdit,
    QProgressBar,
    QScrollArea,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from curation.client import DataverseClient
from curation.config import Config
from curation.download_manager import DownloadManager
from ui.ring import RingProgress
from ui.table_layout import TableLayout
from ui.widgets import AppButton, AppTree, ElidedLabel, WorkflowRail
from ui.workers import CheckWorker, DownloadWorker, MetadataWorker


class DetailState(QWidget):
    """The attributes and the cross-section calls the detail page shares."""

    # -- the page's signals ------------------------------------------------
    # Declared here so every section can emit them; the facade inherits
    # them (a signal may only be declared once in the hierarchy).
    backRequested = Signal()
    metadataLoaded = Signal(str, dict, list)
    # emitted when the real title is known (header/metadata), so TopNav chips show titles
    titleChanged = Signal(str, str)

    # -- the dataset --------------------------------------------------------
    _config: Config
    _pid: str
    _title: str
    _client: DataverseClient
    _dl_mgr: DownloadManager
    _report: Any
    _inventory: list[dict[Any, Any]]
    _metadata: dict[Any, Any] | None
    _guestbook: dict[Any, Any] | None
    _account: dict[Any, Any]
    _curation: dict[Any, Any]
    _version_diff: dict[Any, Any] | None
    _versions: list[Any]
    _timestamps: dict[Any, Any]
    _review_submissions: list[Any]
    _in_review: bool
    _profile: str
    _ruleset: dict[Any, Any]

    # -- workflow state -----------------------------------------------------
    _changes_loaded: bool
    _inventory_ok: bool
    _staged_n: int
    _staged_total: int
    _last_export_path: str | None
    _decision_committed: bool
    _rail: WorkflowRail
    _nav_buttons: list[Any]
    _nav_card: QFrame
    _sidebar_collapse_btn: AppButton
    _sidebar_collapsed: bool
    _sidebar_user_collapsed: bool | None

    # -- response state -----------------------------------------------------
    _completeness_full: list[Any]
    _response_sections: list[Any]
    _response_dirty: bool
    _response_loading: bool
    _response_save_timer: QTimer | None
    _response_page: QWidget
    _response_list: QListWidget
    _response_edit: QTextEdit | QPlainTextEdit
    _response_hint: QLabel
    _response_summary: QLabel
    _response_dirty_lbl: QLabel
    _assessment_card: QFrame
    _notes_edit: QTextEdit | QPlainTextEdit

    # -- workers ------------------------------------------------------------
    _check_worker: CheckWorker | None
    _dl_worker: DownloadWorker | None
    _meta_worker: MetadataWorker | None

    # -- the page frame -----------------------------------------------------
    _pages: QStackedWidget
    _scroll: QScrollArea
    _canvas: QWidget
    _main_wrap: QVBoxLayout
    _side_scroll: QScrollArea
    _side_wrap: QVBoxLayout
    _sections_btn: AppButton
    _sections_menu: QMenu
    _table_layouts: dict[Any, Any]

    # -- the header ---------------------------------------------------------
    _id_badge: QLabel
    _status_pill: QLabel
    _curation_pill: QLabel
    _header_link: QLabel
    _depositor_lbl: QLabel
    _title_lbl: Any
    _status: QLabel
    _dl_btn: AppButton
    _dl_cancel_btn: AppButton
    _history_btn: AppButton
    _load_meta_btn: AppButton
    _check_btn: AppButton
    _checks_cancel_btn: AppButton
    _progress: QProgressBar
    _ring: RingProgress
    _in_response: bool

    # -- the metadata card --------------------------------------------------
    _meta_card: QFrame
    _meta_summary: QLabel
    _meta_filter: QComboBox
    _profile_combo: QComboBox
    _meta_reset_btn: AppButton
    _meta_check_tree: AppTree
    _meta_model: QStandardItemModel
    _meta_results: list[dict[str, Any]]
    _block_labels: dict[Any, Any]
    _raw_btn: AppButton
    _raw_view: QTextEdit | QPlainTextEdit

    # -- the file manifest card ---------------------------------------------
    _file_card: QFrame
    _file_table: None
    _file_tree: AppTree
    _file_filter: QLineEdit
    _scan_filter: QComboBox
    _file_reset_btn: AppButton
    _open_folder_btn: AppButton
    _expand_btn: AppButton
    _file_footer_left: ElidedLabel
    _file_footer_right: QLabel
    _file_checks_data: dict[str, list[Any]]
    _all_file_rows: list[tuple[str, int, str, str]]
    _staged_files: list[Path]
    _staged_names_cache: set[str]
    _staged_paths_cache: set[str]

    # -- the auto-checks card -----------------------------------------------
    _auto_card: QFrame
    _auto_summary: QLabel
    _auto_body: Any
    _auto_placeholder: QLabel

    # -- the version log card -----------------------------------------------
    _version_card: QFrame
    _version_summary: QLabel
    _version_tools: QWidget
    _version_reset_btn: AppButton
    _version_body: Any

    # -- the dataset log card -----------------------------------------------
    _dataset_log_card: QFrame
    _dataset_log: QListWidget

    # -- the assessment action ----------------------------------------------
    _decision_combo: QComboBox
    _decision_help: QLabel
    _commit_btn: AppButton

    # ------------------------------------------------------------------
    # The cross-section API: each method is implemented by the section
    # that owns it.  The bodies here never run — the assembled page
    # resolves every one of them to the section's implementation, and
    # `ui/tests/test_dataset_sections.py` checks that it does.
    # ------------------------------------------------------------------

    # -- the facade (ui/dataset/page.py) -----------------------------------
    def _layout_for(self, name: str, header) -> TableLayout:
        """Return the persisted-layout controller for a table header."""
        raise NotImplementedError

    def _track_table_widths(self, name: str, header) -> None:
        """Remember the widths a table header settled on."""
        raise NotImplementedError

    def _reset_table_view(self, name: str, header) -> bool:
        """Put a table header back to its fitted defaults."""
        raise NotImplementedError

    def _toggle_sidebar(self) -> None:
        """Fold the sidebar away, or open it again."""
        raise NotImplementedError

    def _goto_section(self, attr: str) -> None:
        """Scroll the main column to the section with the given anchor."""
        raise NotImplementedError

    # -- the workflow rail (ui/dataset/workflow_section.py) -----------------
    def _refresh_workflow(self) -> None:
        """Recompute the workflow steps and repaint the rail."""
        raise NotImplementedError

    # -- the metadata card (ui/dataset/metadata_section.py) -----------------
    def _populate_completeness(self, metadata: dict) -> None:
        """Show the completeness results for the given metadata."""
        raise NotImplementedError

    # -- the metadata loader (ui/dataset/metadata_load.py) ------------------
    def _on_profile_changed(self) -> None:
        """Handle a change of the metadata completeness profile."""
        raise NotImplementedError

    def _on_reset_meta_view(self) -> None:
        """Clear the metadata filter and show the metadata again."""
        raise NotImplementedError

    # -- the auto-checks card (ui/dataset/checks_section.py) ----------------
    def _auto_row(
        self, check_id: str, desc: str, passed: bool, level: str, badge: str | None = None
    ) -> QFrame:
        """Build the row that shows one check result."""
        raise NotImplementedError

    def _on_tree_clicked(self, index) -> None:
        """Show the detail of the check row the curator clicked."""
        raise NotImplementedError

    # -- the file manifest card (ui/dataset/files_section.py) ---------------
    def _refresh_files_placeholder(self) -> None:
        """Refresh the placeholder that stands in for an empty manifest."""
        raise NotImplementedError

    def _populate_from_inventory(self) -> None:
        """Fill the manifest from the dataset's inventory."""
        raise NotImplementedError

    def _apply_file_filter_internal(self) -> None:
        """Apply the manifest filter without going through the signal."""
        raise NotImplementedError

    # -- the version log card (ui/dataset/versions_section.py) --------------
    def _populate_version_diff(self) -> None:
        """Fill the version card with the selected version's diff."""
        raise NotImplementedError

    # -- the dataset log card (ui/dataset/log_rail.py) ---------------------
    def _log_action(self, action: str, notes: str = "", details: dict | None = None) -> None:
        """Record one action in the dataset's own log."""
        raise NotImplementedError

    def _refresh_dataset_log(self) -> None:
        """Repaint the dataset log card."""
        raise NotImplementedError

    # -- the response page (ui/dataset/response_section.py) -----------------
    def _show_review_page(self) -> None:
        """Show the review page (the assessment and the findings)."""
        raise NotImplementedError

    def _show_response_page(self) -> None:
        """Show the response page (the draft editor)."""
        raise NotImplementedError

    def _refresh_response(self, force: bool = False) -> None:
        """Rebuild the findings list and the draft."""
        raise NotImplementedError

    def _staged_dir_or_none(self) -> Path | None:
        """Return the staged directory of this dataset, when there is one."""
        raise NotImplementedError

    # -- the assessment action (ui/dataset/actions_section.py) --------------
    def _build_assessment_card(self) -> QFrame:
        """Build the card that holds the assessment action."""
        raise NotImplementedError

    def _refresh_decision_options(self) -> None:
        """Fill the decision combo with the instance's curation labels."""
        raise NotImplementedError

    # -- the header (ui/dataset/header_section.py) -------------------------
    def _update_header_link(self, metadata: dict | None = None) -> None:
        """Point the title link at the dataset's landing page."""
        raise NotImplementedError

    def _update_curation_pill(self) -> None:
        """Repaint the pill that shows the dataset's curation state."""
        raise NotImplementedError

    def _refresh_curation_preview(self) -> None:
        """Refresh the preview of the labels the curator can push."""
        raise NotImplementedError

    def _set_status(self, msg: str) -> None:
        """Show a message in the page's status line."""
        raise NotImplementedError

    def _on_ring_fraction(self, fraction: float) -> None:
        """Move the progress ring to the given fraction."""
        raise NotImplementedError

    def _hide_ring(self) -> None:
        """Hide the progress ring."""
        raise NotImplementedError
