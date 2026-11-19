"""Probe: every rules-table row has one shape (dv-7zv).

Builds the real Review configuration page on a temp workspace and checks
the rules table's geometry at two window sizes: three columns in Field |
Level | Check order with no header band, both dropdowns 32px high and
vertically centred in their 40px row (4px above, 4px below), every row the
same height, and no horizontal scrollbar at 1440x900 or 960x720. It also
saves a screenshot of each size to eyeball.

Run: python tools/probes/probe_review_table.py
"""

from __future__ import annotations

import sys

from _common import Report, boot, save_artifact


def _pump(app, rounds: int = 10) -> None:
    for _ in range(rounds):
        app.processEvents()


def _rows(view):
    return list(view._iter_rows())


def _combo(view, item, column):
    return view._cell_combo(item, column)


def main() -> int:
    app, cfg = boot()
    from ui.review_config import _CELL_V_MARGIN

    view = None
    report = Report("review rules table")
    try:
        from curation.config import Config  # noqa: F401 - imported by boot already
        from ui.review_config import ReviewConfigView

        view = ReviewConfigView(cfg)
        view.resize(1000, 900)
        view.show()
        _pump(app)
        view.refresh_for_dataverse()
        _pump(app)

        tree = view._field_tree
        report.check(tree.columnCount() == 3, "the table has three columns")
        report.check(tree.isHeaderHidden(), "the header band is not painted")
        report.check(
            [tree.headerItem().text(i) for i in range(3)] == ["Field", "Level", "Check"],
            "the columns are Field, Level, Check",
        )
        report.check(
            not hasattr(view, "_fields_reset_btn") and not hasattr(view, "_fields_layout"),
            "no reset control and no saved column layout",
        )

        rows = _rows(view)
        report.check(len(rows) > 10, "the field rows are built", f"rows={len(rows)}")

        bad_gap, bad_height, missing = [], [], []
        for item in rows:
            for column in (1, 2):
                host = tree.itemWidget(item, column)
                combo = _combo(view, item, column)
                if host is None or combo is None:
                    missing.append((tree.indexOfTopLevelItem(item), column))
                    continue
                if combo.height() != 32:
                    bad_height.append(combo.height())
                above = combo.geometry().top()
                below = host.height() - (combo.geometry().top() + combo.height())
                if above != _CELL_V_MARGIN or below != _CELL_V_MARGIN:
                    bad_gap.append((above, below))
        report.check(not missing, "every row carries both dropdowns", f"missing={missing[:4]}")
        report.check(
            not bad_height, "every dropdown is 32px high", f"heights={sorted(set(bad_height))}"
        )
        report.check(
            not bad_gap,
            "every dropdown sits 4px above and 4px below its row cell",
            f"gaps={sorted(set(bad_gap))[:4]}",
        )

        heights = {tree.visualItemRect(item).height() for item in rows if not item.isHidden()}
        report.check(heights == {40}, "every row is 40px tall", f"heights={sorted(heights)}")

        # No dropdown elides its own text: the column is measured from the
        # widest item plus the themed chrome, not from the current one.
        elided = []
        for item in rows:
            for column in (1, 2):
                combo = _combo(view, item, column)
                if combo is not None and combo.width() < combo.sizeHint().width():
                    elided.append((combo.currentText(), combo.width(), combo.sizeHint().width()))
        report.check(
            not elided,
            "no dropdown elides its text",
            f"first={elided[:3]}",
        )

        bad_scroll = {}
        for width, height in ((1440, 900), (960, 720)):
            view.resize(width, height)
            _pump(app, 12)
            maximum = tree.horizontalScrollBar().maximum()
            if maximum:
                bad_scroll[f"{width}x{height}"] = maximum
            report.check(
                maximum == 0,
                f"no horizontal scrollbar at {width}x{height}",
                f"need={maximum}px",
            )
            header = tree.header()
            report.check(
                sum(header.sectionSize(i) for i in range(3)) <= tree.viewport().width(),
                f"the columns fit the viewport at {width}x{height}",
            )
            path = save_artifact(view, f"review_table_{width}x{height}.png")
            print(f"  [note] screenshot: {path}")
    finally:
        if view is not None:
            view.deleteLater()
            _pump(app, 2)
    return report.finish()


if __name__ == "__main__":
    sys.exit(main())
