"""Fractional display scaling must not be rounded before QApplication exists.

A widget with a QGraphicsDropShadowEffect is painted into an offscreen
surface; when Qt rounds a 125% scale to 100% (or 150% to 200%) that surface
is resampled and the 8px card corners and 12px text read as jagged/aliased.
`main.py` sets PassThrough at GUI startup. This source guard keeps that call
in front of app construction: a pytest-qt fixture has already created the
app by the time a test runs, so the ordering cannot be checked at runtime
here. The call is guarded on `instance() is None` because embedders (and
CLI tests) may already own an app.
"""

from pathlib import Path

_MAIN = Path(__file__).resolve().parents[2] / "main.py"


def test_fractional_scaling_is_not_rounded_before_the_app_is_created():
    src = _MAIN.read_text(encoding="utf-8")
    app_at = src.index("app = QApplication(sys.argv)")
    setup = src[:app_at]

    assert "_QGuiApplication.instance() is None" in setup
    assert "setHighDpiScaleFactorRoundingPolicy" in setup
    assert "HighDpiScaleFactorRoundingPolicy.PassThrough" in setup
    assert setup.index("instance() is None") < setup.index(
        "setHighDpiScaleFactorRoundingPolicy"
    ) < app_at
