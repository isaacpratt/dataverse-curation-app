"""Circular progress ring for long-running background work.

Qt has no native circular progress, so this is a small custom widget:
a track ring, a determinate arc, and a centred percentage. Three
behaviours make it honest about a slow or bursty pipeline:

- **Catch-up** — the displayed value eases toward the reported target on
  a 100 ms tick, so bursty arrivals (batch flushes, pooled completions)
  glide instead of teleporting. The displayed value never overshoots the
  target and never regresses except on an explicit reset.
- **Backoff** — when no update arrives for a while and the work is not
  finished, the ring switches to a slow sweep so a stalled network call
  never looks frozen. The next update resumes determinately.
- **Unknown total** — a `None` fraction means the total is not known
  yet (e.g. before the first search page reveals it); the ring shows an
  indeterminate sweep rather than a fake percentage.

Colours come from `ui.theme` tokens only (the theme-token test forbids
hex literals outside theme.py).
"""

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ui.i18n import t
from ui.progress import ease_step
from ui.theme import (
    ERROR,
    ON_SURFACE,
    OUTLINE_VARIANT,
    PRIMARY,
    SUCCESS,
)

__all__ = ["RingProgress", "ease_step"]

# No update for this long while incomplete → switch to the slow sweep.
_STALL_MS = 1500

# Tick interval for the easing animation.
_TICK_MS = 100

# Sweep speed (degrees per second) for indeterminate / stalled states.
_SWEEP_DEG_PER_S = 90.0


class RingProgress(QWidget):
    """Circular progress indicator with catch-up, backoff and error state."""

    def __init__(self, parent: QWidget | None = None, diameter: int = 40) -> None:
        super().__init__(parent)
        self.setObjectName("RingProgress")
        self.setFixedSize(diameter, diameter)
        self.setAccessibleName(t("ring.name"))
        self._diameter = diameter
        self._target: float | None = None
        self._displayed = 0.0
        self._error = False
        self._complete = False
        self._last_update_ms = 0
        self._sweep_deg = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._on_tick)

    # -- public API ---------------------------------------------------------

    def setFraction(self, fraction: float | None) -> None:
        """Report progress.

        `fraction` in [0, 1]; `None` means "total unknown" (indeterminate).
        Out-of-range values are clamped.
        """
        try:
            if fraction is None:
                self._target = None
            else:
                value = float(fraction)
                if value < 0.0:
                    value = 0.0
                if value > 1.0:
                    value = 1.0
                self._target = value
                self._complete = value >= 1.0
        except (TypeError, ValueError):
            self._target = None
        self._error = False
        self._last_update_ms = self._now_ms()
        if not self._timer.isActive():
            self._timer.start()
        self.update()

    def setError(self) -> None:
        """Mark the operation as failed (ring turns red, stops advancing)."""
        self._error = True
        self._complete = False
        self._last_update_ms = self._now_ms()
        self.update()

    def reset(self) -> None:
        """Clear all state for a new operation."""
        self._target = None
        self._displayed = 0.0
        self._error = False
        self._complete = False
        self._sweep_deg = 0.0
        self._last_update_ms = 0
        self._timer.stop()
        self.update()

    def isComplete(self) -> bool:
        return self._complete

    def displayedFraction(self) -> float:
        return self._displayed

    # -- internals ----------------------------------------------------------

    @staticmethod
    def _now_ms() -> int:
        from time import monotonic

        return int(monotonic() * 1000)

    def _on_tick(self) -> None:
        target = self._target
        if target is None:
            # Indeterminate: keep the sweep moving.
            self._sweep_deg = (self._sweep_deg + _SWEEP_DEG_PER_S * _TICK_MS / 1000.0) % 360.0
            self.update()
            return
        if self._displayed < target:
            self._displayed = ease_step(self._displayed, target)
        if self._displayed >= 1.0 and self._complete:
            self._timer.stop()
        self.update()

    def _is_stalled(self) -> bool:
        """Report whether no update arrived recently and work is unfinished."""
        if self._complete or self._error:
            return False
        if self._target is None:
            # Unknown total: the sweep already communicates activity.
            return False
        if not self._last_update_ms:
            return False
        return (self._now_ms() - self._last_update_ms) >= _STALL_MS

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        try:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing, True)
            inset = 3.0
            side = self._diameter - inset * 2
            rect = QRectF(inset, inset, side, side)
            width = max(2.0, self._diameter * 0.11)
            pen = QPen(QColor(OUTLINE_VARIANT), width)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.drawArc(rect, 0, 360 * 16)

            if self._error:
                pen = QPen(QColor(ERROR), width)
                pen.setCapStyle(Qt.RoundCap)
                painter.setPen(pen)
                painter.drawArc(rect, 0, 360 * 16)
                self._paint_label(painter, "!")
                painter.end()
                return

            if self._complete:
                pen = QPen(QColor(SUCCESS), width)
                pen.setCapStyle(Qt.RoundCap)
                painter.setPen(pen)
                painter.drawArc(rect, 0, 360 * 16)
                self._paint_label(painter, "✓")
                painter.end()
                return

            if self._target is None or self._is_stalled():
                # Indeterminate sweep (unknown total or stalled work).
                pen = QPen(QColor(PRIMARY), width)
                pen.setCapStyle(Qt.RoundCap)
                painter.setPen(pen)
                start = int(self._sweep_deg * 16)
                painter.drawArc(rect, start, 110 * 16)
                if self._target is None:
                    self._paint_label(painter, "")
                painter.end()
                return

            fraction = max(0.0, min(1.0, self._displayed))
            pen = QPen(QColor(PRIMARY), width)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.drawArc(rect, 90 * 16, int(-360 * 16 * fraction))
            self._paint_label(painter, f"{int(round(fraction * 100))}")
            painter.end()
        except Exception:
            pass

    def _paint_label(self, painter: QPainter, text: str) -> None:
        if not text:
            return
        try:
            from PySide6.QtGui import QFont

            font = QFont(self.font())
            font.setPointSizeF(max(6.0, self._diameter * 0.22))
            font.setBold(True)
            painter.setFont(font)
            color = SUCCESS if text == "✓" else (ERROR if text == "!" else ON_SURFACE)
            painter.setPen(QColor(color))
            painter.drawText(self.rect(), Qt.AlignCenter, text)
        except Exception:
            pass

    def accessibleDescription(self) -> str:
        if self._error:
            return t("ring.failed")
        if self._complete:
            return t("ring.complete")
        if self._target is None:
            return t("ring.unknown")
        try:
            return t(
                "ring.percent",
                percent=int(round(self._displayed * 100)),
            )
        except Exception:
            return t("ring.running")

    def _paint_state(self) -> str:
        """Test/debug helper: one word describing the current state."""
        if self._error:
            return "error"
        if self._complete:
            return "complete"
        if self._target is None:
            return "unknown"
        if self._is_stalled():
            return "stalled"
        return "running"
