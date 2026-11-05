"""Settings pane: Dataverse chooser, credentials, workspace and tools.

The curator picks which Dataverse to work against (preset for the Borealis
demo at demo.borealisdata.ca plus a Custom entry for any other instance),
enters an API token/collection alias, and chooses a local workspace.
Persists to config.json via config.Config.

Presented as a non-modal stack page (not a blocking dialog): Save persists
and emits `saved`. Closed via the Settings nav toggle (no Close button by
design). Edits are tracked against a baseline snapshot; leaving with unsaved
changes asks Save / Discard / Cancel instead of silently discarding them.
"""

import importlib.metadata
import subprocess
import sys
from pathlib import Path

import requests
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from config import PRESETS, Config
from dataverse_client import DataverseClient
from ui.dialogs import confirm, confirm_save_discard_cancel, show_critical, show_info, show_warning
from ui.i18n import t
from ui.theme import (
    BACKGROUND,
    ERROR,
    MUTED_BG,
    MUTED_BORDER,
    MUTED_TEXT,
    ON_SECONDARY_CONTAINER,
    ON_SURFACE,
    ON_SURFACE_VARIANT,
    OUTLINE_VARIANT,
    PRIMARY,
    SECONDARY_CONTAINER,
    SUCCESS_DARK,
    SURFACE_CONTAINER_HIGH,
    SURFACE_CONTAINER_LOWEST,
    action_button_style,
    enable_table_copy,
    selectable_labels,
)
from ui.widgets import (
    AppButton,
    AppTable,
    PaneFooter,
    flush_table_style,
    make_combo,
    make_line_edit,
)

# Compact face for buttons living inside table action cells: the standard
# action_button_style padding (7px 14px) made "Reinstall"+"Uninstall" need
# 294px against a 240px column, clipping both buttons. Same kit look, cell-
# sized padding.
_CELL_BTN_STYLE = (
    f"QPushButton {{ background: {SURFACE_CONTAINER_LOWEST}; color: {ON_SURFACE}; "
    f"border: 1px solid {OUTLINE_VARIANT}; border-radius: 6px; padding: 0 8px; "
    "font-weight: 600; font-size: 12px; }"
    f"QPushButton:hover {{ background: {SURFACE_CONTAINER_HIGH}; border: 1px solid {PRIMARY}; }}"
    f"QPushButton:pressed {{ background: {SECONDARY_CONTAINER}; }}"
    f"QPushButton:disabled {{ background: {MUTED_BG}; color: {MUTED_TEXT}; "
    f"border: 1px solid {MUTED_BORDER}; }}"
)


class _ShellWorker(QThread):
    """One blocking call (pip / connection probe) off the GUI thread."""

    done = Signal(bool, str, str)  # ok, title, message

    def __init__(self, func, parent=None):
        super().__init__(parent)
        self._func = func

    def run(self) -> None:
        try:
            ok, title, message = self._func()
        except Exception as exc:  # never leave the UI hanging silently
            ok, title, message = False, "Extensions", f"Failed:\n{exc}"
        self.done.emit(ok, title, message)


class _SizeWorker(QThread):
    """Compute package sizes off the GUI thread; emits dict[size-key → human size]."""

    done = Signal(dict)

    def __init__(self, func, parent=None):
        super().__init__(parent)
        self._func = func

    def run(self) -> None:
        try:
            result = self._func()
        except Exception:
            result = {}
        self.done.emit(result if isinstance(result, dict) else {})


