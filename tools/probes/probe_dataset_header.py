"""Probe: measure the dataset header's geometry (dv-gfx baseline).

Offscreen, against a throwaway workspace. Prints the current top-bar height,
page-canvas height, action-row width, Run checks geometry, rail width and
per-step widths at 960, 1280 and 1440. This is the before/after instrument
for the header-revamp implementation beads; it makes no claims about a
particular design.

Run: python tools/probes/probe_dataset_header.py
"""

from __future__ import annotations

import sys

from _common import Report, boot, save_artifact


def _metadata():
    return {
        "id": 1,
        "versionNumber": 1,
        "latestVersion": {
            "metadataBlocks": {
                "citation": {
                    "fields": [
                        {"typeName": "title", "value": "A curation study"},
                        {
                            "typeName": "depositor",
                            "value": "Ada Lovelace",
                        },
                    ]
                }
            }
        },
    }


def main() -> int:
    app, cfg = boot()
    from PySide6.QtWidgets import QWidget

    from ui.dataset import DatasetDetailView

    report = Report("dataset header budget")
    view = DatasetDetailView(
        cfg,
        "doi:10.5072/FK2/HEADER",
        "Header budget",
        cached_metadata=_metadata(),
        cached_inventory=[],
    )
    view.show()
    for _ in range(8):
        app.processEvents()

    top = next(w for w in view.findChildren(QWidget) if w.objectName() == "DetailTopBar")
    rows = top.layout().count()
    report.check(rows >= 1, "the fixed top bar carries the rail", f"rows={rows}")

    # The rail is the first band: under the nav bar, above the chips (dv-gfx.4).
    rail = view._rail
    badge = view._status_pill
    report.check(
        rail.mapTo(view, rail.rect().topLeft()).y()
        <= badge.mapTo(view, badge.rect().topLeft()).y(),
        "the rail sits above the header chips",
        f"rail_y={rail.mapTo(view, rail.rect().topLeft()).y()} chip_y={badge.mapTo(view, badge.rect().topLeft()).y()}",
    )

    widths = (960, 1280, 1440)
    for width in widths:
        view.resize(width, 900)
        for _ in range(8):
            app.processEvents()
        steps = [rail.buttons[key] for key in rail.buttons]
        action_width = max(
            btn.width() for btn in (view._dl_btn, view._record_btn, view._load_meta_btn)
        )
        print(
            f"  [note] {width}: top_bar={top.height()}px canvas={view._canvas.height()}px "
            f"action_row={action_width}px run_checks="
            f"{view._check_btn.width()}x{view._check_btn.height()} "
            f"rail={rail.width()}px steps={[b.width() for b in steps]}"
        )
        report.check(
            view._check_btn.height() >= 32,
            f"the primary action clears the hit-target floor at {width}",
            f"height={view._check_btn.height()}",
        )
        report.check(rail.width() > 0, f"the rail is laid out at {width}")
        path = save_artifact(view, f"header_baseline_{width}.png")
        print(f"  [note] screenshot: {path.name}")

    # Scrolling the column under the rail gives it a shadow (dv-gfx.15).
    bar = view._scroll.verticalScrollBar()
    bar.setValue(bar.maximum())
    for _ in range(4):
        app.processEvents()
    report.check(
        view._rail.graphicsEffect() is not None,
        "the rail is shaded once the column scrolls under it",
        "effect=None" if view._rail.graphicsEffect() is None else "shadow",
    )

    # The rail is the first band, so the header is a little taller than the
    # 200px budget it had when the rail sat at the bottom of the stack.
    report.check(
        top.height() <= 220,
        "the header does not blow past its measured budget",
        f"top={top.height()}px",
    )
    view.deleteLater()
    for _ in range(2):
        app.processEvents()
    return report.finish()


if __name__ == "__main__":
    sys.exit(main())
