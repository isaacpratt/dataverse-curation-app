"""Probe: the file manifest's columns fit, persist and reset.

Three contracts in one place:
* the content fit gives every column a real width (Name keeps a floor);
* a user's column width survives a refresh (the app's own fit must not
  overwrite the saved layout);
* the reset button puts the columns back to the fitted defaults and
  clears the saved layout.

Run: python tools/probes/probe_manifest_columns.py
"""

from __future__ import annotations

import json
import sys

from _common import Report, boot


def main() -> int:
    app, cfg = boot()
    from curation.storage import _table_layout_path
    from ui import dataset_detail as dd

    # The view fetches the dataset's metadata on a timer; the probe only
    # looks at columns, so the fetch is stubbed out (no network).
    dd.DatasetDetailView._on_load_metadata = lambda self: None

    report = Report("file manifest columns")
    view = dd.DatasetDetailView(cfg, "doi:10.5072/FK2/PROBE", "Probe dataset")
    view.resize(1100, 900)
    view.show()
    for _ in range(10):
        app.processEvents()

    view._all_file_rows = [
        (f"folder{i % 3}/file_{i:02d}.csv", 1024 * i, "text/csv", "") for i in range(40)
    ]
    view._apply_file_filter_internal()
    for _ in range(8):
        app.processEvents()

    tree = view._file_tree
    hdr = tree.header()
    widths = [hdr.sectionSize(i) for i in range(hdr.count())]
    print(f"  fitted widths: {widths}")
    report.check(
        all(w > 0 for w in widths),
        "every column has a width",
        f"widths={widths}",
    )
    report.check(
        widths[0] >= 260,
        "the Name column keeps its 260px floor",
        f"width={widths[0]}",
    )

    # The user drags a column edge.
    hdr.resizeSection(1, 220)
    for _ in range(4):
        app.processEvents()
    user_width = hdr.sectionSize(1)
    report.check(user_width == 220, "the user's width was applied", f"width={user_width}")

    # A refresh must not overwrite it (the app's fit is not a user edit).
    view._apply_file_filter_internal()
    for _ in range(8):
        app.processEvents()
    report.check(
        hdr.sectionSize(1) == 220,
        "the user's width survives a refresh",
        f"width={hdr.sectionSize(1)}",
    )

    path = _table_layout_path(cfg.app.workspace)
    state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    report.check(
        "dataset_files" in state and state["dataset_files"].get("v") == 1,
        "the saved layout carries the schema version",
        f"entry={state.get('dataset_files')}",
    )

    # The reset button puts the fitted defaults back.
    view._file_reset_btn.click()
    for _ in range(8):
        app.processEvents()
    report.check(
        hdr.sectionSize(1) != 220,
        "the reset restored the fitted width",
        f"width={hdr.sectionSize(1)}",
    )
    state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    report.check(
        "dataset_files" not in state,
        "the reset cleared the saved layout",
        f"keys={list(state)}",
    )

    view.close()
    return report.finish()


if __name__ == "__main__":
    sys.exit(main())
