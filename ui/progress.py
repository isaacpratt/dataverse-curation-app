"""Pure progress math for the crawl ring (no Qt — unit-testable anywhere).

Kept separate from the widget so the motion and the phase arithmetic can
be tested without an offscreen Qt platform.
"""

__all__ = [
    "ease_step",
    "PHASE_SPANS",
    "PHASE_DISCOVERY",
    "PHASE_ENRICHMENT",
    "PHASE_LOCKS",
    "PHASE_LABELS",
    "phase_fraction",
]

# Fraction of the remaining gap closed per tick (100 ms). 0.3 closes a
# full gap in ~1 s while still showing motion for single increments.
_EASE_RATE = 0.3

# Minimum visible movement per tick, so a 0→1 change on a 1000-step
# pipeline still animates instead of jumping.
_MIN_STEP = 0.002


def ease_step(displayed: float, target: float) -> float:
    """One easing step toward `target`.

    Never overshoots: the result is clamped to the target and never moves
    backwards (a lower target is a reset, not a regression to animate).
    """
    try:
        d = float(displayed)
        t = float(target)
    except (TypeError, ValueError):
        return 0.0
    d = max(0.0, min(1.0, d))
    t = max(0.0, min(1.0, t))
    if t <= d:
        return t
    gap = t - d
    step = gap * _EASE_RATE
    if step < _MIN_STEP:
        step = _MIN_STEP
    if step > gap:
        step = gap
    return min(1.0, d + step)


# Crawl phases, in order. Each phase owns a slice of the 0..1 range; a
# skipped phase jumps straight to the next one's floor.
PHASE_DISCOVERY = "discovery"
PHASE_ENRICHMENT = "enrichment"
PHASE_LOCKS = "locks"
PHASE_LABELS = "labels"

# phase -> (floor, ceiling) of the overall fraction.
PHASE_SPANS: dict[str, tuple[float, float]] = {
    PHASE_DISCOVERY: (0.00, 0.30),
    PHASE_ENRICHMENT: (0.30, 0.75),
    PHASE_LOCKS: (0.75, 0.90),
    PHASE_LABELS: (0.90, 1.00),
}


def phase_fraction(phase: str, done: int = 0, total: int = 0) -> float:
    """Overall fraction for a phase's own progress.

    `done`/`total` are the phase's item counts. An unknown or empty
    total holds the phase floor (the phase is entered but its extent is
    not yet known) so the ring never jumps ahead of reality. A finished
    phase returns its ceiling, which is how skipped phases are handled:
    the caller reports the next phase instead.
    """
    try:
        floor, ceiling = PHASE_SPANS.get(phase, (0.0, 1.0))
    except Exception:
        floor, ceiling = 0.0, 1.0
    try:
        d = max(0, int(done))
        t = int(total)
    except (TypeError, ValueError):
        d, t = 0, 0
    if t <= 0:
        return floor
    ratio = d / t
    if ratio < 0.0:
        ratio = 0.0
    elif ratio > 1.0:
        ratio = 1.0
    return floor + (ceiling - floor) * ratio
