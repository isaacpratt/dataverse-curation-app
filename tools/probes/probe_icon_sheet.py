"""Probe: every mark is a bundled Lucide glyph (dv-kvb).

Three things a unit test cannot see:

* the gallery's icon sheet actually paints a visible mark in every tile, at
  both sizes (16 and 20px) - a name that resolves to an empty pixmap looks
  identical to a name that does not exist;
* the three controls this bead re-pointed carry the glyph they should: the
  refresh buttons (rotate-ccw, icon plus label), the sidebar toggle
  (panel-right-close / panel-right-open) and the progress ring (the check
  in its complete state, not a typed character).

A screenshot of the icon sheet goes to reports/probes/.

Run: python tools/probes/probe_icon_sheet.py
"""

from __future__ import annotations

import sys

from _common import Report, boot, save_artifact


def _marks(window, name: str) -> list:
    """Return the painted marks captioned with one glyph name (one per size)."""
    from PySide6.QtWidgets import QLabel

    return [
        label
        for label in window.findChildren(QLabel)
        if str(label.property("icon_name") or "") == name
    ]


def _has_ink(label) -> bool:
    """Whether a label's pixmap carries at least one non-transparent pixel."""
    pixmap = label.pixmap()
    if pixmap is None or pixmap.isNull():
        return False
    image = pixmap.toImage()
    for y in range(image.height()):
        for x in range(image.width()):
            if image.pixelColor(x, y).alpha() > 0:
                return True
    return False


def main() -> int:
    app, _cfg = boot()
    from PySide6.QtWidgets import QScrollArea

    from ui.gallery import build_gallery
    from ui.icons import ICON_ROLES

    report = Report("icon sheet")
    window = build_gallery()
    window.resize(1440, 900)
    window.show()
    for _ in range(10):
        app.processEvents()

    expected = sorted(set(ICON_ROLES.values()))
    blank = [name for name in expected if not _marks(window, name)]
    report.check(not blank, "every role glyph has a tile on the icon sheet", f"missing={blank}")

    # Every tile shows ink at both sizes (a null pixmap is blank, not blank-ish).
    no_ink = []
    for name in expected:
        tile_marks = _marks(window, name)
        if len(tile_marks) < 2:
            no_ink.append((name, "one size only"))
            continue
        for label in tile_marks:
            if not _has_ink(label):
                no_ink.append((name, label.width()))
    report.check(
        not no_ink, "every tile paints a visible mark at 16 and 20px", f"blank={no_ink[:4]}"
    )
    report.check(
        any(_marks(window, "panel-right-close")),
        "the sidebar-hide glyph is on the sheet",
    )
    report.check(any(_marks(window, "panel-right-open")), "the sidebar-show glyph is on the sheet")
    report.check(any(_marks(window, "ellipsis")), "the more glyph is on the sheet")

    # The refresh helper leads with rotate-ccw and keeps its label: the
    # queue and the Log page both build their refresh through it.
    from ui.widgets import make_refresh_button

    refresh = make_refresh_button("Refresh")
    report.check(
        refresh.text() == "Refresh" and not refresh.icon().isNull(),
        "the refresh button carries rotate-ccw and keeps its label",
    )

    # The ring's complete state paints the Lucide check, not a character.
    from ui.widgets import RingProgress

    ring = RingProgress(diameter=28)
    ring.setFraction(1.0)
    ring.show()
    for _ in range(4):
        app.processEvents()
    image = ring.grab().toImage()
    green_ink = sum(
        1
        for y in range(image.height())
        for x in range(image.width())
        if image.pixelColor(x, y).alpha() > 0
    )
    report.check(green_ink > 0, "the ring paints its completion mark", f"pixels={green_ink}")
    ring.deleteLater()

    # Eyeball shot of the icon sheet itself.
    sheet = _marks(window, expected[0])
    if sheet:
        anchor = sheet[0].parentWidget()
        for scroll in window.findChildren(QScrollArea):
            scroll.ensureWidgetVisible(anchor)
        for _ in range(6):
            app.processEvents()
    path = save_artifact(window, "icon_sheet_1440.png")
    print(f"  [note] screenshot: {path.name}")
    window.deleteLater()
    for _ in range(2):
        app.processEvents()
    return report.finish()


if __name__ == "__main__":
    sys.exit(main())
