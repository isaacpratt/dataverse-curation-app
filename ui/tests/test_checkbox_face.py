"""The check box face: a rounded square with the Lucide check (dv-7mf).

The kit used to draw a 16px indicator with a half-height radius (8px) and an
accent fill when checked - a solid blue circle, the visual language of a
radio button, with no check mark anywhere. These tests read rendered pixels
at 2x, which is where a 4px corner and a half-height radius differ.
"""

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication, QCheckBox

from ui.widgets import AppCheckBox


def _render(box: AppCheckBox, scale: int = 2) -> QImage:
    """Render a widget on a card-coloured image at ``scale`` device pixels."""
    from ui.theme import SURFACE_CARD

    box.adjustSize()
    box.show()
    QApplication.processEvents()
    try:
        image = QImage(
            max(1, box.width()) * scale,
            max(1, box.height()) * scale,
            QImage.Format.Format_ARGB32,
        )
        image.setDevicePixelRatio(float(scale))
        image.fill(QColor(SURFACE_CARD))
        painter = QPainter(image)
        try:
            # The image carries the device pixel ratio, so the painter already
            # works in logical pixels: no extra transform here.
            box.render(painter, QPoint(0, 0))
        finally:
            painter.end()
        return image
    finally:
        box.hide()


def _pixel(image: QImage, x: int, y: int):
    return image.pixelColor(x, y)


def _indicator_bounds(box: AppCheckBox, image: QImage) -> tuple[int, int, int]:
    """The indicator rect in image pixels (the render scale applied)."""
    rect = box.indicatorRect()
    ratio = image.devicePixelRatio() or 1.0
    left = int(round(rect.left() * ratio))
    top = int(round(rect.top() * ratio))
    size = max(1, int(round(rect.width() * ratio)))
    return left, top, size


def _near(a, b, tolerance: int = 24) -> bool:
    return (
        abs(a.red() - b.red()) <= tolerance
        and abs(a.green() - b.green()) <= tolerance
        and abs(a.blue() - b.blue()) <= tolerance
    )


def test_indicator_is_a_rounded_square_not_a_circle(qapp):
    """A 4px corner fills the near-corner pixel; a half-height radius would not."""
    from ui.theme import ACCENT_PRIMARY, SURFACE_CARD
    from ui.widgets import make_checkbox

    box = make_checkbox("Required", checked=True)
    image = _render(box)
    left, top, size = _indicator_bounds(box, image)
    accent = QColor(ACCENT_PRIMARY)
    card = QColor(SURFACE_CARD)

    assert size == 32, f"a 16px indicator renders 32 device pixels at 2x, not {size}"
    # Device pixel (3, 3) is logical (1.75, 1.75): inside a 4px corner radius,
    # outside a circle of radius 8 (the old face) - the discriminating pixel.
    near_corner = _pixel(image, left + 3, top + 3)
    # Device pixel (0, 0) is logical (0.25, 0.25): outside both, because a
    # rounded square still cuts its corner. That rules out a plain square.
    outer_corner = _pixel(image, left, top)

    assert _near(near_corner, accent), (
        f"a 4px corner radius fills the near-corner pixel; got {near_corner.name()}"
    )
    assert _near(outer_corner, card, tolerance=60), (
        f"the corner is rounded, so the outermost pixel is the card; "
        f"got {outer_corner.name()} (a plain square paints it accent)"
    )


def test_checked_indicator_carries_a_light_glyph(qapp):
    """A checked indicator is an accent field with light glyph pixels on it."""
    from ui.theme import ACCENT_PRIMARY, SURFACE_CARD
    from ui.widgets import make_checkbox

    checked = make_checkbox("Include the guestbook response", checked=True)
    unchecked = make_checkbox("Include the guestbook response")
    checked_image = _render(checked)
    unchecked_image = _render(unchecked)
    accent = QColor(ACCENT_PRIMARY)

    def counts(image: QImage, box: AppCheckBox) -> tuple[int, int]:
        left, top, size = _indicator_bounds(box, image)
        inset = 4
        accent_px = light_px = 0
        for x in range(left + inset, left + size - inset):
            for y in range(top + inset, top + size - inset):
                pixel = _pixel(image, x, y)
                if _near(pixel, accent, tolerance=40):
                    accent_px += 1
                elif pixel.lightness() > 200:
                    light_px += 1
        return accent_px, light_px

    checked_accent, checked_light = counts(checked_image, checked)
    unchecked_accent, _ = counts(unchecked_image, unchecked)

    assert checked_accent > 0, "a checked box is filled with the accent"
    assert checked_light > 0, "a checked box draws the Lucide check in ON_PRIMARY over that fill"
    assert unchecked_accent == 0, "an unchecked box is never accent-filled"
    # The unchecked centre is the card face: no glyph to find.
    left, top, size = _indicator_bounds(unchecked, unchecked_image)
    centre = _pixel(unchecked_image, left + size // 2, top + size // 2)
    assert _near(centre, QColor(SURFACE_CARD), tolerance=8)


def test_indicator_keeps_its_box_in_every_state(qapp):
    """16x16 in both states, so the label never moves between states."""
    from ui.widgets import make_checkbox

    off = make_checkbox("Include the guestbook response")
    on = make_checkbox("Include the guestbook response", checked=True)
    off.adjustSize()
    on.adjustSize()

    assert off.indicatorRect().size() == on.indicatorRect().size()
    assert off.indicatorRect().width() == 16
    assert off.indicatorRect().height() == 16
    assert off.sizeHint() == on.sizeHint(), "the label baseline moves between states"


def test_disabled_checked_box_is_muted(qapp):
    """A disabled check is grey, never the live accent, and says so in the label."""
    from ui.theme import ACCENT_PRIMARY, TEXT_DISABLED
    from ui.widgets import make_checkbox

    box = make_checkbox("A disabled option that is on", checked=True)
    box.setEnabled(False)
    image = _render(box)
    left, top, size = _indicator_bounds(box, image)
    accent = QColor(ACCENT_PRIMARY)

    for x in range(left, left + size):
        for y in range(top, top + size):
            assert not _near(_pixel(image, x, y), accent, tolerance=24), (
                "a disabled check must not wear the live accent colour"
            )
    assert TEXT_DISABLED in box.styleSheet(), "disabled text keeps the disabled role"


def test_the_kit_owns_the_three_faces(qapp):
    """Unchecked, checked and disabled are three distinct, documented faces."""
    from ui.theme import (
        ACCENT_PRIMARY,
        BORDER_CONTROL,
        BORDER_SUBTLE,
        ON_PRIMARY,
        SURFACE_CARD,
        SURFACE_SUBTLE,
    )
    from ui.widgets import AppCheckBox, make_checkbox

    off_face, off_edge, _ = AppCheckBox.face_colours(enabled=True, checked=False)
    on_face, on_edge, on_glyph = AppCheckBox.face_colours(enabled=True, checked=True)
    off_face_disabled, off_edge_disabled, _ = AppCheckBox.face_colours(enabled=False, checked=False)

    assert (off_face, off_edge) == (SURFACE_CARD, BORDER_CONTROL)
    assert (on_face, on_edge) == (ACCENT_PRIMARY, ACCENT_PRIMARY)
    assert (off_face_disabled, off_edge_disabled) == (SURFACE_SUBTLE, BORDER_SUBTLE)
    assert on_glyph == ON_PRIMARY

    box = make_checkbox("Required")
    assert isinstance(box, AppCheckBox) and isinstance(box, QCheckBox)
    assert box.isCheckable() and not box.isChecked()
    assert box.indicatorRect().width() == AppCheckBox.INDICATOR_PX
