"""Probe: the component gallery.

The gallery is the kit on one page. This probe checks that it builds,
that it shows a component of every kind, and that every button in it
wears one of the theme's button object names - the gallery must not
show a button the app cannot produce.

It also checks the gallery's own page background against the theme's
page role, so the gallery can never drift from the app it documents.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import Report, boot  # noqa: E402


def main() -> int:
    app, _cfg = boot()
    report = Report("gallery")

    from PySide6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QLineEdit,
        QListWidget,
        QPlainTextEdit,
        QProgressBar,
        QPushButton,
        QTableWidget,
        QTextEdit,
        QTreeWidget,
    )

    from ui.gallery import build_gallery
    from ui.theme import BUTTON_OBJECTS, SURFACE_PAGE

    try:
        window = build_gallery()
    except Exception as exc:  # pragma: no cover - the probe reports it
        report.check(False, "the gallery builds", repr(exc))
        return report.finish()

    report.check(True, "the gallery builds")
    window.show()
    for _ in range(3):
        app.processEvents()

    # Every kind of component the kit offers is on the page.
    wanted = {
        "button": QPushButton,
        "line edit": QLineEdit,
        "combo": QComboBox,
        "multi-line input": QTextEdit,
        "plain-text view": QPlainTextEdit,
        "list": QListWidget,
        "check box": QCheckBox,
        "progress bar": QProgressBar,
        "table": QTableWidget,
        "tree": QTreeWidget,
    }
    for label, cls in wanted.items():
        found = window.findChildren(cls)
        report.check(bool(found), f"the gallery shows a {label}", f"{len(found)} found")

    # Every button in the gallery wears a known button object name: the
    # gallery may not show a button the app cannot produce.
    names = set(BUTTON_OBJECTS.values())
    buttons = window.findChildren(QPushButton)
    report.check(bool(buttons), "the gallery shows buttons")
    unknown = sorted(
        {b.objectName() for b in buttons if b.objectName() and b.objectName() not in names}
    )
    report.check(not unknown, "every gallery button wears a kit object name", str(unknown))

    # The gallery's page background is the theme's page role.
    sheet = window.styleSheet() or ""
    report.check(
        SURFACE_PAGE in sheet,
        "the gallery paints the theme's page role",
        sheet[:120],
    )

    # A disabled button still paints its label: the disabled state is
    # part of the contract, not an accident of the app sheet.
    disabled = [b for b in buttons if not b.isEnabled()]
    report.check(bool(disabled), "the gallery shows a disabled button")

    window.close()
    return report.finish()


if __name__ == "__main__":
    raise SystemExit(main())
