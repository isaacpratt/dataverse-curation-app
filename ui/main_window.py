"""Main window: TopNav + stacked Dashboard / Dataset detail.

TopNav holds all navigation (File/Tools menu items moved here; no separate
menu bar): Dashboard, Back, Settings, Requirements, Log. Open datasets show
as full-title chips (never truncated to DOI). The status bar's repository
badge always shows the chosen Dataverse (base URL + collection alias).
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)

from ui.dialogs import show_warning

from config import Config
from ui.about_pane import AboutPane
from ui.dashboard import DashboardView
from ui.dataset_detail import DatasetDetailView
from ui.log_panel import LogPanel
from ui.settings_dialog import SettingsPane
from ui.widgets import AppButton
from ui.widgets import AppButton


class MainWindow(QMainWindow):
    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config
        self._metadata_cache: dict[str, tuple[dict, list]] = {}
        self._open_pids: list[tuple[str, str]] = []
        self.setWindowTitle("Dataverse Curation App")
        self.resize(1320, 860)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- TopNav: all navigation lives here (no menu bar) ----
        self._topnav = QFrame()
        self._topnav.setObjectName("TopNav")
        self._topnav.setFixedHeight(64)
        nav_lay = QHBoxLayout(self._topnav)
        nav_lay.setContentsMargins(20, 0, 20, 0)
        nav_lay.setSpacing(8)

        self._nav_dashboard = AppButton("Dashboard", kind="nav-active", size=None)
        self._nav_dashboard.setCursor(Qt.PointingHandCursor)
        self._nav_dashboard.setToolTip("Back to the dashboard (Alt+Left)")
        self._nav_dashboard.clicked.connect(self._show_dashboard)
        nav_lay.addWidget(self._nav_dashboard)

        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("color: #c3c6d8;")
        sep.setFixedWidth(1)
        nav_lay.addWidget(sep)

        # Open dataset chips — full titles, never DOI-truncated
        self._chips_wrap = QWidget()
        self._chips_wrap.setStyleSheet("background: transparent; border: none;")
        self._chips_wrap.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._chips_lay = QHBoxLayout(self._chips_wrap)
        self._chips_lay.setContentsMargins(4, 0, 16, 0)
        self._chips_lay.setSpacing(8)
        nav_lay.addWidget(self._chips_wrap, 1)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.VLine)
        sep2.setStyleSheet("color: #c3c6d8;")
        sep2.setFixedWidth(1)
        nav_lay.addWidget(sep2)

        # Former File/Tools menu items, now nav buttons.
        # Settings / Log / About toggle drop-down panes under the nav bar.
        self._nav_settings = AppButton("Settings", kind="nav", size=None)
        self._nav_settings.setCheckable(True)
        self._nav_settings.setCursor(Qt.PointingHandCursor)
        self._nav_settings.setToolTip("Dataverse, API token, workspace (Ctrl+,)")
        self._nav_settings.toggled.connect(self._on_settings_toggled)
        nav_lay.addWidget(self._nav_settings)

        self._nav_requirements = AppButton("Requirements", kind="nav", size=None)
        self._nav_requirements.setCursor(Qt.PointingHandCursor)
        self._nav_requirements.setToolTip("Edit metadata requirement profiles")
        self._nav_requirements.clicked.connect(self._edit_requirements)
        nav_lay.addWidget(self._nav_requirements)

        self._nav_log = AppButton("Log", kind="nav", size=None)
        self._nav_log.setCheckable(True)
        self._nav_log.setCursor(Qt.PointingHandCursor)
        self._nav_log.setToolTip("Show/hide curation log (Ctrl+L)")
        self._nav_log.toggled.connect(self._on_log_toggled)
        nav_lay.addWidget(self._nav_log)

        self._nav_help = AppButton("?", kind="nav", size=None)
        self._nav_help.setCheckable(True)
        self._nav_help.setFixedWidth(36)
        self._nav_help.setCursor(Qt.PointingHandCursor)
        self._nav_help.setToolTip("About this app")
        self._nav_help.toggled.connect(self._on_about_toggled)
        nav_lay.addWidget(self._nav_help)

        root.addWidget(self._topnav)

        # Drop-down panes directly under the nav bar (mutually exclusive).
        # Only one shows at a time; the stack underneath stays put.
        self._log_panel = LogPanel(self)
        self._log_panel.hide()
        self._log_panel.closed.connect(lambda: self._show_pane(None))
        root.addWidget(self._log_panel)

        self._stack = QStackedWidget()
        root.addWidget(self._stack, 1)

        # Hide the native menu bar — everything is in TopNav now
        try:
            self.menuBar().setVisible(False)
        except Exception:
            pass

        # Keyboard shortcuts previously on menu actions
        try:
            QShortcut(QKeySequence("Ctrl+,", QKeySequence.PortableText), self, self._open_settings)  # type: ignore[arg-type]
            QShortcut(QKeySequence("Ctrl+L", QKeySequence.PortableText), self, self._show_log)  # type: ignore[arg-type]
            QShortcut(QKeySequence("Alt+Left", QKeySequence.PortableText), self, self._show_dashboard)  # type: ignore[arg-type]
        except Exception:
            pass

        # Hide the native menu bar — everything is in TopNav now
        self._status_label = QLabel()
        self.statusBar().addWidget(self._status_label, 1)
        self._refresh_status_label()

        self._dashboard = DashboardView(config)
        self._dashboard.openRequested.connect(self._open_dataset)
        self._stack.addWidget(self._dashboard)
        self._settings = SettingsPane(config)
        self._settings.saved.connect(self._on_settings_saved)
        self._settings.discarded.connect(lambda: self._show_pane(None))
        self._settings.hide()
        root.insertWidget(2, self._settings)
        self._about = AboutPane(self)
        self._about.discarded.connect(lambda: self._show_pane(None))
        self._about.hide()
        root.insertWidget(3, self._about)
        self._detail: DatasetDetailView | None = None

        if not self._config.dataverse.base_url:
            self._open_settings()

    # -- status / repo badge -------------------------------------------

    def _refresh_status_label(self) -> None:
        alias = (
            getattr(self._config.dataverse, "collection", "")
            or getattr(self._config.dataverse, "subtree", "")
            or ""
        ).strip() or "whole repository"
        base = (self._config.dataverse.base_url or "").rstrip("/")
        self._status_label.setText(f"  {base}  ·  {alias}  ")
        self._status_label.setToolTip(f"Active Dataverse: {base}\nCollection: {alias}")
        try:
            self.statusBar().showMessage(f"Dataverse: {base}", 4000)
        except Exception:
            pass

    # -- slots ----------------------------------------------------------

    def _show_pane(self, name) -> None:
        """Show one drop-down pane (log/settings/about) exclusively."""
        panes = {
            "log": self._log_panel,
            "settings": self._settings,
            "about": self._about,
        }
        for key, pane in panes.items():
            try:
                visible = key == name
                if pane.isVisible() != visible:
                    pane.setVisible(visible)
            except Exception:
                pass
        for btn, key in (
            (self._nav_log, "log"),
            (self._nav_settings, "settings"),
            (self._nav_help, "about"),
        ):
            try:
                btn.blockSignals(True)
                btn.setChecked(key == name)
            except Exception:
                pass
            finally:
                try:
                    btn.blockSignals(False)
                except Exception:
                    pass

    def _on_log_toggled(self, checked: bool) -> None:
        self._show_pane("log" if checked else None)

    def _on_settings_toggled(self, checked: bool) -> None:
        if checked:
            try:
                self._settings.reload()
            except Exception:
                pass
        self._show_pane("settings" if checked else None)

    def _on_about_toggled(self, checked: bool) -> None:
        self._show_pane("about" if checked else None)

    def _show_about(self) -> None:
        self._show_pane("about")

    def _open_settings(self) -> None:
        try:
            self._settings.reload()
        except Exception:
            pass
        self._show_pane("settings")

    def _on_settings_saved(self) -> None:
        self._show_pane(None)
        self._refresh_status_label()
        try:
            self._dashboard.reload()
        except Exception as exc:
            show_warning(self, "Dashboard", f"Could not refresh dashboard:\n{exc}")

    def _open_dataset(self, persistent_id: str, title: str) -> None:
        if self._detail is not None:
            # Adopt still-running workers so destroying the view cannot kill
            # a live QThread ("Destroyed while thread is still running").
            # Their slots belong to the dying view, so late signals are
            # dropped safely; deleteLater reaps them on completion.
            self._adopt_running_workers(self._detail)
            self._stack.removeWidget(self._detail)
            self._detail.deleteLater()
            self._detail = None
        # Update title if we already track this pid (metadata may have loaded)
        found = False
        for i, (pid, _t) in enumerate(self._open_pids):
            if pid == persistent_id:
                self._open_pids[i] = (persistent_id, title or _t or persistent_id)
                found = True
                break
        if not found:
            self._open_pids.append((persistent_id, title or persistent_id))
            if len(self._open_pids) > 6:
                self._open_pids = self._open_pids[-6:]
        cached = self._metadata_cache.get(persistent_id)
        cached_meta, cached_inv = (cached if cached else (None, None))
        self._detail = DatasetDetailView(
            self._config, persistent_id, title, cached_metadata=cached_meta, cached_inventory=cached_inv
        )
        self._detail.backRequested.connect(self._show_dashboard)
        self._detail.metadataLoaded.connect(self._cache_metadata)
        self._detail.titleChanged.connect(self._on_detail_title)
        self._stack.addWidget(self._detail)
        self._stack.setCurrentWidget(self._detail)
        # Rebuild chips AFTER _detail is set so the active one highlights
        self._rebuild_chips()
        self._style_nav_for_detail(True)

    def _on_detail_title(self, pid: str, title: str) -> None:
        for i, (p, _t) in enumerate(self._open_pids):
            if p == pid and title and title != _t:
                self._open_pids[i] = (p, title)
        self._rebuild_chips()

    def _rebuild_chips(self) -> None:
        while self._chips_lay.count():
            item = self._chips_lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        if not self._open_pids:
            hint = QLabel("No dataset open")
            hint.setStyleSheet(
                "font-size: 11px; color: #57657a; background: transparent; border: none;"
            )
            self._chips_lay.addWidget(hint)
            self._chips_lay.addStretch()
            return
        # No dataset chip reads active while the dashboard is showing — the
        # Dashboard tab owns the highlight there.
        if self._stack.currentWidget() is self._dashboard:
            active_pid = None
        elif self._detail is not None:
            active_pid = getattr(self._detail, "_pid", None)
        else:
            active_pid = None
        for pid, title in self._open_pids:
            # FULL title, never DOI-truncated; tooltip carries the persistent ID.
            # Each chip has an × button to close that dataset.
            label = (title or pid).strip() or pid
            chip = QFrame()
            chip.setStyleSheet("QFrame { background: transparent; border: none; }")
            lay = QHBoxLayout(chip)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(0)
            is_active = active_pid is not None and pid == active_pid
            # NOTE: split-chip one-off (see ui/widgets.py) — not AppButton by design.
            open_btn = QPushButton(label)
            open_btn.setCursor(Qt.PointingHandCursor)
            open_btn.setToolTip(f"{label}\n{pid}\nClick to open")
            open_btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            open_btn.setFixedHeight(28)
            open_btn.setMaximumWidth(280)
            open_btn.setMinimumWidth(80)
            open_btn.setStyleSheet(
                "QPushButton { background: #eaedff; color: #131b2e; border: 1px solid #004ccd; "
                "border-top-left-radius: 8px; border-bottom-left-radius: 8px; "
                "padding: 0 4px 0 10px; font-size: 11px; font-weight: 700; text-align: left; }"
                if is_active else
                "QPushButton { background: #ffffff; color: #131b2e; border: 1px solid #c3c6d8; "
                "border-top-left-radius: 8px; border-bottom-left-radius: 8px; "
                "padding: 0 4px 0 10px; font-size: 11px; font-weight: 600; text-align: left; }"
                "QPushButton:hover { border: 1px solid #004ccd; }"
            )
            open_btn.clicked.connect(lambda _c, p=pid, t=title: self._open_dataset(p, t))
            lay.addWidget(open_btn)
            close_btn = QPushButton("×")
            close_btn.setCursor(Qt.PointingHandCursor)
            close_btn.setToolTip(f"Close {label}")
            close_btn.setFixedSize(28, 28)
            close_btn.setStyleSheet(
                "QPushButton { background: #eaedff; color: #131b2e; border: 1px solid #004ccd; "
                "border-left: none; border-top-right-radius: 8px; border-bottom-right-radius: 8px; "
                "font-size: 13px; font-weight: 700; }"
                if is_active else
                "QPushButton { background: #ffffff; color: #57657a; border: 1px solid #c3c6d8; "
                "border-left: none; border-top-right-radius: 8px; border-bottom-right-radius: 8px; "
                "font-size: 13px; font-weight: 700; }"
                "QPushButton:hover { color: #ba1a1a; border: 1px solid #ba1a1a; border-left: none; }"
            )
            close_btn.clicked.connect(lambda _c, p=pid: self._close_dataset(p))
            lay.addWidget(close_btn)
            self._chips_lay.addWidget(chip)
        self._chips_lay.addStretch()

    def closeEvent(self, event) -> None:
        # Never destroy a running QThread: stop the dashboard crawl and
        # adopt any live detail workers, giving each a bounded moment to
        # finish its in-flight request before the app tears down.
        try:
            self._dashboard.stop()
        except Exception:
            pass
        try:
            if self._detail is not None:
                for worker in self._detail.take_running_workers():
                    try:
                        worker.requestInterruption()
                        worker.quit()
                        worker.wait(3000)
                    except Exception:
                        pass
        except Exception:
            pass
        super().closeEvent(event)

    def _adopt_running_workers(self, view) -> None:
        """Reparent live workers so destroying their view cannot kill a QThread."""
        try:
            for worker in view.take_running_workers():
                worker.setParent(self)
                worker.finished.connect(worker.deleteLater)
                worker.error.connect(worker.deleteLater)
        except Exception:
            pass

    def _close_dataset(self, pid: str) -> None:
        """Close one open dataset chip; leaves the detail view if it was active."""
        self._open_pids = [(p, t) for p, t in self._open_pids if p != pid]
        if self._detail is not None and getattr(self._detail, "_pid", None) == pid:
            # Same adoption as _open_dataset: closing mid-metadata/download/
            # checks must not destroy a running QThread.
            self._adopt_running_workers(self._detail)
            try:
                self._stack.removeWidget(self._detail)
                self._detail.deleteLater()
            except Exception:
                pass
            self._detail = None
            self._stack.setCurrentWidget(self._dashboard)
            self._style_nav_for_detail(False)
        self._rebuild_chips()

    def _style_nav_for_detail(self, in_detail: bool) -> None:
        try:
            self._nav_dashboard.setObjectName("NavItem" if in_detail else "NavActive")
            self._nav_dashboard.style().unpolish(self._nav_dashboard)
            self._nav_dashboard.style().polish(self._nav_dashboard)
        except Exception:
            pass

    def _cache_metadata(self, pid: str, metadata: dict, inventory: list) -> None:
        self._metadata_cache[pid] = (metadata, inventory)

    def _show_dashboard(self) -> None:
        self._stack.setCurrentWidget(self._dashboard)
        self._style_nav_for_detail(False)
        self._rebuild_chips()
        # Pick up sizes/download state recorded while a dataset was open.
        try:
            self._dashboard.refresh_local_columns()
        except Exception:
            pass

    def _show_log(self) -> None:
        self._show_pane(None if self._log_panel.isVisible() else "log")

    def _edit_requirements(self) -> None:
        from ui.requirements_dialog import RequirementsDialog
        RequirementsDialog(self).exec()
        if self._detail is not None:
            try:
                if getattr(self._detail, "_metadata", None) is not None:
                    self._detail._populate_completeness(self._detail._metadata)
            except Exception:
                pass
