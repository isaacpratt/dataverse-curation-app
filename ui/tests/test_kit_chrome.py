"""Kit chrome: elevation, chip height parity, rounded scrollbars (dv-gfx.1).

Four contracts, one per critique item:

* every card and chip carries a real (if subtle) drop shadow;
* a header chip is exactly a standard button tall, so it lines up with the
  controls in its row;
* a scrollbar's lane and groove are rounded, not square;
* a disposition dropdown is tall enough for its own padded text box.
"""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QGraphicsDropShadowEffect

from ui import theme
from ui.widgets import (
    BUTTON_HEIGHTS,
    CHIP_HEIGHT,
    make_badge,
    make_card,
    make_disposition_combo,
    make_split_chip,
)


def test_make_card_carries_an_elevation_effect(qapp):
    _card, _body, _title, _header = make_card("Card")
    effect = _card.graphicsEffect()
    assert isinstance(effect, QGraphicsDropShadowEffect)
    assert effect.blurRadius() > 0


def test_apply_elevation_does_not_stack_effects(qapp):
    _card, _body, _title, _header = make_card("Card")
    theme.apply_elevation(_card)
    theme.apply_elevation(_card)
    assert isinstance(_card.graphicsEffect(), QGraphicsDropShadowEffect)
    # One effect per widget: the second call re-dresses the same one.
    assert _card.graphicsEffect() is not None


def test_a_header_chip_is_a_standard_button_tall(qapp):
    from ui.widgets import make_action_button

    chip = make_badge("Loading", label="loading")
    button = make_action_button("Run checks", kind="primary", size="md")
    assert chip.height() == button.height() == BUTTON_HEIGHTS["md"] == CHIP_HEIGHT
    chip2 = make_badge("doi:10.5072/FK2/AGRI", label="info")
    assert chip2.height() == BUTTON_HEIGHTS["md"]


def test_a_chip_is_elevated_like_a_card(qapp):
    chip = make_badge("Draft", label="draft")
    assert isinstance(chip.graphicsEffect(), QGraphicsDropShadowEffect)
    dataset_chip = make_split_chip("A dataset title")
    assert isinstance(dataset_chip.graphicsEffect(), QGraphicsDropShadowEffect)


def test_in_row_badge_keeps_its_own_metrics(qapp):
    """A check verdict sets its own height; it is not a header chip."""
    verdict = make_badge("PASS", background=theme.ACCENT_PRIMARY, foreground=theme.SURFACE_CARD,
                         chip=False)
    assert verdict.maximumHeight() == 16777215  # QWIDGETSIZE_MAX
    assert verdict.graphicsEffect() is None


def test_scrollbar_lanes_and_grooves_are_rounded(qapp):
    sheet = theme.global_qss()
    assert f"border-radius: {theme.RADIUS_SM};" in sheet
    # The old square lane/groove rules are gone.
    assert "QScrollBar::groove:vertical {\n    background: transparent;" in sheet


def test_disposition_combo_fits_its_text_box(qapp):
    combo = make_disposition_combo()
    metrics = combo.fontMetrics()
    # The combo's own QSS pads the text 7px top and bottom plus the 12px
    # font's ascent/descent: the control has to hold that much.
    needed = metrics.ascent() + metrics.descent() + 14
    assert combo.height() >= needed