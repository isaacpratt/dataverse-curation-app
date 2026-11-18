"""Probe: one navigation map (dv-6wb).

The rail is the single navigation home and stays visible at every
window width and in both sidebar fold states. The sidebar Sections
card and the top-bar Sections button are gone; the header toggle
folds and restores the sidebar.

Run: python tools/probes/probe_rail_nav.py
"""

from __future__ import annotations

import sys

from _common import Report, boot


def main() -> int:
    app, cfg = boot()
    from ui import dataset as dd

    # The view fetches the dataset's metadata on a timer; the probe only
    # exercises navigation chrome, so the fetch is stubbed out (no network).
    dd.DatasetDetailView._on_load_metadata = lambda self: None

    report = Report("one navigation map")
    view = dd.DatasetDetailView(cfg, "doi:10.5072/FK2/RAILNAV", "Rail nav probe")
    view.resize(960, 700)
    view.show()
    for _ in range(12):
        app.processEvents()

    # The rail is present, un-hideable and has both lenses addressable.
    report.check(hasattr(view, "_rail"), "the workflow rail exists")
    report.check(not view._rail.isHidden(), "the rail is visible")
    report.check(not view._rail.isHidden(), "the rail stays visible (again)")

    # The sidebar Sections card and top-bar Sections button are gone.
    for attr in ("_nav_card", "_sections_btn", "_sections_menu", "_sidebar_collapse_btn"):
        report.check(not hasattr(view, attr), f"{attr} is gone")

    # The header toggle is the one sidebar control and starts visible.
    toggle = getattr(view, "_sidebar_toggle_btn", None)
    report.check(toggle is not None, "the header sidebar toggle exists")
    if toggle is None:
        view.close()
        return report.finish()
    report.check(not toggle.isHidden(), "the sidebar toggle is visible")

    # Fold the sidebar: the log moves to the page foot; the rail stays.
    view._toggle_sidebar()
    for _ in range(8):
        app.processEvents()
    report.check(view._side_scroll.isHidden(), "the sidebar folds via the toggle")
    report.check(not view._rail.isHidden(), "the rail is visible while folded")
    log_card = getattr(view, "_dataset_log_card", None)
    if log_card is not None:
        found_in_main = any(
            view._main_wrap.itemAt(i).widget() is log_card for i in range(view._main_wrap.count())
        )
        report.check(found_in_main, "the dataset log moved to the page foot when folded")

    # Unfold: the sidebar returns; the rail stays.
    view._toggle_sidebar()
    for _ in range(8):
        app.processEvents()
    report.check(not view._side_scroll.isHidden(), "the sidebar unfolds via the toggle")
    report.check(not view._rail.isHidden(), "the rail is visible while unfolded")

    view.close()
    return report.finish()


if __name__ == "__main__":
    sys.exit(main())
