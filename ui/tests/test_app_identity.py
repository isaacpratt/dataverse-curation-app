"""App identity: Dataverse Docent rename + docent.png icon (probe40).

Covers the window title, the shared icon-path helper (dev + frozen via
sys._MEIPASS), and the About page's icon-beside-title treatment.
"""

from PySide6.QtWidgets import QLabel


def test_window_title_is_dataverse_docent(win):
    assert win.windowTitle() == "Dataverse Docent"


def test_window_carries_icon_for_taskbar(win):
    """Windows draws the taskbar icon from the window icon.

    Set it on the window itself, not only on QApplication (2026-10-07).
    """
    assert not win.windowIcon().isNull(), "window icon missing (blank taskbar entry)"


def test_app_icon_path_resolves_docent_png():
    from ui.theme import app_icon_path

    path = app_icon_path()
    assert path, "app_icon_path() returned nothing"
    assert path.replace("\\", "/").endswith("docent.png")


def test_docent_png_loads_as_pixmap():
    from PySide6.QtGui import QPixmap

    from ui.theme import app_icon_path

    pix = QPixmap(app_icon_path())
    assert not pix.isNull()
    assert pix.width() > 0 and pix.height() > 0


def test_about_page_shows_icon_beside_renamed_title(win, qapp):
    win._show_about()
    for _ in range(20):
        qapp.processEvents()
    about = win._about
    titles = [lbl for lbl in about.findChildren(QLabel) if "Dataverse Docent" in lbl.text()]
    assert titles, "About title not renamed"
    mark = about.findChild(QLabel, "DocentMark")
    assert mark is not None, "docent icon missing on About"
    assert not mark.pixmap().isNull()
    # 2026-10-07: About mark renders at the icon's native 64×64.
    assert mark.pixmap().height() == 64, mark.pixmap().height()
    assert mark.x() < titles[0].x()
    # Leave the shared window on the dashboard.
    win._show_dashboard()
    for _ in range(10):
        qapp.processEvents()
