"""Settings pane: Dataverse chooser, credentials, workspace and tools.

The curator picks which Dataverse to work against (preset for the Borealis
demo at demo.borealisdata.ca plus a Custom entry for any other instance),
enters an API token/collection alias, and chooses a local workspace.
Persists to config.json via config.Config.

Presented as a non-modal stack page (not a blocking dialog): Save persists
and emits `saved`. Closed via the Settings nav toggle (no Close button by
design); `discarded` is kept for compat but no longer emitted by this pane.
"""

from pathlib import Path

import importlib.metadata
import subprocess
import sys

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ui.dialogs import show_critical, show_info, show_warning
from ui.theme import ERROR, PRIMARY, action_button_style, enable_table_copy, selectable_labels
from ui.widgets import AppButton, AppTable, make_combo, make_line_edit

from config import PRESETS, Config


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


class SettingsPane(QWidget):
    """Edits dataverse.base_url/api_token/subtree, app.workspace and
    optional tool paths. Persists to config.json on Save."""

    saved = Signal()
    discarded = Signal()

    # Optional curation dependencies that are lazy-loaded; lite build excludes them
    EXTENSIONS = [
        ("pyreadstat", "pyreadstat", "SPSS/Stata/SAS checks (sav, dta, sas7bdat)"),
        ("netCDF4", "netCDF4", "NetCDF scientific data"),
        ("h5py", "h5py", "HDF5 data"),
        ("tifffile", "tifffile", "TIFF images"),
        ("Pillow", "PIL", "Raster images (png/jpg)"),
        ("pypdf", "pypdf", "PDF checks"),
        ("lxml", "lxml", "XML validation"),
        ("openpyxl", "openpyxl", "Excel workbooks"),
        ("scipy", "scipy", "MATLAB .mat"),
        ("chardet", "chardet", "Text encoding detection"),
        ("pandas", "pandas", "Tabular helpers"),
    ]

    def __init__(self, config: Config, parent=None) -> None:
        super().__init__(parent)
        self._config = config
        self.setStyleSheet("background: #faf8ff;")

        outer = QVBoxLayout()
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(16)

        heading = QLabel("Settings")
        heading.setStyleSheet("font-size: 22px; font-weight: 600; color: #131b2e; border: none; background: transparent;")
        outer.addWidget(heading)
        sub = QLabel("Dataverse connection, workspace, and optional curation libraries.")
        sub.setStyleSheet("font-size: 13px; color: #57657a; border: none; background: transparent;")
        sub.setWordWrap(True)
        outer.addWidget(sub)

        from PySide6.QtWidgets import QTabWidget

        tabs = QTabWidget()

        # General tab
        general = QWidget()
        form = QFormLayout(general)

        self.preset_combo = make_combo(list(PRESETS), min_width=200)
        form.addRow("Dataverse preset", self.preset_combo)

        self.url_edit = make_line_edit("https://demo.borealisdata.ca")
        form.addRow("Base URL", self.url_edit)

        self.token_edit = make_line_edit("API token (leave blank for public-only)", password=True)
        form.addRow("API token", self.token_edit)

        self.subtree_edit = make_line_edit("collection alias, e.g. dv (empty = whole repository)")
        form.addRow("Collection / collection alias", self.subtree_edit)

        ws_row = QHBoxLayout()
        self.workspace_edit = make_line_edit()
        browse_btn = AppButton("Browse…", kind="secondary", size="sm")
        browse_btn.setStyleSheet(action_button_style(False))
        browse_btn.clicked.connect(self._browse_workspace)
        ws_row.addWidget(self.workspace_edit, 1)
        ws_row.addWidget(browse_btn)
        form.addRow("Workspace", ws_row)

        test_btn = AppButton("Test connection", kind="secondary", size="sm")
        test_btn.setStyleSheet(action_button_style(False))
        test_btn.clicked.connect(self._test_connection)
        self._test_btn = test_btn
        form.addRow(test_btn)

        tabs.addTab(general, "General")

        # Extensions tab: optional libs + external binaries
        ext_tab = QWidget()
        ext_layout = QVBoxLayout(ext_tab)
        self.ext_table = AppTable(
            ["Package", "Installed", "Size", "Used for", "Action"],
            widths={0: 110, 1: 130, 2: 90, 3: 200, 4: 240},
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
        ext_layout.addWidget(self.ext_table, 1)
        ext_hint = QLabel("External binaries (Tesseract for OCR, ExifTool for deep metadata) live in the table below — use Browse… to point at them.")
        ext_hint.setWordWrap(True)
        ext_layout.addWidget(ext_hint)
        ext_btn_row = QHBoxLayout()
        self.ext_status = QLabel("")
        ext_btn_row.addWidget(self.ext_status, 1)
        refresh_ext_btn = AppButton("Refresh", kind="secondary", size="sm")
        refresh_ext_btn.setStyleSheet(action_button_style(False))
        refresh_ext_btn.setToolTip("Re-check installed versions and re-measure sizes")
        refresh_ext_btn.clicked.connect(self._refresh_sizes)
        ext_btn_row.addWidget(refresh_ext_btn)
        install_all_btn = AppButton("Install all missing", kind="secondary", size="sm")
        install_all_btn.setStyleSheet(action_button_style(False))
        install_all_btn.clicked.connect(self._install_all)
        ext_btn_row.addWidget(install_all_btn)
        ext_layout.addLayout(ext_btn_row)
        tabs.addTab(ext_tab, "Extensions")
        outer.addWidget(tabs, 1)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        # No Close button by design — the Settings nav button toggles this
        # pane open/closed, so a second close affordance is redundant.
        buttons.addStretch(1)
        save_btn = AppButton("Save", kind="primary")
        save_btn.setMinimumWidth(140)
        save_btn.setToolTip("Save to config.json (Ctrl+S)")
        save_btn.clicked.connect(self._on_save)
        buttons.addWidget(save_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(outer)
        layout.addLayout(buttons)

        try:
            from PySide6.QtGui import QKeySequence as _QKS, QShortcut as _QSC

            _QSC(_QKS("Ctrl+S", _QKS.PortableText), self, self._on_save)  # type: ignore[arg-type]
        except Exception:
            pass

        self.preset_combo.currentTextChanged.connect(self._on_preset_changed)
        self._tool_paths: dict = {}
        self._shell_worker: _ShellWorker | None = None
        # Package-size cache: os.walk per package is seconds-slow, so sizes
        # are computed once per pane lifetime; Refresh re-walks on demand.
        self._size_cache: dict[str, str] = {}
        self.reload()
        try:
            selectable_labels(self)
            enable_table_copy(self.ext_table)
        except Exception:
            pass

    def reload(self) -> None:
        """Re-read config + extension state (called each time the pane opens)."""
        self._load_from_config()
        self._refresh_extensions()

    def _refresh_sizes(self) -> None:
        """Clear the size cache and re-walk installed packages on demand."""
        self._size_cache = {}
        self._refresh_extensions()

    def _load_from_config(self) -> None:
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

    def _on_preset_changed(self, label: str) -> None:
        preset_url = PRESETS.get(label, "")
        if preset_url:
            self.url_edit.setText(preset_url)

    def _browse_workspace(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Choose workspace folder")
        if chosen:
            self.workspace_edit.setText(chosen)

    # External binaries shown as table rows (not pip packages)
    TOOLS = [
        ("tesseract", "Tesseract", "OCR text extraction (scanned PDFs)"),
        ("exiftool", "ExifTool", "Deep file metadata"),
    ]

    @staticmethod
    def _detect_tool(key: str, configured: str) -> str:
        """Resolved binary path or '' — configured path wins, else PATH lookup."""
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
        frozen = bool(getattr(sys, "frozen", False))
        self.ext_table.setRowCount(len(self.EXTENSIONS))
        for row, (pip_name, import_name, desc) in enumerate(self.EXTENSIONS):
            self.ext_table.setItem(row, 0, QTableWidgetItem(pip_name))
            try:
                ver = importlib.metadata.version(pip_name if pip_name != "Pillow" else "Pillow")
                installed = f"✓ {ver}"
            except importlib.metadata.PackageNotFoundError:
                try:
                    __import__(import_name)
                    installed = "✓ installed"
                except ImportError:
                    installed = "✗ Not installed"
            except Exception:
                installed = "?"
            is_installed = installed.startswith("✓")
            inst_item = QTableWidgetItem(installed)
            if installed.startswith("✗"):
                inst_item.setForeground(QColor(ERROR))
            elif is_installed:
                inst_item.setForeground(QColor(PRIMARY))
            self.ext_table.setItem(row, 1, inst_item)
            if is_installed and import_name not in self._size_cache:
                self._size_cache[import_name] = self._package_size(pip_name, import_name)
            self.ext_table.setItem(
                row, 2, QTableWidgetItem(self._size_cache.get(import_name, "—") if is_installed else "—")
            )
            self.ext_table.setItem(row, 3, QTableWidgetItem(desc))
            # Action cell: padded container so buttons never clip ("mangled" text fix)
            cell = QWidget()
            cell.setStyleSheet("background: transparent; border: none;")
            cell_lay = QHBoxLayout(cell)
            cell_lay.setContentsMargins(6, 3, 6, 3)
            cell_lay.setSpacing(6)
            install_btn = AppButton("Reinstall" if is_installed else "Install", kind="secondary", size="sm")
            install_btn.setStyleSheet(action_button_style(False))
            install_btn.clicked.connect(lambda _checked, n=pip_name: self._install_package(n))
            uninstall_btn = AppButton("Uninstall", kind="secondary", size="sm")
            uninstall_btn.setStyleSheet(action_button_style(False))
            uninstall_btn.setEnabled(is_installed)
            uninstall_btn.clicked.connect(lambda _checked, n=pip_name: self._uninstall_package(n))
            if frozen:
                tip = "Not available in frozen portable — use full build or run from source with pip"
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
            status = "✓ installed" if resolved else "✗ Not installed"
            status_item = QTableWidgetItem(status)
            status_item.setForeground(QColor(PRIMARY if resolved else ERROR))
            status_item.setToolTip(
                resolved
                or (f"Configured: {configured}" if configured else "Add the binary path via Browse… or leave empty to use PATH")
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
            tool_cell.setStyleSheet("background: transparent; border: none;")
            tool_lay = QHBoxLayout(tool_cell)
            tool_lay.setContentsMargins(6, 3, 6, 3)
            tool_lay.setSpacing(6)
            browse_btn = AppButton("Browse…", kind="secondary", size="sm")
            browse_btn.setStyleSheet(action_button_style(False))
            browse_btn.setToolTip(f"Locate the {label} executable")
            browse_btn.clicked.connect(lambda _checked, k=key: self._browse_tool(k))
            tool_lay.addWidget(browse_btn)
            tool_lay.addStretch()
            self.ext_table.setCellWidget(row, 4, tool_cell)
            self.ext_table.setRowHeight(row, 34)

    def _browse_tool(self, key: str) -> None:
        from PySide6.QtWidgets import QFileDialog as _QFileDialog

        current = (self._tool_paths or {}).get(key, "")
        chosen, _ = _QFileDialog.getOpenFileName(
            self, f"Locate {key} executable", current or str(Path.home())
        )
        if chosen:
            if self._tool_paths is None:
                self._tool_paths = {}
            self._tool_paths[key] = chosen
            self._refresh_extensions()

    def _run_shell(self, func, status: str) -> None:
        """Run one blocking `func() -> (ok, title, message)` off the GUI thread."""
        if self._shell_worker is not None and self._shell_worker.isRunning():
            self.ext_status.setText("Another task is already running — please wait…")
            return
        self.ext_status.setText(status)
        worker = _ShellWorker(func, self)
        self._shell_worker = worker
        worker.done.connect(self._on_shell_done)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _on_shell_done(self, ok: bool, title: str, message: str) -> None:
        self._shell_worker = None
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
            return True, "Extensions", f"{pip_name} {verb} successfully."
        return False, "Extensions", f"pip {' '.join(args)} failed:\n{result.stderr[:2000]}"

    def _install_package(self, pip_name: str) -> None:
        # Run pip in a way that works in dev; frozen exe cannot pip install into bundle
        if getattr(sys, "frozen", False):
            show_warning(self, "Extensions", "Pip install is not available in the frozen portable. Use the full build or run from source:\n  pip install " + pip_name)
            self.ext_status.setText("Install not available in frozen build.")
            return
        self._run_shell(
            lambda: self._pip_run(["install", pip_name], pip_name, "installed"),
            f"Installing {pip_name}… (UI stays responsive)",
        )

    def _uninstall_package(self, pip_name: str) -> None:
        if getattr(sys, "frozen", False):
            show_warning(self, "Extensions", "Pip uninstall is not available in the frozen portable. Manage packages from source:\n  pip uninstall " + pip_name)
            self.ext_status.setText("Uninstall not available in frozen build.")
            return
        self._run_shell(
            lambda: self._pip_run(["uninstall", "-y", pip_name], pip_name, "uninstalled"),
            f"Uninstalling {pip_name}… (UI stays responsive)",
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
            show_info(self, "Extensions", "All optional packages are already installed.")
            return
        if getattr(sys, "frozen", False):
            show_warning(self, "Extensions", "Bulk install not available in frozen portable. Install from source:\n  pip install " + " ".join(missing))
            return
        self._run_shell(
            lambda: self._pip_run(["install", *missing], ", ".join(missing), "installed"),
            f"Installing {', '.join(missing)}… (UI stays responsive)",
        )

    def _test_connection(self) -> None:
        base = self.url_edit.text().strip().rstrip("/")
        if not base:
            show_warning(self, "Test connection", "Enter a base URL first.")
            return

        def _probe() -> tuple:
            import requests

            try:
                r = requests.get(f"{base}/api/info/version", timeout=12)
                r.raise_for_status()
                ver = r.json().get("data", {}).get("version", "?")
            except Exception as exc:
                return False, "Test connection", f"Failed to reach {base}:\n{exc}"
            return True, "Test connection", f"Connected to {base}\nDataverse {ver}"

        try:
            self._test_btn.setEnabled(False)
        except Exception:
            pass
        self.ext_status.setText(f"Contacting {base}…")
        if self._shell_worker is not None and self._shell_worker.isRunning():
            self.ext_status.setText("Another task is already running — please wait…")
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
        self.ext_status.setText(message.splitlines()[0] if message else "")
        if ok:
            show_info(self, title, message)
        else:
            show_critical(self, title, message)

    def _on_save(self) -> None:
        base = self.url_edit.text().strip().rstrip("/")
        if not base.startswith("http"):
            show_warning(self, "Settings", "Base URL must start with http:// or https://")
            return
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
            show_critical(self, "Settings", f"Could not save config.json:\n{exc}")
            return
        self.saved.emit()
