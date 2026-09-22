"""Main window: unified title bar (TopNav + window controls) + stacked views.

TopNav IS the window title bar (custom frame: standard window styles with
the native caption stripped via WM_NCCALCSIZE, so no native chrome): it
holds all navigation (Dashboard, dataset chips, Settings, Requirements,
Log) plus custom minimize / maximize-restore / close buttons at the right
edge. Dragging empty TopNav space moves the window (native HTCAPTION on
Windows so snap/Aero keep working); double-click toggles maximize.
Open datasets show as full-title chips (never truncated to DOI). The status
bar's repository badge always shows the chosen Dataverse (base URL +
collection alias).
"""

from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)

# ctypes at module level: only struct *layouts* live here (no handles), so
# this is safe on every platform; all real Win32 calls stay Windows-gated.
import ctypes

from ui.dialogs import show_warning

from config import Config
from ui.about_pane import AboutPane
from ui.dashboard import DashboardView
from ui.dataset_detail import DatasetDetailView
from ui.log_panel import LogPage
from ui.settings_dialog import SettingsPane
from ui.widgets import AppButton


def _declare_dwm_signatures(dwmapi, margins_type) -> None:
    """Declare ctypes signatures for the DWM calls (Windows-only helper).

    Without argtypes ctypes coerces every argument to 32-bit int, silently
    truncating 64-bit HWNDs, so DWM calls fail while reporting nothing
    useful. Declared once here so both the window code and tests share them.
    Never raises.
    """
    try:
        import ctypes
        from ctypes import wintypes

        dwmapi.DwmExtendFrameIntoClientArea.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(margins_type),
        ]
        dwmapi.DwmExtendFrameIntoClientArea.restype = ctypes.HRESULT
        dwmapi.DwmSetWindowAttribute.argtypes = [
            wintypes.HWND,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
        ]
        dwmapi.DwmSetWindowAttribute.restype = ctypes.HRESULT
        dwmapi.DwmGetWindowAttribute.argtypes = [
            wintypes.HWND,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
        ]
        dwmapi.DwmGetWindowAttribute.restype = ctypes.HRESULT
    except Exception:
        pass


class _RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _WINDOWPLACEMENT(ctypes.Structure):
    _fields_ = [("length", ctypes.c_uint), ("flags", ctypes.c_uint),
                ("showCmd", ctypes.c_uint), ("ptMinPosition", _POINT),
                ("ptMaxPosition", _POINT), ("rcNormalPosition", _RECT)]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("rcMonitor", _RECT),
                ("rcWork", _RECT), ("dwFlags", ctypes.c_uint)]


class _NCCALCSIZE_PARAMS(ctypes.Structure):
    _fields_ = [("rgrc", _RECT * 3), ("lppos", ctypes.c_void_p)]


_SW_SHOWMAXIMIZED = 3
_MONITOR_DEFAULTTONEAREST = 2


def _user32():
    """user32 with the signatures this module needs, configured once."""
    import ctypes
    from ctypes import wintypes

    existing = globals().get("_USER32_CONFIGURED")
    handle = ctypes.windll.user32
    if not existing:
        handle.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        handle.MonitorFromWindow.restype = wintypes.HANDLE
        handle.GetMonitorInfoW.argtypes = [wintypes.HANDLE,
                                           ctypes.POINTER(_MONITORINFO)]
        handle.GetMonitorInfoW.restype = wintypes.BOOL
        handle.GetWindowPlacement.argtypes = [wintypes.HWND,
                                              ctypes.POINTER(_WINDOWPLACEMENT)]
        handle.GetWindowPlacement.restype = wintypes.BOOL
        globals()["_USER32_CONFIGURED"] = True
    return handle


def _work_area_for_hwnd(hwnd: int):
    """Work area (taskbar-excluded) of the monitor holding hwnd.

    Returns (left, top, right, bottom) or None when it cannot be
    determined. Pure ctypes — no Qt, so unit tests can call it with any
    real HWND (e.g. the desktop window) without a display widget.
    """
    try:
        import ctypes
        from ctypes import wintypes

        user32 = _user32()
        monitor = user32.MonitorFromWindow(wintypes.HWND(hwnd),
                                           _MONITOR_DEFAULTTONEAREST)
        if not monitor:
            return None
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(_MONITORINFO)
        if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return None
        rc = info.rcWork
        if rc.right <= rc.left or rc.bottom <= rc.top:
            return None
        return (rc.left, rc.top, rc.right, rc.bottom)
    except Exception:
        return None