class SettingsPane(QWidget):
    """Edit dataverse.base_url/api_token/subtree, app.workspace and tool paths.

    Persists to config.json on Save.
    """

    saved = Signal()
    # Emitted after any successful persist (explicit Save or save-on-leave).
    # MainWindow refreshes the dashboard from this without closing the pane.
    configurationChanged = Signal()

    # Format-check libraries (pip name, import name, description).
    # Heavy binary libs are excluded from the lite build; pure-Python format
    # helpers ship in lite. Required scanners (piigex, hush-scan) are bundled
    # in both builds and listed here so install status stays visible.
    EXTENSIONS = [
        ("pyreadstat", "pyreadstat", t("settings.extensions.used_pyreadstat")),
        ("netCDF4", "netCDF4", t("settings.extensions.used_netcdf4")),
        ("h5py", "h5py", t("settings.extensions.used_h5py")),
        ("tifffile", "tifffile", t("settings.extensions.used_tifffile")),
        ("Pillow", "PIL", t("settings.extensions.used_pillow")),
        ("pypdf", "pypdf", t("settings.extensions.used_pypdf")),
        ("lxml", "lxml", t("settings.extensions.used_lxml")),
        ("openpyxl", "openpyxl", t("settings.extensions.used_openpyxl")),
        ("chardet", "chardet", t("settings.extensions.used_chardet")),
        ("piigex", "piigex", t("settings.extensions.used_piigex")),
        ("hush-scan", "hush", t("settings.extensions.used_hush")),
    ]

    def __init__(self, config: Config, parent=None) -> None:
        super().__init__(parent)
        self._config = config
        # Scoped to self: a bare `background` rule would act subtree-wide
        # and override app-level backgrounds (e.g. the extensions table).
        self.setObjectName("SettingsDialog")
        self.setStyleSheet(f"QWidget#SettingsDialog {{ background: {BACKGROUND}; }}")
        # Baseline-based dirty tracking: capture the saved values after a
        # reload, compare on every edit, and guard every exit.
        self._loading = False
        self._dirty = False
        self._baseline: dict[str, str] = {}

        outer = QVBoxLayout()
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(16)

        heading = QLabel(t("settings.title"))
        heading.setStyleSheet(f"font-size: 22px; font-weight: 600; color: {ON_SURFACE}; border: none; background: transparent;")
        outer.addWidget(heading)
        sub = QLabel(t("settings.subtitle"))
        sub.setStyleSheet(f"font-size: 13px; color: {ON_SECONDARY_CONTAINER}; border: none; background: transparent;")
        sub.setWordWrap(True)
        outer.addWidget(sub)


        tabs = QTabWidget()

        # General tab
        general = QWidget()
        form = QFormLayout(general)
        form.setContentsMargins(16, 16, 16, 16)
        form.setSpacing(12)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(12)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.DontWrapRows)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.setFormAlignment(Qt.AlignTop)

        self.preset_combo = make_combo(list(PRESETS), min_width=200)
        form.addRow(t("settings.fields.preset"), self.preset_combo)

        self.url_edit = make_line_edit(t("settings.fields.url_placeholder"))
        form.addRow(t("settings.fields.url"), self.url_edit)

        self.token_edit = make_line_edit(
            t("settings.fields.token_placeholder"), password=True
        )
        form.addRow(t("settings.fields.token"), self.token_edit)

        self.subtree_edit = make_line_edit(
            t("settings.fields.collection_placeholder")
        )
        form.addRow(t("settings.fields.collection"), self.subtree_edit)

        ws_row = QHBoxLayout()
        ws_row.setContentsMargins(0, 0, 0, 0)
        ws_row.setSpacing(8)
        self.workspace_edit = make_line_edit()
        browse_btn = AppButton(t("common.browse"), kind="secondary", size="sm")
        browse_btn.setStyleSheet(action_button_style(False))
        browse_btn.clicked.connect(self._browse_workspace)
        ws_row.addWidget(self.workspace_edit, 1)
        ws_row.addWidget(browse_btn, 0)
        form.addRow(t("settings.fields.workspace"), ws_row)

        test_btn = AppButton(
            t("settings.fields.test_connection"), kind="secondary", size="sm"
        )
        test_btn.setStyleSheet(action_button_style(False))
        test_btn.clicked.connect(self._test_connection)
        self._test_btn = test_btn
        
        # Save/Revert live in the shared PaneFooter below the tabs so both
        # General and Extensions expose the same controls.
        conn_row = QHBoxLayout()
        conn_row.setContentsMargins(0, 0, 0, 0)
        conn_row.setSpacing(8)
        conn_row.addWidget(test_btn, 0)
        self._conn_status = QLabel("")
        self._conn_status.setWordWrap(True)
        self._conn_status.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
        )
        self._conn_status.setStyleSheet(f"font-size: 12px; color: {ON_SECONDARY_CONTAINER}; border: none; background: transparent;")
        conn_row.addWidget(self._conn_status, 1)
        form.addRow("", conn_row)
        # A stale verdict must not survive a URL edit.
        self.url_edit.textChanged.connect(lambda _t: self._conn_status.setText(""))
        self.url_edit.textChanged.connect(lambda _t: self._clear_user_info())
        self.token_edit.textChanged.connect(lambda _t: self._clear_user_info())
        self.subtree_edit.textChanged.connect(lambda _t: self._clear_collection_role())

        # Signed-in user (identity from GET /api/users/:me, collection
        # role by matching that identifier in the alias assignments).
        user_heading = QLabel(t("settings.user.heading"))
        user_heading.setStyleSheet(
            f"font-size: 12px; font-weight: 600; color: {ON_SURFACE_VARIANT}; "
            "border: none; background: transparent; padding-top: 8px;"
        )
        form.addRow(user_heading)
        self._user_identifier = self._make_user_value()
        form.addRow(t("settings.user.identifier"), self._user_identifier)
        self._user_display = self._make_user_value()
        form.addRow(t("settings.user.display"), self._user_display)
        self._user_super = self._make_user_value()
        form.addRow(t("settings.user.superuser"), self._user_super)
        self._user_affil = self._make_user_value()
        form.addRow(t("settings.user.affiliation"), self._user_affil)
        self._user_role = self._make_user_value()
        form.addRow(t("settings.user.collection_role"), self._user_role)
        self._user_status = QLabel("")
        self._user_status.setWordWrap(True)
        self._user_status.setStyleSheet(f"font-size: 11px; color: {ON_SECONDARY_CONTAINER}; border: none; background: transparent;")
        # Single-widget rows span both form columns — the hint must run the
        # full width instead of wrapping in the narrow value column
        # (2026-10-02 minor: the hint rendered as a cramped block).
        form.addRow(self._user_status)

        tabs.addTab(general, t("settings.tabs.general"))

        # Extensions tab: optional libs + external binaries.
        # Flush tab page (card pattern): zero layout margins; the table
        # bleeds edge-to-edge while the hint/buttons below keep an inset.
        # Table is first (square top meets the tab bar) but not last
        # (square bottom meets the inset content below).
        ext_tab = QWidget()
        ext_layout = QVBoxLayout(ext_tab)
        ext_layout.setContentsMargins(0, 0, 0, 0)
        ext_layout.setSpacing(0)
        self.ext_table = AppTable(
            [
                t("settings.extensions.columns.package"),
                t("settings.extensions.columns.installed"),
                t("settings.extensions.columns.size"),
                t("settings.extensions.columns.used_for"),
                t("settings.extensions.columns.action"),
            ],
            widths={0: 110, 1: 130, 2: 90, 3: 200, 4: 300},
            row_height=34,
            stretch_last=False,
            # NOTE: sorting stays OFF here on purpose — per-row action
            # buttons are cell *widgets*, which Qt does not move when rows
            # sort (the original dashboard-garbling bug). All item-only
            # tables sort; this one must not.
            sortable=False,
        )
        # Used-for column absorbs leftover width.
        self.ext_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        # Qt derives CELL-WIDGET geometry from the item content box whenever
        # a stylesheet is active: the app's `QTableWidget::item` rule
        # (padding 10px 12px + 1px border-bottom) shrank every action cell to
        # 13px inside a 34px row, clipping the 28px buttons to hollow slivers
        # that painted over the Used-for column (2026-10-02). Zeroing the
        # vertical padding here (12px horizontal inset kept, item text stays
        # centered at the same y) lets the cell fill the row; the row
        # separator still comes from the app rule's border-bottom.
        self.ext_table.setStyleSheet(
            flush_table_style(last=False)
            + "QTableWidget::item { padding: 0px 12px; }"
        )
        # Remember the user's column widths/order across sessions.
        try:
            from storage import (
                restore_table_state,
                save_table_state,
                snapshot_table_view,
            )

            _ext_header = self.ext_table.horizontalHeader()
            self._ext_snap = snapshot_table_view(_ext_header)
            if restore_table_state(self._config.app.workspace, "extensions", _ext_header):
                self.ext_table.disable_auto_fit()
            _ext_header.sectionResized.connect(
                lambda *a: save_table_state(
                    self._config.app.workspace, "extensions", _ext_header
                )
            )
            _ext_header.sectionMoved.connect(
                lambda *a: save_table_state(
                    self._config.app.workspace, "extensions", _ext_header
                )
            )
        except Exception:
            pass
        ext_layout.addWidget(self.ext_table, 1)
        ext_hint = QLabel(t("settings.extensions.hint"))
        ext_hint.setWordWrap(True)
        bottom = QWidget()
        bottom_lay = QVBoxLayout(bottom)
        bottom_lay.setContentsMargins(12, 8, 12, 8)
        bottom_lay.addWidget(ext_hint)
        ext_btn_row = QHBoxLayout()
        self.ext_status = QLabel("")
        ext_btn_row.addWidget(self.ext_status, 1)
        refresh_ext_btn = AppButton(t("common.refresh"), kind="secondary")
        refresh_ext_btn.setStyleSheet(action_button_style(False))
        refresh_ext_btn.setToolTip(t("settings.extensions.refresh_tip"))
        refresh_ext_btn.clicked.connect(self._refresh_sizes)
        ext_btn_row.addWidget(refresh_ext_btn)
        install_all_btn = AppButton(
            t("settings.extensions.install_all"), kind="secondary"
        )
        install_all_btn.setStyleSheet(action_button_style(False))
        install_all_btn.clicked.connect(self._install_all)
        ext_btn_row.addWidget(install_all_btn)
        reset_cols_btn = AppButton(
            t("settings.extensions.reset_columns"), kind="secondary"
        )
        reset_cols_btn.setStyleSheet(action_button_style(False))
        reset_cols_btn.setToolTip(t("settings.extensions.reset_tip"))
        reset_cols_btn.clicked.connect(self._on_reset_ext_view)
        ext_btn_row.addWidget(reset_cols_btn)
        bottom_lay.addLayout(ext_btn_row)
        ext_layout.addWidget(bottom)
        tabs.addTab(ext_tab, t("settings.tabs.extensions"))
        # Outline wrapper: the tab pane cannot draw rounded corners itself
        # (Qt drops the arcs — see theme.py TabWidget note), so a plain
        # card draws the outline. Standard card inset keeps flush children
        # (e.g. the Extensions table) clear of the corner arcs.
        tabs_card = QFrame()
        tabs_card.setObjectName("Card")
        card_lay = QVBoxLayout(tabs_card)
        card_lay.setContentsMargins(16, 12, 16, 12)
        card_lay.setSpacing(8)
        card_lay.addWidget(tabs)
        outer.addWidget(tabs_card, 1)

        # Shared Save/Revert footer — the same component Review configuration
        # uses, so both pages speak one visual language.
        self._footer = PaneFooter(
            self,
            save_tip="Save to config.json (Ctrl+S)",
            revert_tip="Discard unsaved edits and reload the saved configuration",
        )
        self._footer.saveRequested.connect(self._on_save)
        self._footer.revertRequested.connect(self._on_revert)
        outer.addWidget(self._footer)
        # Compatibility aliases for callers/tests that addressed the buttons.
        self._save_btn = self._footer.save_btn
        self._revert_btn = self._footer.revert_btn

        for _edit in (self.url_edit, self.token_edit, self.subtree_edit, self.workspace_edit):
            _edit.textChanged.connect(self._refresh_dirty)
        self.preset_combo.currentTextChanged.connect(self._refresh_dirty)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(outer)

        try:
            from PySide6.QtGui import QKeySequence as _QKS
            from PySide6.QtGui import QShortcut as _QSC

            _QSC(_QKS("Ctrl+S", _QKS.PortableText), self, self._on_save)  # type: ignore[arg-type]
        except Exception:
            pass

        self.preset_combo.currentTextChanged.connect(self._on_preset_changed)
        self._tool_paths: dict = {}
        self._shell_worker: _ShellWorker | None = None
        self._size_worker: _SizeWorker | None = None
        # Package-size cache: os.walk per package is seconds-slow, so sizes
        # are computed once per pane lifetime; Refresh re-walks on demand.
        # First paint shows "…" and fills in from a background worker so the
        # GUI thread never blocks on importlib.metadata + os.walk.
        self._size_cache: dict[str, str] = {}
        self.reload()
        self._start_size_worker()
        try:
            selectable_labels(self)
            enable_table_copy(self.ext_table)
        except Exception:
            pass

    def _start_size_worker(self) -> None:
        """Compute package sizes off the GUI thread; patch rows when done."""
        if getattr(self, "_size_worker", None) is not None and self._size_worker.isRunning():
            return
        rows = list(self.EXTENSIONS)

        def _work() -> dict[str, str]:
            out: dict[str, str] = {}
            for pip_name, import_name, _desc in rows:
                out[import_name or pip_name] = SettingsPane._package_size(pip_name, import_name)
            return out

        def _done(sizes: dict[str, str]) -> None:
            self._size_cache.update(sizes)
            try:
                self._apply_size_cache()
            except Exception:
                pass

        worker = _SizeWorker(_work, self)
        worker.done.connect(_done)
        worker.finished.connect(self._clear_size_worker)
        worker.finished.connect(worker.deleteLater)
        self._size_worker = worker
        worker.start()

    def _clear_size_worker(self) -> None:
        self._size_worker = None

    def _apply_size_cache(self) -> None:
        """Write cached sizes into the extensions table Size column (index 2)."""
        for row, (pip_name, import_name, _desc) in enumerate(self.EXTENSIONS):
            key = import_name or pip_name
            size = self._size_cache.get(key)
            if size:
                item = self.ext_table.item(row, 2)
                if item is None:
                    item = QTableWidgetItem(size)
                    self.ext_table.setItem(row, 2, item)
                else:
                    item.setText(size)

    def reload(self) -> None:
        """Re-read config + extension state (called each time the pane opens)."""
        self._load_from_config()
        self._refresh_extensions()
        self._refresh_user_info()

    def _refresh_sizes(self) -> None:
        """Clear the size cache and re-walk installed packages on demand."""
        self._size_cache = {}
        self._refresh_extensions()
        self._start_size_worker()

    def _on_reset_ext_view(self) -> None:
        """Reset the extensions table to its construction view."""
        try:
            from storage import apply_table_view, clear_table_state

            snap = getattr(self, "_ext_snap", None)
            clear_table_state(self._config.app.workspace, "extensions")
            self.ext_table.enable_auto_fit()
            if isinstance(snap, dict):
                apply_table_view(self.ext_table.horizontalHeader(), snap)
            self._refresh_extensions()
        except Exception:
            pass

    def _load_from_config(self) -> None:
        self._loading = True
        try:
            self.preset_combo.setCurrentText(self._config.preset_label())
            self.url_edit.setText(self._config.dataverse.base_url)
            self.token_edit.setText(self._config.dataverse.api_token)
            collection = getattr(self._config.dataverse, "collection", "") or getattr(self._config.dataverse, "subtree", "")
            self.subtree_edit.setText(collection)
            self.workspace_edit.setText(str(self._config.app.workspace))
            self._tool_paths = {
                "tesseract": self._config.app.tesseract or "",
                "exiftool": self._config.app.exiftool or "",
            }
            self._on_preset_changed(self.preset_combo.currentText())
        finally:
            self._loading = False
        self._baseline = self._snapshot()
        self._dirty = False
        self._footer.set_dirty(False)
        self._footer.set_status("")

    def _snapshot(self) -> dict[str, str]:
        """Return the persisted values in the form `persist()` writes them."""
        return {
            "url": self.url_edit.text().strip().rstrip("/"),
            "token": self.token_edit.text().strip(),
            "collection": self.subtree_edit.text().strip(),
            "workspace": self.workspace_edit.text().strip(),
            "tesseract": (self._tool_paths or {}).get("tesseract", "").strip(),
            "exiftool": (self._tool_paths or {}).get("exiftool", "").strip(),
        }

    def _refresh_dirty(self) -> None:
        if self._loading:
            return
        self._dirty = self._snapshot() != self._baseline
        try:
            self._footer.set_dirty(self._dirty)
        except Exception:
            pass

    def has_unsaved_changes(self) -> bool:
        return bool(self._dirty)

    def confirm_leave(self, parent=None) -> bool:
        """Ask Save/Discard/Cancel when leaving with unsaved edits.

        Returns True when navigation may proceed (saved or discarded), False
        when the curator chose Cancel or a save failed.
        """
        if not self._dirty:
            return True
        action = confirm_save_discard_cancel(
            parent or self,
            "Unsaved settings",
            "You have unsaved settings changes. Save them before leaving?",
        )
        if action == "save":
            return self.persist()
        if action == "discard":
            self._load_from_config()
            return True
        return False

    def _on_revert(self) -> None:
        if not self._dirty:
            return
        if not confirm(
            self,
            "Revert settings",
            "Discard unsaved settings changes and reload the saved configuration?",
            confirm_label="Revert",
        ):
            return
        self._load_from_config()
        self._footer.set_status("Reverted to saved settings.")

    def _on_preset_changed(self, label: str) -> None:
        preset_url = PRESETS.get(label, "")
        if preset_url:
            self.url_edit.setText(preset_url)

    def _browse_workspace(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, t("settings.extensions.choose_workspace")
        )
        if chosen:
            self.workspace_edit.setText(chosen)

    # External binaries shown as table rows (not pip packages)
    TOOLS = [
        (
            "tesseract",
            t("settings.extensions.tool_tesseract"),
            t("settings.extensions.tool_tesseract_desc"),
        ),
        (
            "exiftool",
            t("settings.extensions.tool_exiftool"),
            t("settings.extensions.tool_exiftool_desc"),
        ),
    ]

    @staticmethod
    def _detect_tool(key: str, configured: str) -> str:
        """Resolve a binary path — configured path wins, else PATH lookup ('' if missing)."""
        import shutil

        candidates: list[str] = []
        if (configured or "").strip():
            candidates.append(configured.strip())
        candidates.append(key)
        if sys.platform.startswith("win"):
            candidates.append(f"{key}.exe")
        for candidate in candidates:
            try:
                if Path(candidate).is_file():
                    return str(Path(candidate))
                found = shutil.which(candidate)
                if found:
                    return found
            except Exception:
                continue
        return ""

    @staticmethod
    def _humanize_bytes(total: int) -> str:
        for unit in ("B", "KB", "MB", "GB"):
            if total < 1024 or unit == "GB":
                return f"{total:.1f} {unit}" if unit != "B" else f"{total} B"
            total /= 1024
        return f"{total:.1f} GB"

    @staticmethod
    def _package_size(pip_name: str, import_name: str = "") -> str:
        """Installed size of a distribution (humanized) or '—'.

        Fast path first: sum the dist RECORD via importlib.metadata (no
        import, no package __init__ side effects). Falls back to locating
        the top-level module with find_spec (still no import) and walking
        only that subtree. Never imports the target package — importing
        scipy/pandas just to stat files froze the Settings tab.
        """
        import_name = import_name or pip_name
        try:
            files = importlib.metadata.files(pip_name)
        except Exception:
            files = None
        if files:
            try:
                total = 0
                for f in files:
                    try:
                        loc = f.locate()
                    except Exception:
                        continue
                    try:
                        if loc.is_file():
                            total += loc.stat().st_size
                    except Exception:
                        continue
                if total:
                    return SettingsPane._humanize_bytes(total)
            except Exception:
                pass
        try:
            import importlib.util as _util
            import os as _os

            spec = _util.find_spec(import_name)
            roots: list[Path] = []
            if spec is not None:
                try:
                    locations = list(getattr(spec, "submodule_search_locations", None) or [])
                except Exception:
                    locations = []
                if locations:
                    roots.extend(Path(p) for p in locations)
                elif getattr(spec, "origin", None):
                    origin = Path(str(spec.origin))
                    roots.append(origin.parent if origin.name == "__init__.py" else origin)
            total = 0
            for root in roots:
                try:
                    if root.is_file():
                        total += root.stat().st_size
                    elif root.is_dir():
                        for dirpath, _dirnames, filenames in _os.walk(root):
                            for name in filenames:
                                try:
                                    total += (root.__class__(dirpath) / name).stat().st_size
                                except Exception:
                                    continue
                except Exception:
                    continue
            if total:
                return SettingsPane._humanize_bytes(total)
        except Exception:
            pass
        return "—"

    def _refresh_extensions(self) -> None:
        from ui.icons import icon as _ext_icon  # hoisted: also used in TOOLS rows below

        frozen = bool(getattr(sys, "frozen", False))
        # Hide the cells being replaced before repopulating: Qt only
        # deleteLater()s the old cell widgets, so without this they keep
        # painting at their stale geometry until the next event-loop turn —
        # ghost button copies over the Used-for column in any capture (or
        # one-frame flash) taken between the replacement and that turn.
        for _r in range(self.ext_table.rowCount()):
            _old = self.ext_table.cellWidget(_r, 4)
            if _old is not None:
                _old.hide()
        self.ext_table.setRowCount(len(self.EXTENSIONS))
        for row, (pip_name, import_name, desc) in enumerate(self.EXTENSIONS):
            self.ext_table.setItem(row, 0, QTableWidgetItem(pip_name))

            try:
                ver = importlib.metadata.version(pip_name if pip_name != "Pillow" else "Pillow")
                installed, is_installed = ver, True
            except importlib.metadata.PackageNotFoundError:
                try:
                    __import__(import_name)
                    installed, is_installed = (
                        t("settings.extensions.installed_lower"),
                        True,
                    )
                except ImportError:
                    installed, is_installed = (
                        t("settings.extensions.not_installed"),
                        False,
                    )
            except Exception:
                installed, is_installed = "?", False
            inst_item = QTableWidgetItem(installed)
            if not is_installed and installed != "?":
                inst_item.setForeground(QColor(ERROR))
            elif is_installed:
                inst_item.setForeground(QColor(PRIMARY))
            try:
                if not is_installed and installed != "?":
                    inst_item.setIcon(_ext_icon("x", color=ERROR))
                elif is_installed:
                    inst_item.setIcon(_ext_icon("check", color=PRIMARY))
                else:
                    inst_item.setIcon(_ext_icon("minus", color=ON_SECONDARY_CONTAINER))
            except Exception:
                pass
            self.ext_table.setItem(row, 1, inst_item)
            # Sizes come from the background _SizeWorker — never walk here
            # (importlib.metadata + os.walk on the GUI thread froze Settings).
            size_key = import_name or pip_name
            cached = self._size_cache.get(size_key, "…")
            self.ext_table.setItem(
                row, 2, QTableWidgetItem(cached if is_installed else "—")
            )
            self.ext_table.setItem(row, 3, QTableWidgetItem(desc))
            # Action cell: padded container so buttons never clip ("mangled" text fix)
            cell = QWidget()
            cell.setObjectName("ExtActionCell")
            cell.setStyleSheet("QWidget#ExtActionCell { background: transparent; border: none; }")
            cell_lay = QHBoxLayout(cell)
            cell_lay.setContentsMargins(6, 3, 6, 3)
            cell_lay.setSpacing(6)
            install_label = (
                t("settings.extensions.reinstall")
                if is_installed
                else t("settings.extensions.install")
            )
            install_btn = AppButton(
                install_label, kind="secondary", size="sm"
            )
            install_btn.setStyleSheet(_CELL_BTN_STYLE)
            install_btn.clicked.connect(lambda _checked, n=pip_name: self._install_package(n))
            uninstall_btn = AppButton(
                t("settings.extensions.uninstall"), kind="secondary", size="sm"
            )
            uninstall_btn.setStyleSheet(_CELL_BTN_STYLE)
            uninstall_btn.setEnabled(is_installed)
            uninstall_btn.clicked.connect(lambda _checked, n=pip_name: self._uninstall_package(n))
            if frozen:
                tip = t("settings.extensions.frozen_tip")
                install_btn.setEnabled(False)
                install_btn.setToolTip(tip)
                uninstall_btn.setEnabled(False)
                uninstall_btn.setToolTip(tip)
            cell_lay.addWidget(install_btn)
            cell_lay.addWidget(uninstall_btn)
            cell_lay.addStretch()
            self.ext_table.setCellWidget(row, 4, cell)
            self.ext_table.setRowHeight(row, 34)
        # External binaries as table rows (same columns, Browse… action)
        base_row = len(self.EXTENSIONS)
        self.ext_table.setRowCount(base_row + len(self.TOOLS))
        for offset, (key, label, desc) in enumerate(self.TOOLS):
            row = base_row + offset
            configured = (self._tool_paths or {}).get(key, "")
            resolved = self._detect_tool(key, configured)
            self.ext_table.setItem(row, 0, QTableWidgetItem(label))
            status_item = QTableWidgetItem(
                t("settings.extensions.installed_lower")
                if resolved
                else t("settings.extensions.not_installed")
            )
            status_item.setForeground(QColor(PRIMARY if resolved else ERROR))
            try:
                status_item.setIcon(
                    _ext_icon("check", color=PRIMARY) if resolved
                    else _ext_icon("x", color=ERROR)
                )
            except Exception:
                pass
            status_item.setToolTip(
                resolved
                or (
                    t("settings.extensions.configured", configured=configured)
                    if configured
                    else t("settings.extensions.add_path_tip")
                )
            )
            self.ext_table.setItem(row, 1, status_item)
            if resolved:
                try:
                    _size = Path(resolved).stat().st_size
                    tool_size = self._humanize_bytes(_size)
                except Exception:
                    tool_size = "—"
            else:
                tool_size = "—"
            self.ext_table.setItem(row, 2, QTableWidgetItem(tool_size))
            self.ext_table.setItem(row, 3, QTableWidgetItem(desc))
            tool_cell = QWidget()
            tool_cell.setObjectName("ToolActionCell")
            tool_cell.setStyleSheet("QWidget#ToolActionCell { background: transparent; border: none; }")
            tool_lay = QHBoxLayout(tool_cell)
            tool_lay.setContentsMargins(6, 3, 6, 3)
            tool_lay.setSpacing(6)
            browse_btn = AppButton(
                t("settings.extensions.locate_button"), kind="secondary", size="sm"
            )
            browse_btn.setStyleSheet(_CELL_BTN_STYLE)
            browse_btn.setToolTip(
                t("settings.extensions.locate_tip", label=label)
            )
            browse_btn.clicked.connect(lambda _checked, k=key: self._browse_tool(k))
            tool_lay.addWidget(browse_btn)
            tool_lay.addStretch()
            self.ext_table.setCellWidget(row, 4, tool_cell)
            self.ext_table.setRowHeight(row, 34)
        # Content-width columns (Used-for stays Stretch); no-op when a
        # saved view was restored or the user already resized.
        self.ext_table.fit_columns_to_content()

    def _browse_tool(self, key: str) -> None:
        from PySide6.QtWidgets import QFileDialog as _QFileDialog

        current = (self._tool_paths or {}).get(key, "")
        chosen, _ = _QFileDialog.getOpenFileName(
            self,
            t("settings.extensions.locate_title", key=key),
            current or str(Path.home()),
        )
        if chosen:
            if self._tool_paths is None:
                self._tool_paths = {}
            self._tool_paths[key] = chosen
            self._refresh_extensions()
            self._refresh_dirty()

    def _run_shell(self, func, status: str) -> None:
        """Run one blocking `func() -> (ok, title, message)` off the GUI thread."""
        if self._shell_worker is not None and self._shell_worker.isRunning():
            self.ext_status.setText(t("settings.extensions.busy"))
            return
        self.ext_status.setText(status)
        worker = _ShellWorker(func, self)
        self._shell_worker = worker
        worker.done.connect(self._on_shell_done)
        # Clear the ref only after the thread has fully finished — `done`
        # fires before termination, so clearing there let a second worker
        # start while the first was still winding down.
        worker.finished.connect(self._on_shell_finished)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _on_shell_finished(self) -> None:
        self._shell_worker = None

    def _on_shell_done(self, ok: bool, title: str, message: str) -> None:
        self.ext_status.setText(message.splitlines()[0] if message else "")
        try:
            self._test_btn.setEnabled(True)
        except Exception:
            pass
        if ok:
            show_info(self, title, message)
        else:
            show_critical(self, title, message)
        self._refresh_extensions()

    @staticmethod
    def _pip_run(args: list, pip_name: str, verb: str) -> tuple:
        result = subprocess.run(
            [sys.executable, "-m", "pip", *args],
            capture_output=True, text=True, timeout=600,
        )
        if result.returncode == 0:
            return (
                True,
                t("settings.extensions.dialog_title"),
                t(
                    "settings.extensions.pip_success",
                    package=pip_name,
                    verb=verb,
                ),
            )
        return (
            False,
            t("settings.extensions.dialog_title"),
            t(
                "settings.extensions.pip_failed",
                args=" ".join(args),
                stderr=result.stderr[:2000],
            ),
        )

    def _install_package(self, pip_name: str) -> None:
        # Run pip in a way that works in dev; frozen exe cannot pip install into bundle
        if getattr(sys, "frozen", False):
            show_warning(
                self,
                t("settings.extensions.dialog_title"),
                t("settings.extensions.install_frozen", package=pip_name),
            )
            self.ext_status.setText(
                t("settings.extensions.install_frozen_status")
            )
            return
        self._run_shell(
            lambda: self._pip_run(["install", pip_name], pip_name, "installed"),
            t("settings.extensions.installing_status", package=pip_name),
        )

    def _uninstall_package(self, pip_name: str) -> None:
        if getattr(sys, "frozen", False):
            show_warning(
                self,
                t("settings.extensions.dialog_title"),
                t("settings.extensions.uninstall_frozen", package=pip_name),
            )
            self.ext_status.setText(
                t("settings.extensions.uninstall_frozen_status")
            )
            return
        self._run_shell(
            lambda: self._pip_run(["uninstall", "-y", pip_name], pip_name, "uninstalled"),
            t("settings.extensions.uninstalling_status", package=pip_name),
        )

    def _install_all(self) -> None:
        missing = []
        for pip_name, import_name, _ in self.EXTENSIONS:
            try:
                importlib.metadata.version(pip_name if pip_name != "Pillow" else "Pillow")
            except Exception:
                try:
                    __import__(import_name)
                except ImportError:
                    missing.append(pip_name)
        if not missing:
            show_info(
                self,
                t("settings.extensions.dialog_title"),
                t("settings.extensions.all_installed"),
            )
            return
        if getattr(sys, "frozen", False):
            show_warning(
                self,
                t("settings.extensions.dialog_title"),
                t(
                    "settings.extensions.bulk_frozen",
                    packages=" ".join(missing),
                ),
            )
            return
        self._run_shell(
            lambda: self._pip_run(["install", *missing], ", ".join(missing), "installed"),
            t(
                "settings.extensions.installing_status",
                package=", ".join(missing),
            ),
        )

    @staticmethod
    def _make_user_value() -> QLabel:
        """Read-only identity field (selectable, muted until resolved).

        The unfetched state is a NAMED one ("Not checked yet", then
        "Checking…"/"No user returned"/"Not set" — 2026-10-02 P2), never
        a bare "—".
        """
        lbl = QLabel(t("settings.user.not_checked"))
        lbl.setWordWrap(True)
        lbl.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
        )
        lbl.setStyleSheet(f"font-size: 12px; color: {ON_SURFACE_VARIANT}; border: none; background: transparent;")
        return lbl

    def _clear_collection_role(self) -> None:
        """Blank only the collection-role row (alias edits stale it alone)."""
        try:
            if getattr(self, "_user_role", None) is not None:
                self._user_role.setText(t("settings.user.not_checked"))
        except Exception:
            pass

    def _set_collection_role(
        self, roles: list | None, alias: str = "", checked: bool = True
    ) -> None:
        """Render the caller's role(s) on the alias collection.

        roles None = could not determine (denied/network/empty alias);
        [] = no direct role assignment; otherwise the joined role names.
        checked=False = the identity pass never ran (no URL/token yet), so
        the row keeps its named unfetched state instead of implying a
        failed check.
        """
        try:
            if roles is None:
                if not checked:
                    self._user_role.setText(t("settings.user.not_checked"))
                    tip = t("settings.user.tip_enter_credentials")
                elif (alias or "").strip():
                    self._user_role.setText(t("settings.user.couldnt_check"))
                    tip = t("settings.user.tip_role_unknown")
                else:
                    self._user_role.setText(t("settings.user.not_checked"))
                    tip = t("settings.user.tip_enter_alias")
            elif not roles:
                self._user_role.setText(
                    t("settings.user.no_direct_role")
                    if (alias or "").strip()
                    else t("settings.user.not_checked")
                )
                tip = (
                    t("settings.user.tip_no_role_alias", alias=alias)
                    if (alias or "").strip()
                    else t("settings.user.tip_enter_alias")
                )
            else:
                self._user_role.setText(", ".join(str(r) for r in roles))
                tip = t(
                    "settings.user.tip_roles_alias",
                    alias=alias,
                    roles=", ".join(str(r) for r in roles),
                )
            self._user_role.setToolTip(tip)
        except Exception:
            pass

    def _clear_user_info(self) -> None:
        """Reset the identity rows (stale identity must not survive edits)."""
        try:
            for attr in (
                "_user_identifier", "_user_display", "_user_super", "_user_affil",
                "_user_role",
            ):
                lbl = getattr(self, attr, None)
                if lbl is not None:
                    lbl.setText(t("settings.user.not_checked"))
                    lbl.setStyleSheet(
                        f"font-size: 12px; color: {ON_SURFACE_VARIANT}; "
                        "border: none; background: transparent;"
                    )
            if getattr(self, "_user_status", None) is not None:
                self._user_status.setText("")
        except Exception:
            pass

    def _set_user_info(self, me: dict | None, status: str = "", checked: bool = False) -> None:
        """Render a /api/users/:me profile into the identity rows.

        checked=False (never queried: no URL/token yet) reads "Not checked
        yet"; checked=True with no payload reads "No user returned"; a
        loaded profile with an absent field reads "Not set" — each state is
        named, never a bare "—" (2026-10-02 P2).
        """
        try:
            ok = isinstance(me, dict) and bool(me)
            if not ok:
                empty = (
                    t("settings.user.no_user_returned")
                    if checked
                    else t("settings.user.not_checked")
                )
                self._user_identifier.setText(empty)
                self._user_display.setText(empty)
                self._user_super.setText(empty)
                self._user_super.setStyleSheet(
                    "font-size: 12px; "
                    f"color: {ON_SURFACE_VARIANT}; border: none; background: transparent;"
                )
                self._user_affil.setText(empty)
                self._user_status.setText(status)
                return
            self._user_identifier.setText(
                str(me.get("identifier") or t("settings.user.not_set"))
            )
            display = str(
                me.get("displayName")
                or " ".join(
                    p for p in (
                        str(me.get("firstName") or "").strip(),
                        str(me.get("lastName") or "").strip(),
                    )
                    if p
                )
                or t("settings.user.not_set")
            )
            self._user_display.setText(display)
            is_super = bool(me.get("superuser"))
            self._user_super.setText(
                t("settings.user.yes") if is_super else t("settings.user.no")
            )
            self._user_super.setStyleSheet(
                "font-size: 12px; font-weight: 600; "
                f"color: {SUCCESS_DARK if is_super else ON_SECONDARY_CONTAINER}; "
                "border: none; background: transparent;"
            )
            self._user_affil.setText(
                str(me.get("affiliation") or t("settings.user.not_set"))
            )
            self._user_status.setText(status)
        except Exception:
            pass

    def _set_user_rows(self, text: str) -> None:
        """Put every identity row in the same named state (in-flight check)."""
        for attr in ("_user_identifier", "_user_display", "_user_super", "_user_affil", "_user_role"):
            lbl = getattr(self, attr, None)
            if lbl is not None:
                lbl.setText(text)

    def _refresh_user_info(self) -> None:
        """Fetch identity + alias-collection role off the GUI thread."""
        try:
            base = self.url_edit.text().strip().rstrip("/")
            token = self.token_edit.text().strip()
            alias = self.subtree_edit.text().strip()
        except Exception:
            return
        if not base or not token:
            # Nothing was queried: every row keeps its named unfetched state.
            self._set_user_info(
                None, t("settings.user.tip_enter_credentials")
            )
            self._set_collection_role(None, alias, checked=False)
            return
        if self._shell_worker is not None and self._shell_worker.isRunning():
            return  # a test/extension task is running; refreshes on next open
        self._user_status.setText(t("settings.user.checking_identity"))
        self._set_user_rows(t("settings.user.checking"))

        def _fetch() -> tuple:
            import json as _json

            try:
                client = DataverseClient(base, token)
                me = client.get_me()
            except Exception:
                me = None
            try:
                roles = client.get_collection_roles(alias) if alias else None
            except Exception:
                roles = None
            return True, t("settings.user.identity_title"), _json.dumps({"me": me or {}, "roles": roles})

        worker = _ShellWorker(_fetch, self)
        self._shell_worker = worker
        worker.done.connect(self._on_identity_done)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _on_identity_done(self, ok: bool, title: str, message: str) -> None:
        self._shell_worker = None
        try:
            import json as _json

            payload = _json.loads(message or "{}")
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        me = payload.get("me") if isinstance(payload.get("me"), dict) else {}
        roles = payload.get("roles")
        try:
            alias = self.subtree_edit.text().strip()
        except Exception:
            alias = ""
        if me:
            self._set_user_info(me, "")
        else:
            self._set_user_info(
                None,
                t("settings.user.verify_failed"),
                checked=True,
            )
        self._set_collection_role(
            list(roles) if isinstance(roles, list) else None, alias
        )

    def _set_conn_status(self, ok: bool | None, text: str, tip: str = "") -> None:
        """Inline connection verdict next to the Test connection button.

        ok True/False colors the text green/red; None is the neutral
        in-progress tone. No dialog — the result lives where the test ran.
        """
        try:
            color = SUCCESS_DARK if ok is True else (ERROR if ok is False else ON_SECONDARY_CONTAINER)
            self._conn_status.setStyleSheet(
                f"font-size: 12px; color: {color}; border: none; background: transparent;"
            )
            self._conn_status.setText(text)
            self._conn_status.setToolTip(tip or text)
        except Exception:
            pass

    def _test_connection(self) -> None:
        base = self.url_edit.text().strip().rstrip("/")
        if not base:
            self._set_conn_status(False, t("settings.connection.enter_url"))
            return

        def _probe() -> tuple:
            try:
                r = requests.get(f"{base}/api/info/version", timeout=12)
                r.raise_for_status()
                ver = r.json().get("data", {}).get("version", "?")
            except Exception as exc:
                return (
                    False,
                    t("settings.connection.test_title"),
                    t(
                        "settings.connection.failed_to_reach",
                        base=base,
                        exc=exc,
                    ),
                )
            return (
                True,
                t("settings.connection.test_title"),
                t(
                    "settings.connection.connected_to",
                    base=base,
                    version=ver,
                ),
            )

        try:
            self._test_btn.setEnabled(False)
        except Exception:
            pass
        self._set_conn_status(
            None, t("settings.connection.contacting", base=base)
        )
        if self._shell_worker is not None and self._shell_worker.isRunning():
            self._set_conn_status(None, t("settings.extensions.busy"))
            try:
                self._test_btn.setEnabled(True)
            except Exception:
                pass
            return
        worker = _ShellWorker(_probe, self)
        self._shell_worker = worker
        worker.done.connect(self._on_conn_done)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _on_conn_done(self, ok: bool, title: str, message: str) -> None:
        self._shell_worker = None
        try:
            self._test_btn.setEnabled(True)
        except Exception:
            pass
        # Inline verdict (no dialog): first line in the label, full text in tooltip.
        first = (message.splitlines()[0] if message else "").strip()
        self._set_conn_status(
            bool(ok),
            first
            or (
                t("settings.connection.connected")
                if ok
                else t("settings.connection.failed")
            ),
            message,
        )
        if ok:
            # A good connection means the token is worth identifying.
            self._refresh_user_info()

    def persist(self) -> bool:
        """Validate and write config.json; no navigation, no `saved` signal."""
        base = self.url_edit.text().strip().rstrip("/")
        if not base.startswith("http"):
            show_warning(
                self,
                t("settings.title"),
                t("settings.save.base_url_error"),
            )
            return False
        ws = Path(self.workspace_edit.text().strip() or str(Path.home() / "Documents" / "curation-workspace"))
        self._config.dataverse.base_url = base
        self._config.dataverse.api_token = self.token_edit.text().strip()
        collection = self.subtree_edit.text().strip()
        self._config.dataverse.collection = collection
        # keep subtree alias in sync for compat
        try:
            self._config.dataverse.subtree = collection
        except Exception:
            pass
        self._config.app.workspace = ws
        self._config.app.tesseract = (self._tool_paths or {}).get("tesseract", "").strip()
        self._config.app.exiftool = (self._tool_paths or {}).get("exiftool", "").strip()
        try:
            self._config.save()
        except Exception as exc:
            show_critical(
                self,
                t("settings.title"),
                t("settings.save.failed", exc=exc),
            )
            return False
        self._baseline = self._snapshot()
        self._dirty = False
        self._footer.set_dirty(False)
        self._footer.set_status(t("settings.save.saved_to"))
        self.configurationChanged.emit()
        return True

    def _on_save(self) -> None:
        if self.persist():
            self.saved.emit()
