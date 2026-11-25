"""Golden screenshot infrastructure (dv-ufu.1).

Agents generate candidate images; only the human blesses them into
``baseline/`` with ``uv run poe golden-update``. The default suite never
runs these tests: goldens need the native Windows platform (offscreen Qt
renders substitute glyphs) and an environment pinned in ``baseline.meta``.
"""

from __future__ import annotations

import json
import platform
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops

GOLDEN_DIR = Path(__file__).resolve().parent
BASELINE_DIR = GOLDEN_DIR / "baseline"
CANDIDATE_DIR = GOLDEN_DIR / "candidates"
META_PATH = GOLDEN_DIR / "baseline.meta"

# Per-image overrides: name -> (max % pixels over tolerance, max channel delta)
TOLERANCES: dict[str, tuple[float, int]] = {}
DEFAULT_TOLERANCE = (0.5, 12)
MAX_CHANNEL_DELTA = 64


@dataclass
class GoldenSession:
    app: Any
    window: Any
    config: Any
    workspace: Path


def golden_boot(workspace: Path) -> GoldenSession:
    """Build a window against a throwaway workspace, never the user's.

    A shared workspace carries saved table-layout state, which reordered the
    dashboard columns between two supposedly identical golden runs. Probes
    already follow this rule; goldens need it even more because a byte-level
    diff turns any saved preference into a false failure.
    """
    import os
    import sys

    from PySide6.QtWidgets import QApplication

    from curation.config import Config
    from ui.main_window import MainWindow
    from ui.theme import apply_theme

    # Qt 6 ships no fonts; point it at the platform fonts before QApplication
    # exists, or the diff measures substitute glyphs instead of the app.
    if not os.environ.get("QT_QPA_FONTDIR"):
        candidates = (
            [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")]
            if sys.platform.startswith("win")
            else (["/usr/share/fonts", "/usr/local/fonts"] if sys.platform != "darwin" else [])
        )
        for candidate in candidates:
            if os.path.isdir(candidate):
                os.environ["QT_QPA_FONTDIR"] = candidate
                break

    app = QApplication.instance() or QApplication([])
    apply_theme(app)  # type: ignore[arg-type]
    config = Config()
    config.app.workspace = workspace
    window = MainWindow(config)
    window.show()
    for _ in range(10):
        app.processEvents()
    return GoldenSession(app, window, config, workspace)


@dataclass(frozen=True)
class Diff:
    changed_percent: float
    max_delta: int
    bbox: tuple[int, int, int, int] | None

    def fails(self, name: str) -> bool:
        percent, _channel = TOLERANCES.get(name, DEFAULT_TOLERANCE)
        return self.changed_percent > percent or self.max_delta > MAX_CHANNEL_DELTA


def environment() -> dict[str, str]:
    import PySide6
    from PySide6 import QtCore

    return {
        "python": sys.version.split()[0],
        "pyside6": PySide6.__version__,
        "qt": QtCore.qVersion(),
        "platform": platform.platform(),
        "qt_qpa_platform": "windows",
    }


def check_environment() -> None:
    """Fail loudly when the rendering environment differs from the baseline."""
    if not META_PATH.exists():
        raise AssertionError(
            f"no {META_PATH}: run `uv run poe golden-update` on Windows to bless baselines"
        )
    expected = json.loads(META_PATH.read_text(encoding="utf-8"))
    import os

    current = environment()
    current["qt_qpa_platform"] = os.environ.get("QT_QPA_PLATFORM", "")
    if os.environ.get("QT_QPA_PLATFORM", "").lower() != "windows":
        raise AssertionError(
            "goldens need QT_QPA_PLATFORM=windows (offscreen renders substitute glyphs)"
        )
    mismatches = {
        key: (expected.get(key), value)
        for key, value in current.items()
        if expected.get(key) != value
    }
    assert not mismatches, f"golden environment drift: {mismatches}"


def write_meta() -> None:
    META_PATH.write_text(
        json.dumps(environment(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def capture(widget: Any, name: str) -> Path:
    """Render `widget` to the candidate folder and return the PNG path."""
    from PySide6.QtWidgets import QApplication

    CANDIDATE_DIR.mkdir(parents=True, exist_ok=True)
    widget.show()
    for _ in range(3):
        QApplication.processEvents()
    path = CANDIDATE_DIR / f"{name}.png"
    assert widget.grab().save(str(path)), f"could not capture {name}"
    return path


def bless(name: str) -> Path:
    """Human-only: promote one candidate into the baseline folder."""
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    candidate = CANDIDATE_DIR / f"{name}.png"
    assert candidate.exists(), f"no candidate for {name}; run the golden first"
    target = BASELINE_DIR / f"{name}.png"
    target.write_bytes(candidate.read_bytes())
    return target


def compare(baseline: Path, candidate: Path) -> Diff:
    with Image.open(baseline) as expected, Image.open(candidate) as actual:
        left = expected.convert("RGB")
        right = actual.convert("RGB")
        if left.size != right.size:
            return Diff(100.0, 255, (0, 0, *left.size))
        difference = ImageChops.difference(left, right)
        bbox = difference.getbbox()
        raw = difference.tobytes()
        deltas = [max(raw[i], raw[i + 1], raw[i + 2]) for i in range(0, len(raw), 3)]
        worst = max(deltas, default=0)
        changed = sum(1 for value in deltas if value > 12)
        percent = changed * 100.0 / (left.size[0] * left.size[1])
        return Diff(percent, worst, bbox)
