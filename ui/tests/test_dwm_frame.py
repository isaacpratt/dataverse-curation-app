"""Regression tests for the native window frame (MainWindow._apply_dwm_frame).

Background: the frameless window lost its border/shadow because the DWM
calls were issued without ctypes argtypes, so 64-bit HWNDs were truncated
to 32 bits and both calls failed with no trace. These tests pin the
declarations and the log-instead-of-silence contract without needing a
display (no QApplication required).
"""

import sys

import pytest

win32_only = pytest.mark.skipif(
    not sys.platform.startswith("win"), reason="Windows-only DWM interop"
)


@win32_only
def test_dwm_signatures_use_full_width_hwnd():
    """Declared signatures must pass HWND at full pointer width."""
    import ctypes
    from ctypes import wintypes

    from ui.main_window import _declare_dwm_signatures

    class _MARGINS(ctypes.Structure):
        _fields_ = [
            ("cxLeftWidth", ctypes.c_int),
            ("cxRightWidth", ctypes.c_int),
            ("cyTopHeight", ctypes.c_int),
            ("cyBottomHeight", ctypes.c_int),
        ]

    dwmapi = ctypes.windll.dwmapi
    old_extend = (
        dwmapi.DwmExtendFrameIntoClientArea.argtypes,
        dwmapi.DwmExtendFrameIntoClientArea.restype,
    )
    old_attr = (dwmapi.DwmSetWindowAttribute.argtypes, dwmapi.DwmSetWindowAttribute.restype)
    old_get = (dwmapi.DwmGetWindowAttribute.argtypes, dwmapi.DwmGetWindowAttribute.restype)
    try:
        _declare_dwm_signatures(dwmapi, _MARGINS)
        assert dwmapi.DwmExtendFrameIntoClientArea.argtypes[0] is wintypes.HWND
        assert dwmapi.DwmExtendFrameIntoClientArea.restype == ctypes.HRESULT
        assert dwmapi.DwmSetWindowAttribute.argtypes[0] is wintypes.HWND
        assert dwmapi.DwmSetWindowAttribute.restype == ctypes.HRESULT
        assert dwmapi.DwmGetWindowAttribute.argtypes[0] is wintypes.HWND
    finally:
        (
            dwmapi.DwmExtendFrameIntoClientArea.argtypes,
            dwmapi.DwmExtendFrameIntoClientArea.restype,
        ) = old_extend
        dwmapi.DwmSetWindowAttribute.argtypes, dwmapi.DwmSetWindowAttribute.restype = old_attr
        dwmapi.DwmGetWindowAttribute.argtypes, dwmapi.DwmGetWindowAttribute.restype = old_get


@win32_only
def test_hwnd_survives_ctypes_boundary():
    """A realistic >32-bit HWND must round-trip through wintypes.HWND."""
    from ctypes import wintypes

    big = 0x0000023A4F51C8D1
    assert big > 0xFFFFFFFF
    assert wintypes.HWND(big).value == big


@win32_only
def test_dwm_failure_is_logged_with_full_hwnd(monkeypatch):
    """End to end through _apply_dwm_frame with a stub DWM module.

    Uses a >32-bit handle: proves the real method path hands DWM the full
    value (the original truncation bug) and that a failing HRESULT lands in
    the app log instead of vanishing.
    """
    from curation import applog
    from ui.main_window import MainWindow

    seen = {}

    class FakeDwm:
        def DwmExtendFrameIntoClientArea(self, hwnd, _margins):
            seen["frame_hwnd"] = int(getattr(hwnd, "value", hwnd))
            return 0x80070006  # E_HANDLE

        def DwmSetWindowAttribute(self, _hwnd, _attr, _val, _size):
            return 0

    class FakeWindll:
        dwmapi = FakeDwm()

    monkeypatch.setattr("ctypes.windll", FakeWindll())

    class FakeSelf:
        def winId(self):
            return 0x0000023A4F51C8D1

        def isMaximized(self):
            return False

    before = len(applog.lines())
    MainWindow._apply_dwm_frame(FakeSelf())
    assert seen["frame_hwnd"] == 0x0000023A4F51C8D1
    fresh = applog.lines()[before:]
    assert any("0x80070006" in line for line in fresh)


def test_apply_dwm_frame_never_raises_without_window():
    """Missing/unusable native handle is an early return, never an error."""
    from ui.main_window import MainWindow

    class NoHandle:
        def winId(self):
            return 0

    class BadHandle:
        def winId(self):
            raise RuntimeError("no native window")

    MainWindow._apply_dwm_frame(NoHandle())
    MainWindow._apply_dwm_frame(BadHandle())


@win32_only
def test_cloak_window_sets_dwm_cloak_attribute(monkeypatch):
    """The window is cloaked (attribute 13) until the first frame is ready."""
    from ui.main_window import MainWindow

    seen = {}

    class FakeDwm:
        def DwmSetWindowAttribute(self, hwnd, attr, value, size):
            seen["hwnd"] = int(getattr(hwnd, "value", hwnd))
            seen["attr"] = int(attr)
            seen["value"] = value._obj.value
            seen["size"] = int(size)
            return 0

    class FakeWindll:
        dwmapi = FakeDwm()

    monkeypatch.setattr("ctypes.windll", FakeWindll())

    class FakeSelf:
        _hwnd = 0x0000023A4F51C8D1

        def winId(self):
            return self._hwnd

    assert MainWindow._cloak_window(FakeSelf(), True) is True
    assert seen == {
        "hwnd": 0x0000023A4F51C8D1,
        "attr": 13,
        "value": 1,
        "size": 4,
    }

    assert MainWindow._cloak_window(FakeSelf(), False) is True
    assert seen["value"] == 0


def test_cloak_window_never_raises_without_window():
    """Cloaking degrades to False (window still shows) when Win32 fails."""
    from ui.main_window import MainWindow

    class NoHandle:
        _hwnd = 0

        def winId(self):
            return 0

    class BadHandle:
        def winId(self):
            raise RuntimeError("no native window")

    assert MainWindow._cloak_window(NoHandle(), True) is False
    assert MainWindow._cloak_window(BadHandle(), True) is False


@win32_only
def test_work_area_for_hwnd_returns_plausible_rect():
    """Work-area lookup works against a real HWND with no Qt involved."""
    import ctypes
    from ctypes import wintypes

    from ui.main_window import _work_area_for_hwnd

    user32 = ctypes.windll.user32
    user32.GetDesktopWindow.restype = wintypes.HWND
    rect = _work_area_for_hwnd(int(user32.GetDesktopWindow()))
    assert rect is not None
    left, top, right, bottom = rect
    assert right - left > 100
    assert bottom - top > 100


@win32_only
def test_maximized_client_rect_none_when_not_maximized():
    """A non-maximized window needs no client inset (desktop never is)."""
    import ctypes
    from ctypes import wintypes

    from ui.main_window import _maximized_client_rect

    user32 = ctypes.windll.user32
    user32.GetDesktopWindow.restype = wintypes.HWND
    assert _maximized_client_rect(int(user32.GetDesktopWindow())) is None
    assert _maximized_client_rect(0) is None
