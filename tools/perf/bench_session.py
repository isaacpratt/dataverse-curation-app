"""Measure the phases of an app session: startup, views, dashboard, dataset.

Run with: uv run python tools/perf/bench_session.py
Offscreen, throwaway workspace, no network. Each phase is timed 2-3 times.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "probes"))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from _common import boot  # noqa: E402

app, cfg = boot()
from PySide6.QtWidgets import QWidget  # noqa: E402

from ui.main_window import MainWindow  # noqa: E402


def timed(label: str, fn, n: int = 3) -> None:
    out = []
    for _ in range(n):
        t = time.perf_counter()
        fn()
        out.append(time.perf_counter() - t)
    print(f"{label:38} {min(out):6.3f}s  (runs: {', '.join(f'{v:.3f}' for v in out)})")


print("=== startup ===")
win = MainWindow(cfg)
win.resize(1280, 860)
timed("MainWindow construction", lambda: MainWindow(cfg), n=2)
win.show()
timed("first show + processEvents", lambda: [app.processEvents() for _ in range(6)], n=2)

print("\n=== views ===")
for label, fn in (
    ("open Settings", lambda: win._ensure_settings()),
    ("open About", lambda: win._ensure_about()),
    ("open Help", lambda: win._ensure_help()),
    ("open Log", lambda: win._show_pane("log")),
    ("open Review Config", lambda: win._show_review_config()),
):
    try:
        timed(label, fn, n=2)
    except Exception as exc:
        print(f"{label:38} ERROR {exc}")

print("\n=== dashboard ===")
dash = win._dashboard
rows = [
    {
        "title": f"Dataset {i}",
        "persistent_id": f"doi:10.5072/FK2/{i}",
        "state": "DRAFT",
        "date_created": "2026-01-01",
        "file_count": 3,
        "total_size_bytes": 1024,
    }
    for i in range(500)
]


def load_filter():
    dash._all_datasets = rows
    dash._filter_edit.setText("")
    dash._apply_filter()
    app.processEvents()


timed("dashboard 500 rows filter+paint", load_filter)
print("widgets under window:", len([win, *win.findChildren(QWidget)]))

print("\n=== dataset detail ===")
for label, fn in (
    ("open dataset detail", lambda: win._open_dataset("doi:10.5072/FK2/BENCH", "Benchmark")),
    ("detail settle (timers)", lambda: [app.processEvents() for _ in range(20)]),
):
    timed(label, fn, n=2)

print("\n=== theme switch ===")
from ui import theme  # noqa: E402

for target in ("dark", "light"):
    timed(
        f"switch to {target}",
        lambda t=target: (
            theme.set_active_theme(t),
            theme.apply_theme(app, t, retheme=True),
        ),
        n=2,
    )

print("\n=== imports ===")
import subprocess  # noqa: E402

for mod in ("main", "ui.main_window", "ui.theme", "ui.widgets", "engine.runner"):
    out = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import time; t=time.perf_counter(); import {mod}; print(time.perf_counter()-t)",
        ],
        capture_output=True,
        text=True,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
    )
    print(f"  import {mod:20} {out.stdout.strip()[:12]}s")

win.close()
