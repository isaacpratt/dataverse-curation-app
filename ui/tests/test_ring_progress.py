"""Progress ring + phase arithmetic (W-09/W-12).

Pure math (ease_step, phase_fraction) is tested without Qt; the widget
tests use the session's offscreen qapp fixture.
"""

import os
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from ui.progress import (
    PHASE_DISCOVERY,
    PHASE_ENRICHMENT,
    PHASE_LABELS,
    PHASE_LOCKS,
    ease_step,
    phase_fraction,
)  # isort: skip

# -- pure math -----------------------------------------------------------


def test_ease_step_moves_toward_target():
    assert ease_step(0.0, 1.0) == pytest.approx(0.3)
    assert ease_step(0.5, 1.0) == pytest.approx(0.65)


def test_ease_step_never_overshoots():
    out = ease_step(0.99, 1.0)
    assert out <= 1.0
    assert out > 0.99


def test_ease_step_converges():
    value = 0.0
    for _ in range(200):
        value = ease_step(value, 1.0)
    assert value == pytest.approx(1.0, abs=1e-6)


def test_ease_step_never_regresses_on_higher_target():
    assert ease_step(0.7, 0.9) > 0.7
    # A lower target is a reset, not a regression to animate.
    assert ease_step(0.7, 0.2) == pytest.approx(0.2)


def test_ease_step_clamps_inputs():
    # A negative displayed value clamps to 0 first, then eases 30% of 0.5.
    assert ease_step(-5.0, 0.5) == pytest.approx(0.15)
    # A target above 1 clamps to 1.
    assert ease_step(0.5, 5.0) == pytest.approx(0.65)
    # A non-numeric input is tolerated: ease_step returns 0.0 instead of
    # raising (the defensive path the widget relies on).
    not_a_number: Any = "x"
    assert ease_step(not_a_number, 1.0) == 0.0


def test_phase_fraction_spans():
    assert phase_fraction(PHASE_DISCOVERY, 0, 10) == pytest.approx(0.0)
    assert phase_fraction(PHASE_DISCOVERY, 10, 10) == pytest.approx(0.30)
    assert phase_fraction(PHASE_ENRICHMENT, 0, 10) == pytest.approx(0.30)
    assert phase_fraction(PHASE_ENRICHMENT, 10, 10) == pytest.approx(0.75)
    assert phase_fraction(PHASE_LOCKS, 5, 10) == pytest.approx(0.825)
    assert phase_fraction(PHASE_LABELS, 1, 1) == pytest.approx(1.0)


def test_phase_fraction_unknown_total_holds_floor():
    assert phase_fraction(PHASE_ENRICHMENT, 0, 0) == pytest.approx(0.30)
    assert phase_fraction(PHASE_ENRICHMENT, 5, 0) == pytest.approx(0.30)
    assert phase_fraction(PHASE_LOCKS, 0, -1) == pytest.approx(0.75)


def test_phase_fraction_monotonic_across_phases():
    values = [
        phase_fraction(PHASE_DISCOVERY, 5, 10),
        phase_fraction(PHASE_DISCOVERY, 10, 10),
        phase_fraction(PHASE_ENRICHMENT, 0, 10),
        phase_fraction(PHASE_ENRICHMENT, 10, 10),
        phase_fraction(PHASE_LOCKS, 0, 10),
        phase_fraction(PHASE_LOCKS, 10, 10),
        phase_fraction(PHASE_LABELS, 0, 10),
        phase_fraction(PHASE_LABELS, 10, 10),
    ]
    assert values == sorted(values)


def test_phase_fraction_clamps_ratio():
    assert phase_fraction(PHASE_DISCOVERY, 99, 10) == pytest.approx(0.30)
    assert phase_fraction(PHASE_DISCOVERY, -5, 10) == pytest.approx(0.0)


# -- widget --------------------------------------------------------------


def test_ring_clamps_and_reports(qapp):
    from ui.ring import RingProgress

    ring = RingProgress(diameter=20)
    ring.setFraction(0.5)
    assert ring.displayedFraction() <= 0.5
    ring.setFraction(5.0)
    assert ring.displayedFraction() <= 1.0
    ring.setFraction(-1.0)
    assert ring.displayedFraction() >= 0.0


def test_ring_states(qapp):
    from ui.ring import RingProgress

    ring = RingProgress(diameter=20)
    assert ring._paint_state() == "unknown"
    ring.setFraction(0.4)
    assert ring._paint_state() == "running"
    ring.setFraction(1.0)
    assert ring._paint_state() == "complete"
    assert ring.isComplete() is True
    ring.setError()
    assert ring._paint_state() == "error"
    assert "fail" in ring.accessibleDescription().lower()
    ring.reset()
    assert ring._paint_state() == "unknown"
    assert ring.displayedFraction() == 0.0
    assert ring.isComplete() is False


def test_ring_paints_without_raising(qapp):
    from ui.ring import RingProgress

    ring = RingProgress(diameter=20)
    ring.setFraction(0.42)
    ring.repaint()  # must not raise
    ring.setFraction(None)
    ring.repaint()
    ring.setError()
    ring.repaint()


def test_ring_unknown_total_is_indeterminate(qapp):
    from ui.ring import RingProgress

    ring = RingProgress(diameter=20)
    ring.setFraction(None)
    assert ring._target is None
    assert ring._paint_state() == "unknown"
    assert "unknown" in ring.accessibleDescription().lower()
