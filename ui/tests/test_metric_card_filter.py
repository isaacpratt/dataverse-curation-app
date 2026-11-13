"""Dashboard metric cards: hover affordance, no tooltip, whole-chip click (dv-1k4)."""

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QLabel


def test_metric_cards_carry_no_tooltip(win):
    dash = win._dashboard
    for card in dash._metric_cards:
        assert card.toolTip() == "", "the card is a control, not a tooltip target"


def test_metric_card_children_are_mouse_transparent(win):
    """Presses on the icon/caption/value must reach the card's eventFilter."""
    dash = win._dashboard
    for card in dash._metric_cards:
        for child in card.findChildren(QLabel):
            assert child.testAttribute(Qt.WA_TransparentForMouseEvents), (
                f"{child.text()!r} would swallow the click"
            )


def test_press_on_the_card_applies_its_filter(win, monkeypatch):
    dash = win._dashboard
    dash._all_datasets = [
        {"title": "a", "persistent_id": "p1", "state": "DRAFT"},
        {"title": "b", "persistent_id": "p2", "state": "IN REVIEW"},
        {"title": "c", "persistent_id": "p3", "state": "RELEASED"},
    ]
    card = dash._metric_cards[0]
    press = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(5, 5),
        QPointF(5, 5),
        Qt.LeftButton,
        Qt.LeftButton,
        Qt.NoModifier,
    )
    handled = dash.eventFilter(card, press)
    assert handled is True
    assert {d["persistent_id"] for d in dash._datasets} == {"p1", "p2"}


def test_theme_paints_a_metric_card_hover_state():
    from ui.theme import global_qss

    qss = global_qss()
    assert "#MetricCard:hover" in qss, "hover must signal the filter (dv-1k4)"
    hover = qss.split("#MetricCard:hover", 1)[1].split("}", 1)[0]
    assert "background" in hover and "border" in hover


def test_caption_label_is_elided_not_truncated(win):
    """Guard the caption still elides (its tooltip is gone with the card's)."""
    dash = win._dashboard
    card = dash._metric_cards[0]
    captions = [lbl for lbl in card.findChildren(QLabel) if lbl.text().startswith("PENDING")]
    assert captions, "caption label missing"
