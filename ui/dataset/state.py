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

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QModelIndex, QTimer, Signal
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QScrollArea,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from curation.client import DataverseClient
from curation.config import Config
from curation.download_manager import DownloadManager
from ui.table_layout import TableLayout
from ui.widgets import AppButton, AppTree, ElidedLabel, WorkflowRail
from ui.workers import CheckWorker, DownloadWorker, MetadataWorker

if TYPE_CHECKING:
    from ui.preview import PreviewCard


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
    _versions: Any
    _timestamps: Any
    _review_submissions: Any
    _in_review: bool
    _profile: str
    _ruleset: dict[Any, Any]
    #: What the dashboard already knew about this dataset (its search
    #: payload's state and access facts). It saves the detail page from
    #: asking for versions that cannot exist.
    _dataset_hint: dict[Any, Any]
    #: The open depositor follow-up for this dataset, refreshed from
    #: storage on load and after a decision commits; None when closed.
    _follow_up: dict[Any, Any] | None
    #: The curator's answers to the sensitivity (ethics) questions.
    _sensitivity_answers: dict[Any, Any]

    # -- workflow state -----------------------------------------------------
    _changes_loaded: bool
    _inventory_ok: bool
    _staged_n: int
    _staged_total: int
    _last_export_path: str | None
    _decision_committed: bool
    _rail: WorkflowRail
    _sidebar_collapsed: bool
    _sidebar_user_collapsed: bool | None
    #: The button that folds the sidebar away (the narrow-window toggle).
    _sidebar_toggle_btn: AppButton
    #: The keyboard shortcuts the page installed, so it can drop them.
    _shortcuts: list[Any]
    #: Fires once the page has settled, so a slow instance can load the
    #: metadata without fighting the curator's first clicks.
    _auto_load_timer: QTimer

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
    _table_layouts: dict[Any, Any]

    # -- the header ---------------------------------------------------------
    _id_badge: Any
    _status_pill: QLabel
    _curation_pill: QLabel
    _depositor_lbl: QLabel
    _title_lbl: Any
    _status: QLabel
    _dl_btn: AppButton
    _dl_cancel_btn: AppButton
    _load_meta_btn: AppButton
    _run_after_download: bool
    _check_btn: AppButton
    #: True while the checks run and the primary button reads "Cancel".
    _checks_running: bool
    _checks_cancel_btn: AppButton
    _status_widget: Any
    _in_response: bool
    #: The row that carries the status line (an icon plus the message).
    _status_row: QWidget
    _status_icon: QLabel
    #: The verdict card's widgets (the overall level and its reasons).
    _verdict_card: QFrame
    _verdict_icon: QLabel
    _verdict_label: QLabel
    _verdict_chips: QHBoxLayout
    #: The keys of the findings the verdict was computed from.
    _finding_keys: list[Any]

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
    #: The rows the metadata card is built from (one per metadata entry).
    _meta_body: QWidget
    _meta_body_lay: QVBoxLayout
    _meta_row_results: list[dict[str, Any]]
    _meta_row_widgets: list[tuple[QFrame, int]]
    #: The results the curator chose not to look at (skipped checks).
    _unchecked_results: list[Any]
    #: Whether the metadata card has been populated with a real dataset.
    _meta_loaded: bool

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
    #: The button that writes a variable-dictionary draft for a tabular file.
    _dictionary_btn: AppButton
    #: The card that previews a file's contents.
    _preview_card: PreviewCard | None

    # -- the auto-checks section (inside the Dataset checks card) -------------
    _auto_card: QWidget
    _auto_summary: QLabel
    _auto_body: Any
    _auto_placeholder: QLabel
    #: The summary line without the finding counts, so the counts can be
    #: repainted without losing the wording.
    _auto_summary_base: str
    #: The finding dispositions the curator has already chosen.
    _dispositions_cache: dict[Any, Any]
    # Test fixtures poke these onto the view (see ui/tests); declared so
    # mypy accepts the pattern without weakening the shape checks.
    _logged: list[tuple[Any, ...]]
    _status_msgs: list[str]
    _statuses: Any
    _jumps: Any
    _responses: Any

    # -- the version log card -----------------------------------------------
    _version_card: QFrame
    _version_summary: QLabel
    _version_body: Any

    # -- the dataset log card -----------------------------------------------
    _dataset_log_card: QFrame
    _dataset_log: QListWidget

    # -- the assessment action ----------------------------------------------
    _decision_combo: QComboBox
    _decision_help: QLabel
    _commit_btn: AppButton
    #: The button that records the curation decision in the instance.
    _record_btn: AppButton
    #: The open depositor follow-up card and its parts.
    _follow_up_card: QFrame
    _follow_up_icon: QLabel
    _follow_up_label: QLabel
    _follow_up_checks_btn: AppButton
    _follow_up_changes_btn: AppButton
    #: The sensitivity (ethics) review card and its parts.
    _sensitivity_card: QFrame
    _sensitivity_status: QLabel
    _sensitivity_combos: dict[str, QComboBox]

    # ------------------------------------------------------------------
    # The cross-section API: each method is implemented by the section
    # that owns it.  The bodies here never run — the assembled page
    # resolves every one of them to the section's implementation, and
    # `ui/tests/test_dataset_sections.py` checks that it does.
    # ------------------------------------------------------------------

    # -- the facade (ui/dataset/page.py) -----------------------------------
    def _layout_for(self, name: str, header: QHeaderView) -> TableLayout:
        """Return the persisted-layout controller for a table header."""
        raise NotImplementedError

    def _track_table_widths(self, name: str, header: QHeaderView) -> None:
        """Remember the widths a table header settled on."""
        raise NotImplementedError

    def _reset_table_view(self, name: str, header: QHeaderView) -> bool:
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

    def _on_workflow_step(self, key: str) -> None:
        """Jump to (or trigger) a workflow step."""
        raise NotImplementedError

    def _refresh_verdict(self) -> None:
        """Repaint the verdict card from the current report."""
        raise NotImplementedError

    def _refresh_follow_up(self) -> None:
        """Paint the follow-up banner from in-memory + stored state."""
        raise NotImplementedError

    # -- the metadata loader (ui/dataset/metadata_load.py) ------------------
    def _on_load_metadata(self) -> None:
        """Load (or refresh) the metadata for this dataset."""
        raise NotImplementedError

    # -- the metadata card (ui/dataset/metadata_section.py) -----------------
    def _populate_completeness(self, metadata: dict[str, Any]) -> None:
        """Show the completeness results for the given metadata."""
        raise NotImplementedError

    # -- the metadata loader (ui/dataset/metadata_load.py) ------------------
    def _on_profile_changed(self) -> None:
        """Handle a change of the metadata completeness profile."""
        raise NotImplementedError

    # -- the auto-checks card (ui/dataset/checks_section.py) ----------------
    def _auto_row(
        self,
        check_id: str,
        desc: str,
        passed: bool,
        level: str,
        badge: str | None = None,
        disposition_key: str = "",
        detail_lines: list[tuple[str, bool]] | None = None,
    ) -> QFrame:
        """Build the row that shows one check result."""
        raise NotImplementedError

    def _on_tree_clicked(self, index: QModelIndex) -> None:
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
    def _log_action(
        self, action: str, notes: str = "", details: dict[str, Any] | None = None
    ) -> None:
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

    # -- cross-section calls from master (implemented by the checks, files,
    #    actions and log-rail sections) --------------------------------------
    def _note_follow_up_update(self) -> None:
        """Persist the observed draft lastUpdateTime for an open follow-up."""
        raise NotImplementedError

    def _refresh_sensitivity_card(self) -> None:
        """Repaint the sensitivity (ethics) review card."""
        raise NotImplementedError

    def _build_sensitivity_card(self) -> QFrame:
        """Build the sensitivity (ethics) review card."""
        raise NotImplementedError

    def _dispositions_map(self) -> dict[str, Any]:
        """Return the finding dispositions already recorded for the pid."""
        raise NotImplementedError

    def _set_auto_summary(self, text: str) -> None:
        """Set the Auto-Checks summary line (the counts are repainted later)."""
        raise NotImplementedError

    def _on_run_checks(self) -> None:
        """Stage the dataset if needed, then run the auto-check suite."""
        raise NotImplementedError

    def _start_checks(self) -> None:
        """Start the check worker against the already-staged files."""
        raise NotImplementedError

    def _on_download(self) -> None:
        """Open the approval gate and stage the dataset bundle."""
        raise NotImplementedError

    def _refresh_metadata_button(self) -> None:
        """Load vs Reload Metadata on the Dataset checks section header."""
        raise NotImplementedError

    def _apply_auto_filter(self, *args: Any) -> None:
        """Apply the Auto-Checks severity filter to the card rows."""
        raise NotImplementedError

    def _on_disposition_changed(self, key: str, token: str) -> None:
        """Persist a changed finding disposition."""
        raise NotImplementedError

    def _on_edit_disposition_note(self, key: str, token: str = "") -> None:
        """Edit the note on a finding disposition."""
        raise NotImplementedError

    def _show_disposition_menu(self, key: str, global_pos: Any) -> None:
        """Pop the right-click disposition menu for a finding."""
        raise NotImplementedError

    def _refresh_finding_summary(self) -> None:
        """Repaint the finding summary row on the Auto-Checks card."""
        raise NotImplementedError

    def _on_file_context_menu(self, pos: Any) -> None:
        """Pop the right-click menu on a file row."""
        raise NotImplementedError

    def _show_preview_for_file(self, path: str) -> None:
        """Preview the given file in the preview card."""
        raise NotImplementedError

    def _state(self) -> Any:
        """Return a session-scoped storage handle for this dataset."""
        raise NotImplementedError

    # -- the header (ui/dataset/header_section.py) -------------------------
    def _update_header_link(self, metadata: dict[str, Any] | None = None) -> None:
        """Point the DOI chip at the dataset's Dataverse landing page."""
        raise NotImplementedError

    def _check_button_text(self) -> str:
        """Primary action label — Run / Run file / Re-run Automatic Checks."""
        raise NotImplementedError

    def _refresh_check_button(self) -> None:
        """Keep the primary button's label in step with the current report."""
        raise NotImplementedError

    def _refresh_header_actions(self) -> None:
        """Repaint the section-header buttons and the primary label."""
        raise NotImplementedError

    def _update_curation_pill(self) -> None:
        """Repaint the pill that shows the dataset's curation state."""
        raise NotImplementedError

    def _refresh_curation_preview(self) -> None:
        """Refresh the preview of the labels the curator can push."""
        raise NotImplementedError

    def _set_status(self, msg: str, tone: str = "info") -> None:
        """Show a message in the page's status line."""
        raise NotImplementedError

    def _on_cancel_checks_click(self) -> None:
        """Ask the running check pass to stop at the next checkpoint."""
        raise NotImplementedError

    def _refresh_rail_counts(self, summary: Any = None) -> None:
        """Feed the rail's result pills from a check-run summary."""
        raise NotImplementedError

    def _show_status_running(
        self, title: str, detail: str = "", fraction: float | None = None
    ) -> None:
        """Show the compact status widget mid-work (dv-gfx.3)."""
        raise NotImplementedError

    def _show_status_complete(self, title: str, detail: str = "") -> None:
        """Show the success face of the compact status widget."""
        raise NotImplementedError

    def _show_status_error(self, title: str, detail: str = "") -> None:
        """Show the error face of the compact status widget."""
        raise NotImplementedError

    def _status_context(self) -> str:
        """Short count detail for the compact widget, from state in memory."""
        raise NotImplementedError
