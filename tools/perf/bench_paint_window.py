"""Benchmark: the queue's painting window at 25k rows (bead dv-fjr).

The queue paints into a ``QTableWidget``: one heap item per cell, so a
collection of 25k rows is 300k items rebuilt on every filter
keystroke. The dashboard therefore caps the *painted* rows - the filter
and the sort still cover the full set - and the status line says how
many rows the cap hides.

The cap was a safe default, not a measured optimum. This harness
measures it: it builds a synthetic collection, paints it under several
caps, and times the three operations a curator feels - the filter, the
keystroke that narrows it, and the sort.

Run::

    uv run python tools/perf/bench_paint_window.py
    uv run python tools/perf/bench_paint_window.py --rows 25000 --caps 2000 5000 10000 25000
    uv run python tools/perf/bench_paint_window.py --markdown   # for the docs

Nothing here touches the network or the user's workspace: the config
has no token and the workspace is a throwaway directory.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import statistics
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_ROWS = 25_000
DEFAULT_CAPS = (2_000, 5_000, 10_000, 25_000)
REPEATS = 5


def _synthetic_rows(count: int) -> list[dict]:
    """Build a synthetic collection: the fields the queue reads, filled out."""
    states = ("DRAFT", "RELEASED", "IN REVIEW", "DEACCESSIONED")
    labels = ("", "", "Needs review", "Approved", "Hold for internal review")
    rows = []
    for i in range(count):
        rows.append(
            {
                "title": f"Dataset {i:06d} - a synthetic collection record",
                "persistent_id": f"doi:10.5072/FK2/SYN{i:06d}",
                "contact": f"Researcher {i % 997:03d}",
                "depositor": f"Department {i % 41:02d}",
                "date_created": "2026-01-15 10:30:00",
                "date_published": "2026-02-20 09:00:00",
                "collection": f"collection-{i % 7}",
                "file_count": (i % 53) + 1,
                "total_size_bytes": (i % 900) * 1_048_576,
                "state": states[i % len(states)],
                "curation_label": labels[i % len(labels)],
                "downloaded_at": "2026-03-01 12:00:00",
            }
        )
    return rows


def _boot():
    """Boot an offscreen app, a throwaway workspace and a dashboard view."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from curation.config import Config
    from ui.dashboard import DashboardView
    from ui.theme import apply_theme

    apply_theme(app)
    cfg = Config()
    cfg.dataverse.api_token = ""
    cfg.app.workspace = pathlib.Path(tempfile.mkdtemp(prefix="bench_ws_"))
    dash = DashboardView(cfg)
    dash.resize(1280, 800)
    dash.show()
    app.processEvents()
    return app, dash


def _time(callable_, repeats: int = REPEATS) -> float:
    """Median seconds of `repeats` runs (the first run is a warm-up)."""
    samples = []
    for index in range(repeats + 1):
        start = time.perf_counter()
        callable_()
        elapsed = time.perf_counter() - start
        if index:  # the first run warms caches and imports
            samples.append(elapsed)
    return statistics.median(samples)


def _measure(app, dash, rows: list[dict], cap: int) -> dict[str, float]:
    """Time the filter, two keystrokes and a sort under one painting cap."""
    from PySide6.QtCore import Qt

    from ui.dashboard import DashboardView

    DashboardView._MAX_PAINTED_ROWS = cap
    dash._all_datasets = rows
    dash._filter_edit.setText("")

    # Warm-up: the first paint populates caches the measured runs reuse.
    dash._apply_filter()
    app.processEvents()

    filter_seconds = _time(lambda: (dash._apply_filter(), app.processEvents()))

    def keystroke(term: str) -> None:
        dash._filter_edit.setText(term)
        dash._apply_filter()
        app.processEvents()

    # The first keystroke of a search still matches everything - that is
    # the worst case a curator types, and the one the cap has to answer.
    keystroke_wide = _time(lambda: keystroke("Dataset"))
    # A specific term: few rows match, so the repaint is cheap.
    keystroke_narrow = _time(lambda: keystroke("Dataset 012"))

    dash._filter_edit.setText("")
    dash._apply_filter()
    app.processEvents()

    def sort() -> None:
        dash._table.sortItems(0, Qt.SortOrder.AscendingOrder)
        app.processEvents()

    sort_seconds = _time(sort)

    return {
        "filter": filter_seconds,
        "keystroke": keystroke_wide,
        "keystroke_narrow": keystroke_narrow,
        "sort": sort_seconds,
        "painted": float(min(cap, len(rows))),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS)
    parser.add_argument(
        "--caps",
        type=int,
        nargs="+",
        default=list(DEFAULT_CAPS),
        help="painting caps to measure",
    )
    parser.add_argument("--markdown", action="store_true", help="print a markdown table")
    args = parser.parse_args(argv)

    app, dash = _boot()
    rows = _synthetic_rows(args.rows)
    results = []
    for cap in [*list(args.caps), 0]:
        result = _measure(app, dash, rows, cap)
        results.append((cap, result))
        if not args.markdown:
            print(
                f"cap {cap:>6}: filter {result['filter']:.3f}s  "
                f"keystroke {result['keystroke']:.3f}s  "
                f"keystroke (narrow) {result['keystroke_narrow']:.3f}s  "
                f"sort {result['sort']:.3f}s"
            )

    if args.markdown:
        print(
            "| painted rows | filter + paint | keystroke (all rows) | keystroke (few rows) | sort |"
        )
        print("| --- | --- | --- | --- | --- |")
        for cap, result in results:
            label = f"{int(result['painted']):,}" if cap else "0 (scan only)"
            print(
                f"| {label} | {result['filter']:.3f} s | {result['keystroke']:.3f} s | "
                f"{result['keystroke_narrow']:.3f} s | {result['sort']:.3f} s |"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
