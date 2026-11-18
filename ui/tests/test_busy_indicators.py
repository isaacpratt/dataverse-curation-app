"""Busy/progress indicators: one vocabulary (dv-o58).

The kit owns the two components and their names: ``make_progress_bar``
(a thin determinate bar) and ``RingProgress`` (re-exported from the kit).
No view may construct a raw QProgressBar or import ui.ring directly —
these scans fail the build if a view starts hand-rolling one.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_ALLOWED = {
    "ui/widgets.py",  # the kit's make_progress_bar factory
    "ui/ring.py",  # the ring's implementation (re-exported)
    "ui/theme.py",  # the app-level progress-bar QSS fallback
    "ui/gallery.py",  # the component gallery
}


def _scan(pattern: str) -> list[str]:
    rx = re.compile(pattern)
    hits: list[str] = []
    for path in (ROOT / "ui").rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith("ui/tests/"):
            continue
        if rel in _ALLOWED:
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if rx.search(line):
                hits.append(f"{rel}:{i}")
    return hits


def test_no_bare_qprogressbar_outside_the_kit():
    assert _scan(r"QProgressBar\s*\(") == []


def test_no_qprogressbar_import_outside_the_kit():
    assert _scan(r"import\s+[^\n]*QProgressBar") == []


def test_no_direct_ring_import_outside_the_kit():
    assert _scan(r"from\s+ui\.ring\s+import") == []


def test_kit_exports_both_indicators():
    import ui.widgets as widgets

    assert "make_progress_bar" in widgets.__all__
    assert "RingProgress" in widgets.__all__
    assert hasattr(widgets, "RingProgress")


def test_ring_paints_and_reports_its_variant(qapp):
    from ui.widgets import RingProgress

    ring = RingProgress(diameter=20)
    ring.setFraction(0.5)
    assert ring.objectName() == "RingProgress"
    ring.close()