def _maximized_client_rect(hwnd: int):
    """Client rect to enforce while maximized, else None.

    Caption-style windows overscan the screen edges when maximized (to
    hide their borders); since WM_NCCALCSIZE claims the whole window as
    client area, unconstrained content would slide under the taskbar and
    screen edges. Returns the monitor work area when the window is
    maximized so the handler can inset the client rect.
    """
    try:
        import ctypes
        from ctypes import wintypes

        user32 = _user32()
        placement = _WINDOWPLACEMENT()
        placement.length = ctypes.sizeof(_WINDOWPLACEMENT)
        if not user32.GetWindowPlacement(wintypes.HWND(hwnd),
                                         ctypes.byref(placement)):
            return None
        if int(placement.showCmd) != _SW_SHOWMAXIMIZED:
            return None
        return _work_area_for_hwnd(hwnd)
    except Exception:
        return None


class MainWindow(QMainWindow):
    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config
        self._metadata_cache: dict[str, tuple[dict, list]] = {}
        self._open_pids: list[tuple[str, str]] = []
        self.setWindowTitle("Dataverse Curation App")
        self.resize(1320, 860)
        # Custom frame, standard behavior: keep the normal window styles
        # (caption + thick frame) so DWM draws the border/shadow/snap, and
        # strip the native caption via WM_NCCALCSIZE in nativeEvent — the
        # TopNav below doubles as the title bar (custom min/max/close at
        # its right edge). Native resize/snap is restored via WM_NCHITTEST;
        # Qt fallback drag in eventFilter. A bare FramelessWindowHint window
        # (WS_POPUP, no caption) gets NO DWM shadow even with an extended
        # glass frame, which is how the border/shadow went missing before.
        self.setWindowFlags(Qt.Window)
        self._drag_pos = None
        self._border_width = 8
        # Native handle cache for use inside nativeEvent: NEVER call winId()
        # from a WindowProc callback — forcing native creation there re-enters
        # message processing and recurses until the stack blows up (killed
        # the app once via exactly this path). _apply_dwm_frame refreshes it
        # from safe (non-callback) contexts.
        self._hwnd = 0

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- TopNav doubles as the title bar (compact so nav + caption
        # buttons fit one 48px row; right margin 0 so Close meets the corner)
        self._topnav = QFrame()
        self._topnav.setObjectName("TopNav")
        self._topnav.setFixedHeight(48)
        nav_lay = QHBoxLayout(self._topnav)
        nav_lay.setContentsMargins(12, 0, 0, 0)
        nav_lay.setSpacing(6)

        self._nav_dashboard = AppButton("Dashboard", kind="nav-active", size=None)
        self._nav_dashboard.setCursor(Qt.PointingHandCursor)
        self._nav_dashboard.setFixedHeight(32)
        self._nav_dashboard.setToolTip("Back to the dashboard (Alt+Left)")
        self._nav_dashboard.clicked.connect(self._show_dashboard)
        nav_lay.addWidget(self._nav_dashboard)

        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("color: #c3c6d8;")
        sep.setFixedWidth(1)
        nav_lay.addWidget(sep)

        # Nav group: Settings, Review configuration, Log, Help (moved left)
        self._nav_settings = AppButton("Settings", kind="nav", size=None)
        self._nav_settings.setCheckable(True)
        self._nav_settings.setCursor(Qt.PointingHandCursor)
        self._nav_settings.setFixedHeight(32)
        self._nav_settings.setToolTip("Dataverse, API token, workspace (Ctrl+,)")
        self._nav_settings.toggled.connect(self._on_settings_toggled)
        nav_lay.addWidget(self._nav_settings)

        self._nav_requirements = AppButton("Review configuration", kind="nav", size=None)
        self._nav_requirements.setCursor(Qt.PointingHandCursor)
        self._nav_requirements.setFixedHeight(32)
        self._nav_requirements.setToolTip("Edit review rules and depositor response templates")
        self._nav_requirements.clicked.connect(self._show_review_config)
        nav_lay.addWidget(self._nav_requirements)

        self._nav_log = AppButton("Log", kind="nav", size=None)
        self._nav_log.setCheckable(True)
        self._nav_log.setCursor(Qt.PointingHandCursor)
        self._nav_log.setFixedHeight(32)
        self._nav_log.setToolTip("Show/hide curation log (Ctrl+L)")
        self._nav_log.toggled.connect(self._on_log_toggled)
        nav_lay.addWidget(self._nav_log)

        self._nav_help = AppButton("?", kind="nav", size=None)
        self._nav_help.setCheckable(True)
        self._nav_help.setFixedSize(32, 32)
        self._nav_help.setCursor(Qt.PointingHandCursor)
        self._nav_help.setToolTip("About this app")
        self._nav_help.toggled.connect(self._on_about_toggled)
        nav_lay.addWidget(self._nav_help)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.VLine)
        sep2.setStyleSheet("color: #c3c6d8;")
        sep2.setFixedWidth(1)
        nav_lay.addWidget(sep2)

        # Open dataset chips — full titles, never DOI-truncated
        self._chips_wrap = QWidget()
        self._chips_wrap.setObjectName("ChipsWrap")
        self._chips_wrap.setStyleSheet("QWidget#ChipsWrap { background: transparent; border: none; }")
        self._chips_wrap.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._chips_lay = QHBoxLayout(self._chips_wrap)
        self._chips_lay.setContentsMargins(4, 0, 8, 0)
        self._chips_lay.setSpacing(6)
        nav_lay.addWidget(self._chips_wrap, 1)

        # ---- Unified window controls (replace the native title bar) ----
        # 46x32 Windows-standard caption buttons, zero gap, flush to the
        # top-right corner (nav layout right margin is 0 for this reason).
        self._win_controls = QWidget()
        self._win_controls.setObjectName("WinControls")
        self._win_controls.setStyleSheet("QWidget#WinControls { background: transparent; border: none; }")
        win_lay = QHBoxLayout(self._win_controls)
        win_lay.setContentsMargins(6, 0, 0, 0)
        win_lay.setSpacing(0)
        win_base = (
            "QPushButton { background: transparent; color: #131b2e; border: none; "
            "border-radius: 0px; font-size: 13px; }"
            "QPushButton:hover { background: #e2e7ff; }"
            "QPushButton:pressed { background: #d5e3fc; }"
        )
        self._btn_min = QPushButton("–")
        self._btn_min.setFixedSize(46, 32)
        self._btn_min.setCursor(Qt.PointingHandCursor)
        self._btn_min.setToolTip("Minimize")
        self._btn_min.setStyleSheet(win_base)
        self._btn_min.clicked.connect(self.showMinimized)
        win_lay.addWidget(self._btn_min)
        self._btn_max = QPushButton("▢")
        self._btn_max.setFixedSize(46, 32)
        self._btn_max.setCursor(Qt.PointingHandCursor)
        self._btn_max.setToolTip("Maximize")
        self._btn_max.setStyleSheet(win_base)
        self._btn_max.clicked.connect(self._on_max_restore)
        win_lay.addWidget(self._btn_max)
        self._btn_close = QPushButton("✕")
        self._btn_close.setFixedSize(46, 32)
        self._btn_close.setCursor(Qt.PointingHandCursor)
        self._btn_close.setToolTip("Close")
        self._btn_close.setStyleSheet(
            "QPushButton { background: transparent; color: #131b2e; border: none; "
            "border-radius: 0px; font-size: 13px; }"
            "QPushButton:hover { background: #ba1a1a; color: #ffffff; }"
            "QPushButton:pressed { background: #93000a; color: #ffffff; }"
        )
        self._btn_close.clicked.connect(self.close)
        win_lay.addWidget(self._btn_close)
        nav_lay.addWidget(self._win_controls, 0)
        # Fallback drag for non-Windows (Windows uses HTCAPTION in
        # nativeEvent so snap/Aero keep working).
        self._topnav.installEventFilter(self)

        root.addWidget(self._topnav)

        # ---- Stacked pages (full-page views) ----
        self._stack = QStackedWidget()
        root.addWidget(self._stack, 1)

        # Hide the native menu bar — everything is in TopNav now
        try:
            self.menuBar().setVisible(False)
        except Exception:
            pass

        # Keyboard shortcuts previously on menu actions. Keep refs so Qt
        # does not garbage-collect them (required on some bindings).
        try:
            self._shortcuts = [
                QShortcut(QKeySequence("Ctrl+,", QKeySequence.PortableText), self, self._open_settings),  # type: ignore[arg-type]
                QShortcut(QKeySequence("Ctrl+L", QKeySequence.PortableText), self, self._show_log),  # type: ignore[arg-type]
                QShortcut(QKeySequence("Alt+Left", QKeySequence.PortableText), self, self._show_dashboard),  # type: ignore[arg-type]
            ]
        except Exception:
            self._shortcuts = []

        # Hide the native menu bar — everything is in TopNav now
        try:
            self.menuBar().setVisible(False)
        except Exception:
            pass
        # No status bar: repository scope lives in the dashboard title.

        self._dashboard = DashboardView(config)
        self._dashboard.openRequested.connect(self._open_dataset)
        self._stack.addWidget(self._dashboard)
        try:
            from ui.review_config import ReviewConfigView

            self._review_config = ReviewConfigView(config)
            self._review_config.saved.connect(self._on_review_config_saved)
            self._stack.addWidget(self._review_config)
        except Exception:
            self._review_config = None
        self._settings = SettingsPane(config)
        self._settings.saved.connect(self._on_settings_saved)
        self._settings.discarded.connect(lambda: self._show_pane(None))
        # Stack pages wrapped in scroll areas (never layout siblings): tall
        # panes scroll in place instead of growing the window.
        self._settings_page = self._wrap_pane_page(self._settings)
        self._stack.addWidget(self._settings_page)
        self._about = AboutPane(self)
        self._about.discarded.connect(lambda: self._show_pane(None))
        self._about_page = self._wrap_pane_page(self._about)
        self._stack.addWidget(self._about_page)
        # Full-page log view
        self._log_page = LogPage(self)
        self._stack.addWidget(self._log_page)
        # Content role to return to when a settings/about page closes.
        self._pane_return: str | None = None
        self._detail: DatasetDetailView | None = None

        if not self._config.dataverse.base_url:
            self._open_settings()

    # -- status / repo badge -------------------------------------------

    @staticmethod
    def _wrap_pane_page(pane) -> QWidget:
        """Scroll-wrapped stack page for a tall pane.

        The scroll area (not the pane) joins the stack, so the page's
        sizeHint stays small and opening it never resizes the window —
        overflow scrolls instead.
        """
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: #faf8ff; border: none; }")
        scroll.setWidget(pane)
        return scroll

    # -- slots ----------------------------------------------------------

    def _content_role(self) -> str:
        """Which content the stack shows: dashboard/detail/review/settings/about/log."""
        try:
            cur = self._stack.currentWidget()
        except Exception:
            return "dashboard"
        if cur is getattr(self, "_settings_page", None):
            return "settings"
        if cur is getattr(self, "_about_page", None):
            return "about"
        if cur is getattr(self, "_log_page", None):
            return "log"
        if getattr(self, "_review_config", None) is not None and cur is self._review_config:
            return "review"
        if self._detail is not None and cur is self._detail:
            return "detail"
        return "dashboard"

    def _role_widget(self, role) -> QWidget:
        """Stack widget for a content role (dashboard fallback, never raises)."""
        try:
            if role == "review" and getattr(self, "_review_config", None) is not None:
                return self._review_config
            if role == "detail" and self._detail is not None:
                return self._detail
        except Exception:
            pass
        return self._dashboard

    def _refresh_nav_state(self) -> None:
        """Highlight the active location tab + sync pane toggles with reality."""
        try:
            role = self._content_role()
        except Exception:
            role = "dashboard"
        try:
            self._nav_dashboard.setObjectName("NavActive" if role == "dashboard" else "NavItem")
            self._nav_dashboard.style().unpolish(self._nav_dashboard)
            self._nav_dashboard.style().polish(self._nav_dashboard)
        except Exception:
            pass
        try:
            self._nav_requirements.setObjectName("NavActive" if role == "review" else "NavItem")
            self._nav_requirements.style().unpolish(self._nav_requirements)
            self._nav_requirements.style().polish(self._nav_requirements)
        except Exception:
            pass
        for btn, on in (
            (self._nav_log, role == "log"),
            (self._nav_settings, role == "settings"),
            (self._nav_help, role == "about"),
        ):
            try:
                btn.blockSignals(True)
                btn.setChecked(bool(on))
            except Exception:
                pass
            finally:
                try:
                    btn.blockSignals(False)
                except Exception:
                    pass

    def _show_pane(self, name) -> None:
        """Show one pane exclusively (settings/about) or switch to log page."""
        try:
            role = self._content_role()
            if name in ("settings", "about"):
                # Exclusive like before: opening a page switches stack.
                if role not in ("settings", "about"):
                    self._pane_return = role
                target = self._settings_page if name == "settings" else self._about_page
                if self._stack.currentWidget() is not target:
                    self._stack.setCurrentWidget(target)
            elif name == "log":
                # Switch to log page; remember where we came from.
                if role not in ("log", "settings", "about"):
                    self._pane_return = role
                if self._stack.currentWidget() is not self._log_page:
                    self._stack.setCurrentWidget(self._log_page)
            elif name is None:
                # Close pane: return to previous content if we're in settings/about/log.
                if role in ("settings", "about", "log"):
                    self._stack.setCurrentWidget(self._role_widget(getattr(self, "_pane_return", None)))
                    self._pane_return = None
            # Any other name: stack untouched.
        except Exception:
            pass
        self._refresh_nav_state()

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
        # Direct navigation abandons any pane return target.
        self._pane_return = None
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
        elif getattr(self, "_review_config", None) is not None and self._stack.currentWidget() is self._review_config:
            active_pid = None
        elif self._detail is not None:
            active_pid = getattr(self._detail, "_pid", None)
        else:
            active_pid = None
        for pid, title in self._open_pids:
            # FULL title, never DOI-truncated; tooltip carries the persistent ID.
            # Each chip has an x-icon button to close that dataset.
            label = (title or pid).strip() or pid
            chip = QFrame()
            chip.setObjectName("DatasetChip")
            chip.setStyleSheet("QFrame#DatasetChip { background: transparent; border: none; }")
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
            open_btn.setMaximumWidth(220)
            open_btn.setMinimumWidth(60)
            open_btn.setStyleSheet(
                "QPushButton { background: #eaedff; color: #131b2e; border: 1px solid #004ccd; "
                "border-top-left-radius: 8px; border-bottom-left-radius: 8px; "
                "padding: 0 10px 0 10px; font-size: 11px; font-weight: 700; text-align: left; }"
                if is_active else
                "QPushButton { background: #ffffff; color: #131b2e; border: 1px solid #c3c6d8; "
                "border-top-left-radius: 8px; border-bottom-left-radius: 8px; "
                "padding: 0 10px 0 10px; font-size: 11px; font-weight: 600; text-align: left; }"
                "QPushButton:hover { border: 1px solid #004ccd; }"
            )
            open_btn.clicked.connect(lambda _c, p=pid, t=title: self._open_dataset(p, t))
            lay.addWidget(open_btn)
            close_btn = QPushButton()
            close_btn.setCursor(Qt.PointingHandCursor)
            close_btn.setToolTip(f"Close {label}")
            close_btn.setFixedSize(28, 28)
            try:
                from PySide6.QtCore import QSize as _QSize

                from ui.icons import icon as _chip_icon

                close_btn.setIcon(
                    _chip_icon("x", color="#131b2e" if is_active else "#57657a")
                )
                close_btn.setIconSize(_QSize(12, 12))
            except Exception:
                close_btn.setText("×")
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
        # adopted workers, requesting interruption and waiting boundedly.
        # Note: QThread.quit() is a no-op for overridden run() loops without
        # an event loop — interruption + wait is what actually stops them.
        try:
            self._dashboard.stop()
        except Exception:
            pass
        workers: list = []
        try:
            if self._detail is not None:
                workers.extend(self._detail.take_running_workers())
        except Exception:
            pass
        try:
            workers.extend(getattr(self, "_adopted_workers", []) or [])
        except Exception:
            pass
        for worker in workers:
            try:
                worker.requestInterruption()
                # quit() harmless for event-loop workers; wait() covers
                # run()-override workers via interruption polling.
                try:
                    worker.quit()
                except Exception:
                    pass
                worker.wait(5000)
            except Exception:
                pass
        super().closeEvent(event)

    def _adopt_running_workers(self, view) -> None:
        """Reparent live workers so destroying their view cannot kill a QThread."""
        try:
            if not hasattr(self, "_adopted_workers"):
                self._adopted_workers: list = []
            for worker in view.take_running_workers():
                worker.setParent(self)
                self._adopted_workers.append(worker)
                # deleteLater on finish + drop from tracking.
                worker.finished.connect(worker.deleteLater)
                worker.error.connect(worker.deleteLater)
                try:
                    worker.finished.connect(lambda *a, w=worker: self._forget_worker(w))
                    worker.error.connect(lambda *a, w=worker: self._forget_worker(w))
                except Exception:
                    pass
        except Exception:
            pass

    def _forget_worker(self, worker) -> None:
        try:
            tracked = getattr(self, "_adopted_workers", [])
            if worker in tracked:
                tracked.remove(worker)
        except Exception:
            pass

    def _close_dataset(self, pid: str) -> None:
        """Close one open dataset chip; leaves the detail view if it was active."""
        self._open_pids = [(p, t) for p, t in self._open_pids if p != pid]
        if self._detail is not None and getattr(self._detail, "_pid", None) == pid:
            # Same adoption as _open_dataset: closing mid-metadata/download/
            # checks must not destroy a running QThread.
            self._adopt_running_workers(self._detail)
            was_showing = self._stack.currentWidget() is self._detail
            try:
                self._stack.removeWidget(self._detail)
                self._detail.deleteLater()
            except Exception:
                pass
            self._detail = None
            if was_showing:
                # Detail was on screen: fall back to the dashboard. A
                # settings/about page stays put (only its return updates).
                self._stack.setCurrentWidget(self._dashboard)
                self._pane_return = None
            elif getattr(self, "_pane_return", None) == "detail":
                self._pane_return = "dashboard"
            self._style_nav_for_detail(False)
        self._rebuild_chips()

    def _style_nav_for_detail(self, in_detail: bool) -> None:
        # Legacy entry point: nav state is derived from the stack now.
        try:
            self._refresh_nav_state()
        except Exception:
            pass

    def _cache_metadata(self, pid: str, metadata: dict, inventory: list) -> None:
        self._metadata_cache[pid] = (metadata, inventory)

    def _show_dashboard(self) -> None:
        self._stack.setCurrentWidget(self._dashboard)
        self._pane_return = None
        self._style_nav_for_detail(False)
        self._rebuild_chips()
        # Pick up sizes/download state recorded while a dataset was open.
        try:
            self._dashboard.refresh_local_columns()
        except Exception:
            pass

    def _show_log(self) -> None:
        # Toggle log page via Ctrl+L
        role = self._content_role()
        self._show_pane(None if role == "log" else "log")

    # -- unified title bar: window controls + drag/resize ----------------

    def _on_max_restore(self) -> None:
        try:
            if self.isMaximized():
                self.showNormal()
            else:
                self.showMaximized()
        except Exception:
            pass
        self._update_max_glyph()
        self._apply_dwm_frame()

    def _update_max_glyph(self) -> None:
        try:
            if self.isMaximized():
                self._btn_max.setText("❐")
                self._btn_max.setToolTip("Restore")
            else:
                self._btn_max.setText("▢")
                self._btn_max.setToolTip("Maximize")
        except Exception:
            pass

    def changeEvent(self, event) -> None:
        try:
            super().changeEvent(event)
        except Exception:
            pass
        try:
            if event.type() == QEvent.WindowStateChange:
                self._update_max_glyph()
                self._apply_dwm_frame()
        except Exception:
            pass

    def showEvent(self, event) -> None:
        try:
            super().showEvent(event)
        except Exception:
            pass
        # HWND + DWM are ready here; also re-applied on every
        # maximize/restore (see _on_max_restore/changeEvent).
        self._apply_dwm_frame()

    def _apply_dwm_frame(self) -> None:
        """Restore the standard Windows border + drop shadow.

        Frameless windows lose the DWM frame entirely (no border, no
        shadow, square corners). Extending the frame 1px into the client
        area brings back the system-drawn 1px border and shadow while the
        custom TopNav keeps working; maximized windows get zero margins
        (standard: no shadow/border when maximized). Win11 also gets the
        standard rounded corners. No-ops off Windows or when DWM is
        unavailable — never raises.
        """
        try:
            import sys as _sys

            if not _sys.platform.startswith("win"):
                return
            import ctypes
            from ctypes import wintypes

            try:
                hwnd = int(self.winId())
            except Exception:
                return
            if not hwnd:
                return
            self._hwnd = hwnd
            dwmapi = ctypes.windll.dwmapi

            class _MARGINS(ctypes.Structure):
                _fields_ = [
                    ("cxLeftWidth", ctypes.c_int),
                    ("cxRightWidth", ctypes.c_int),
                    ("cyTopHeight", ctypes.c_int),
                    ("cyBottomHeight", ctypes.c_int),
                ]

            # NOTE: argtypes are REQUIRED here and are configured before any
            # handle is touched (also so tests can assert the declarations).
            # Without them ctypes passes every argument as 32-bit int,
            # truncating the 64-bit HWND, so both calls below fail on 64-bit
            # Python — previously with no trace, which is exactly how the
            # border/shadow went missing.
            _declare_dwm_signatures(dwmapi, _MARGINS)

            try:
                from applog import get_app_log as _get_log
            except Exception:
                _get_log = None  # type: ignore[assignment]

            def _report(what: str, hr: int) -> None:
                if _get_log is None:
                    return
                try:
                    if int(hr) == 0:
                        _get_log().info(f"DWM frame: {what} applied")
                    else:
                        _get_log().error(
                            f"DWM frame: {what} failed (HRESULT 0x{int(hr) & 0xFFFFFFFF:08X})"
                        )
                except Exception:
                    pass

            if self.isMaximized():
                margins = _MARGINS(0, 0, 0, 0)
            else:
                margins = _MARGINS(1, 1, 1, 1)
            hr_frame = dwmapi.DwmExtendFrameIntoClientArea(
                wintypes.HWND(hwnd), ctypes.byref(margins)
            )
            _report("1px extended frame (border + shadow)", hr_frame)
            # Win11 22000+: standard rounded corners (fails harmlessly on
            # Win10, where the attribute does not exist — logged, not raised).
            _DWMWA_WINDOW_CORNER_PREFERENCE = 33
            _DWMWCP_ROUND = 2
            pref = ctypes.c_int(_DWMWCP_ROUND)
            hr_corners = dwmapi.DwmSetWindowAttribute(
                wintypes.HWND(hwnd),
                _DWMWA_WINDOW_CORNER_PREFERENCE,
                ctypes.byref(pref),
                ctypes.sizeof(pref),
            )
            _report("rounded corners", hr_corners)
        except Exception:
            pass

    def _topnav_is_interactive(self, topnav_pos) -> bool:
        """True when the TopNav point sits on a clickable control."""
        try:
            for btn in self._topnav.findChildren(QPushButton):
                try:
                    if not btn.isVisible():
                        continue
                    # topnav_pos is TopNav-local; map into the button.
                    mapped = btn.mapFrom(self._topnav, topnav_pos)
                    if btn.rect().contains(mapped):
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        return False

    def eventFilter(self, obj, event):
        # Fallback drag for platforms without nativeEvent (non-Windows).
        # Windows uses HTCAPTION in nativeEvent, so this is a no-op there.
        try:
            import sys as _sys

            if obj is self._topnav and not _sys.platform.startswith("win"):
                etype = event.type()
                if etype == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                    if not self.isMaximized() and not self._topnav_is_interactive(event.position().toPoint()):
                        self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                        return True
                elif etype == QEvent.MouseMove:
                    if self._drag_pos is not None and event.buttons() & Qt.LeftButton and not self.isMaximized():
                        self.move(event.globalPosition().toPoint() - self._drag_pos)
                        return True
                elif etype == QEvent.MouseButtonRelease:
                    self._drag_pos = None
                elif etype == QEvent.MouseButtonDblClick:
                    if not self._topnav_is_interactive(event.position().toPoint()):
                        self._on_max_restore()
                        return True
        except Exception:
            pass
        try:
            return super().eventFilter(obj, event)
        except Exception:
            return False

    def nativeEvent(self, eventType, message):
        """Custom-frame handling on Windows.

        WM_NCCALCSIZE strips the native caption/borders (whole window becomes
        client area); maximized windows are inset to the monitor work area.
        WM_NCHITTEST returns HTCAPTION over empty TopNav space (native drag,
        double-click maximize, Aero snap) and HT* edge codes over the window
        border (native resize). Points over actual buttons stay HTCLIENT so
        clicks work.
        """
        try:
            import sys as _sys

            if _sys.platform.startswith("win"):
                etype = ""
                try:
                    etype = bytes(eventType).decode("ascii", "ignore")
                except Exception:
                    try:
                        etype = eventType.data().decode("ascii", "ignore")
                    except Exception:
                        etype = str(eventType)
                if "windows_generic_MSG" in etype:
                    import ctypes

                    try:
                        addr = message.__int__()
                    except Exception:
                        addr = int(message)
                    msg = ctypes.wintypes.MSG.from_address(addr)
                    WM_NCCALCSIZE = 0x83
                    if msg.message == WM_NCCALCSIZE:
                        # Strip the native caption/borders: the whole window
                        # becomes client area, leaving TopNav as the only
                        # chrome. DWM keeps drawing border/shadow/snap around
                        # it because the underlying caption/thickframe styles
                        # are intact (a bare FramelessWindowHint popup gets
                        # none of that even with extended glass).
                        #
                        # CAUTION: never call winId() (or anything that can
                        # force native window creation) from in here — it
                        # re-enters this callback and overflows the stack.
                        # Use the cached handle from _apply_dwm_frame; when
                        # it is not known yet, strip without insetting (the
                        # window cannot be maximized before first show).
                        if msg.wParam:
                            try:
                                hwnd = int(getattr(self, "_hwnd", 0) or 0)
                                target = _maximized_client_rect(hwnd) if hwnd else None
                            except Exception:
                                target = None
                            if target is not None:
                                # Maximized caption windows overscan the
                                # screen edges; inset the client rect to the
                                # monitor work area so content never slides
                                # under the taskbar or off-screen.
                                try:
                                    params = ctypes.cast(
                                        int(msg.lParam),
                                        ctypes.POINTER(_NCCALCSIZE_PARAMS),
                                    ).contents
                                    (params.rgrc[0].left, params.rgrc[0].top,
                                     params.rgrc[0].right, params.rgrc[0].bottom) = target
                                except Exception:
                                    pass
                            return True, 0
                        return super().nativeEvent(eventType, message)
                    WM_NCHITTEST = 0x84
                    if msg.message == WM_NCHITTEST:
                        HTCLIENT, HTCAPTION = 1, 2
                        HTLEFT, HTRIGHT, HTTOP = 10, 11, 12
                        HTTOPLEFT, HTTOPRIGHT = 13, 14
                        HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT = 15, 16, 17
                        raw = msg.lParam & 0xFFFFFFFF
                        x = raw & 0xFFFF
                        y = (raw >> 16) & 0xFFFF
                        if x >= 0x8000:
                            x -= 0x10000
                        if y >= 0x8000:
                            y -= 0x10000
                        global_pt = QPoint(x, y)
                        if not self.rect().contains(self.mapFromGlobal(global_pt)):
                            return super().nativeEvent(eventType, message)
                        # Caption buttons and nav controls keep clicks.
                        try:
                            for btn in self._topnav.findChildren(QPushButton):
                                try:
                                    if btn.isVisible() and btn.rect().contains(btn.mapFromGlobal(global_pt)):
                                        return True, HTCLIENT
                                except Exception:
                                    continue
                        except Exception:
                            pass
                        if self.isMaximized():
                            # Borders don't resize when maximized; TopNav
                            # still drags (restore-on-drag handled by Windows).
                            try:
                                topnav_rect = self._topnav.rect()
                                topnav_tl = self._topnav.mapToGlobal(topnav_rect.topLeft())
                                from PySide6.QtCore import QRect as _QRect

                                if _QRect(topnav_tl, topnav_rect.size()).contains(global_pt):
                                    return True, HTCAPTION
                            except Exception:
                                pass
                            return True, HTCLIENT
                        bw = int(getattr(self, "_border_width", 8) or 8)
                        local = self.mapFromGlobal(global_pt)
                        r = self.rect()
                        left = local.x() < bw
                        right = local.x() >= r.width() - bw
                        top = local.y() < bw
                        bottom = local.y() >= r.height() - bw
                        if top and left:
                            return True, HTTOPLEFT
                        if top and right:
                            return True, HTTOPRIGHT
                        if bottom and left:
                            return True, HTBOTTOMLEFT
                        if bottom and right:
                            return True, HTBOTTOMRIGHT
                        if left:
                            return True, HTLEFT
                        if right:
                            return True, HTRIGHT
                        if top:
                            return True, HTTOP
                        if bottom:
                            return True, HTBOTTOM
                        try:
                            topnav_rect = self._topnav.rect()
                            topnav_tl = self._topnav.mapToGlobal(topnav_rect.topLeft())
                            from PySide6.QtCore import QRect as _QRect

                            if _QRect(topnav_tl, topnav_rect.size()).contains(global_pt):
                                return True, HTCAPTION
                        except Exception:
                            pass
                        return True, HTCLIENT
        except Exception:
            pass
        try:
            return super().nativeEvent(eventType, message)
        except Exception:
            return False, 0

    def _show_review_config(self) -> None:
        """Show the full-page Review configuration (replaces the old dialog)."""
        try:
            if getattr(self, "_review_config", None) is None:
                from ui.review_config import ReviewConfigView

                self._review_config = ReviewConfigView(self._config)
                self._review_config.saved.connect(self._on_review_config_saved)
                self._stack.addWidget(self._review_config)
            self._review_config.refresh_for_dataverse()
            self._stack.setCurrentWidget(self._review_config)
            self._pane_return = None
            self._style_nav_for_detail(True)
            self._rebuild_chips()
        except Exception as exc:
            show_warning(self, "Review configuration", f"Could not open review configuration:\n{exc}")

    def _on_review_config_saved(self) -> None:
        if self._detail is not None:
            try:
                if getattr(self._detail, "_metadata", None) is not None:
                    self._detail.refresh_rules()
            except Exception:
                pass

    def _edit_requirements(self) -> None:
        # Back-compat entry point (old nav slot): route to the full page.
        self._show_review_config()
