"""Probe: the dashboard queue columns fill the viewport and never clip.

Covers the three ways the queue used to break: a dragged column edge, a
moved column, and a resized window. The invariant is the same in every
case: the visible column widths add up to the viewport width (the queue
has no horizontal scrollbar), so nothing is cut off and the right-hand
label stays inside its column.

Run: python tools/probes/probe_queue_columns.py
"""

from __future__ import annotations

import sys

from _common import Report, boot


def visible_total(header) -> int:
    return sum(
        header.sectionSize(i) for i in range(header.count()) if not header.isSectionHidden(i)
    )


def last_visible_logical(header) -> int:
    last = -1
    for v in range(header.count()):
        logical = header.logicalIndex(v)
        if not header.isSectionHidden(logical):
            last = logical
    return last


def main() -> int:
    app, cfg = boot()
    from ui.main_window import MainWindow

    report = Report("dashboard queue columns")
    win = MainWindow(cfg)
    win.resize(1200, 800)
    win.show()
    for _ in range(10):
        app.processEvents()

    dash = win._dashboard
    table = dash._table
    hdr = table.horizontalHeader()

    def check_fit(tag: str) -> None:
        for _ in range(8):
            app.processEvents()
        vw = table.viewport().width()
        total = visible_total(hdr)
        report.check(
            total == vw,
            f"{tag}: visible columns fill the viewport",
            f"total={total} viewport={vw}",
        )
        report.check(
            total <= vw,
            f"{tag}: nothing is clipped",
            f"total={total} viewport={vw}",
        )
        last = last_visible_logical(hdr)
        report.check(
            hdr.sectionSize(last) > 0,
            f"{tag}: the last visible column has width",
            f"width={hdr.sectionSize(last)}",
        )

    check_fit("initial")

    # The user drags a column edge.
    hdr.resizeSection(0, hdr.sectionSize(0) + 50)
    check_fit("after a column drag")

    # The user moves a column.
    hdr.moveSection(0, 3)
    check_fit("after a column move")

    # The window gets narrower: the columns scale down instead of clipping.
    win.resize(900, 800)
    for _ in range(10):
        app.processEvents()
    check_fit("after a window resize")

    # And wider again: the pre-scale widths come back.
    win.resize(1300, 800)
    for _ in range(10):
        app.processEvents()
    check_fit("after widening the window")

    win.close()
    return report.finish()


if __name__ == "__main__":
    sys.exit(main())
