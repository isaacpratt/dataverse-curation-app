"""Probe: hover never paints a chosen-row band in the rules table (dv-ud0).

Selects row A, hovers row B (its text, its level combo and its check combo),
and checks that the pointer leaves no row band behind while row A keeps the
selected face and stays the row the Response pane edits. Saves a screenshot
with row B hovered to eyeball.

Run: python tools/probes/probe_review_selection.py
"""

from __future__ import annotations

import sys

from _common import Report, boot, save_artifact


def _rgb(hex_color: str) -> tuple[int, int, int]:
    text = str(hex_color).lstrip("#")
    return tuple(int(text[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def main() -> int:
    app, cfg = boot()
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from ui.theme import SECONDARY_CONTAINER, SURFACE_SUBTLE
    from ui.widgets import AppTreeWidget

    report = Report("review row selection")
    view = AppTreeWidget()  # the default tree still has the hover tint
    report.check(
        "::item:hover" in view.styleSheet(),
        "ordinary trees keep the hover tint",
    )
    view.deleteLater()

    from ui.review_config import ReviewConfigView

    page = ReviewConfigView(cfg)
    page.resize(1440, 900)
    page.show()
    for _ in range(10):
        app.processEvents()

    tree = page._field_tree
    rows = list(page._iter_rows())
    report.check(len(rows) > 5, "the field rows are built", f"rows={len(rows)}")
    report.check(
        "::item:hover" not in tree.styleSheet(),
        "the rules table has no hover band rule",
    )
    selected, hovered = rows[-1], rows[0]
    if selected is hovered:
        report.check(False, "two distinct rows to compare")
        return report.finish()
    page._select_row(selected)
    chosen = page._sel_key
    for _ in range(4):
        app.processEvents()

    # Hover the other row's text and both of its dropdowns.
    for target in (
        tree.viewport(),
        page._cell_combo(hovered, 1),
        page._cell_combo(hovered, 2),
    ):
        if target is tree.viewport():
            point = tree.visualItemRect(hovered).center()
        else:
            point = target.rect().center()
        QTest.mouseMove(target, pos=point)
        for _ in range(4):
            app.processEvents()

    report.check(
        page._sel_key == chosen,
        "hovering a row never retargets the Response pane",
        f"chosen={page._sel_key!r}",
    )
    report.check(
        list(tree.selectedItems()) == [selected],
        "only the clicked row is selected after hovering another",
    )

    # Pixel check: the hovered band must not be painted in the hover tint.
    image = tree.grab().toImage()
    hover_rect = tree.visualItemRect(hovered)
    selected_rect = tree.visualItemRect(selected)
    hover_color = _rgb(SURFACE_SUBTLE)
    selected_color = _rgb(SECONDARY_CONTAINER)

    def _band_pixels(rect):
        out = []
        for x in (rect.left() + 4, rect.left() + rect.width() // 2):
            y = rect.top() + rect.height() // 2
            if 0 <= x < image.width() and 0 <= y < image.height():
                c = image.pixelColor(x, y)
                out.append((c.red(), c.green(), c.blue()))
        return out

    hovered_pixels = _band_pixels(hover_rect)
    selected_pixels = _band_pixels(selected_rect)
    report.check(
        all(pixel != hover_color for pixel in hovered_pixels),
        "the hovered row carries no SURFACE_SUBTLE band",
        f"pixels={hovered_pixels}",
    )
    report.check(
        bool(selected_pixels) and any(pixel == selected_color for pixel in selected_pixels),
        "the clicked row still wears the selected face",
        f"pixels={selected_pixels}",
    )

    # A click on the hovered row *does* retarget it.
    QTest.mouseClick(
        tree.viewport(), Qt.MouseButton.LeftButton, pos=tree.visualItemRect(hovered).center()
    )
    for _ in range(4):
        app.processEvents()
    report.check(page._sel_key != chosen, "a click chooses the row under the pointer")

    path = save_artifact(page, "review_selection_1440.png")
    print(f"  [note] screenshot: {path.name}")
    page.deleteLater()
    for _ in range(2):
        app.processEvents()
    return report.finish()


if __name__ == "__main__":
    sys.exit(main())
