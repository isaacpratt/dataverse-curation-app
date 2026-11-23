"""Top-nav dataset chips: full titles, centred Lucide close (dv-dvu, dv-ap7)."""

from typing import Any, cast

from PySide6.QtWidgets import QPushButton


def test_chip_label_asks_for_its_full_title(qapp):
    """The hint must not shrink to the elided text (titling ratchet, dv-dvu)."""
    from ui.widgets import _ElidedChipButton

    title = "Longitudinal Survey of Arctic Sea Ice 2008-2020"
    btn = _ElidedChipButton(title)
    btn.resize(120, 32)  # narrower than the title
    full_hint = btn.sizeHint().width()
    assert full_hint > 120, "the hint keeps asking for the full title"
    assert btn._full_text == title, "the original title is kept for widening"
    assert btn.text() == title, "an empty nav bar shows the whole title"


def test_a_chip_only_elides_once_the_bar_is_full(qapp):
    """Short titles stay whole until the nav bar is genuinely out of room (dv-gfx.19)."""
    from ui.widgets import make_split_chip, set_chip_room_limited

    chip = make_split_chip("A dataset title")
    set_chip_room_limited(chip, False)
    label = cast(Any, chip).label_half
    assert label.text() == "A dataset title"

    # Once the owner says the bar is full, the same chip is allowed to cut.
    set_chip_room_limited(chip, True)
    label.resize(60, 32)
    label._apply_elide()
    assert label.text() != "A dataset title"


def test_chip_label_half_stays_left_aligned(qapp):
    from ui.widgets import _split_chip_qss

    css = _split_chip_qss(False, "left")
    assert "text-align: left" in css


def test_chip_close_half_centres_its_icon(qapp):
    from PySide6.QtCore import QSize
    from PySide6.QtWidgets import QFrame

    from ui.widgets import _split_chip_qss, make_split_chip

    css = _split_chip_qss(False, "right")
    assert "text-align: center" in css, "the x must sit centred (dv-ap7)"

    chip = make_split_chip("A dataset", on_open=lambda: None, on_close=lambda: None)
    assert isinstance(chip, QFrame)
    buttons = chip.findChildren(QPushButton)
    close = [b for b in buttons if b.text() == ""]
    assert close, "the close half renders an icon, not a text glyph"
    btn = close[0]
    assert not btn.icon().isNull(), "the Lucide x icon must be set"
    assert btn.iconSize() == QSize(12, 12)


def test_chip_close_half_is_a_32px_square(qapp):
    from ui.widgets import make_split_chip

    chip = make_split_chip("A dataset", on_open=lambda: None, on_close=lambda: None)
    close = next(b for b in chip.findChildren(QPushButton) if b.text() == "")
    assert close.width() == 32
    assert close.height() == 32
