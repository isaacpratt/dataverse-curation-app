"""Probe: a table card's bottom-right corner stays connected.

A filled scrollbar lane paints the page colour over the card's rounded
corner, so the card border used to end in a white notch. The lanes are
transparent now; this probe reads the pixels at the corner and checks
that the card's border curve is unbroken.

Run: python tools/probes/probe_card_corner.py
"""

from __future__ import annotations

import sys

from _common import Report, boot


def card_of(widget):
    """Find the nearest ancestor frame named Card (the table's card)."""
    frame = widget.parentWidget()
    while frame is not None and frame.objectName() != "Card":
        frame = frame.parentWidget()
    return frame


def main() -> int:
    app, cfg = boot()
    from ui.main_window import MainWindow

    report = Report("table card corner")
    win = MainWindow(cfg)
    win.resize(1200, 800)
    win.show()
    for _ in range(10):
        app.processEvents()

    dash = win._dashboard
    dash._all_datasets = [
        {
            "title": f"Dataset {i}",
            "persistent_id": f"doi:10.5072/FK2/{i}",
            "state": "DRAFT",
            "date_created": "2026-01-01",
            "file_count": 3,
            "total_size_bytes": 1024,
        }
        for i in range(40)
    ]
    dash._filter_edit.setText("")
    dash._apply_filter()
    for _ in range(15):
        app.processEvents()

    table = dash._table
    frame = card_of(table)
    report.check(frame is not None, "the queue card was found")
    if frame is None:
        win.close()
        return report.finish()

    image = frame.grab().toImage()
    w, h = image.width(), image.height()
    print(f"  card image: {w}x{h}")

    # The corner patch: the border curve must not be interrupted by a
    # page-coloured notch. The page colour is #faf8ff (BACKGROUND).
    page = (0xFA, 0xF8, 0xFF)
    notch = 0
    for y in range(h - 12, h):
        for x in range(w - 12, w):
            c = image.pixelColor(x, y)
            if (
                abs(c.red() - page[0]) <= 2
                and abs(c.green() - page[1]) <= 2
                and abs(c.blue() - page[2]) <= 2
            ):
                notch += 1
    report.check(
        notch == 0,
        "the bottom-right corner has no page-coloured notch",
        f"page-coloured pixels={notch}",
    )

    frame.grab().save("queue_card.png")
    print("  saved queue_card.png")
    win.close()
    return report.finish()


if __name__ == "__main__":
    sys.exit(main())
