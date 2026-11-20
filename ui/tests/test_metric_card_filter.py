"""Dashboard metric cards: hover affordance, no tooltip, whole-chip click (dv-1k4)."""

from typing import Any

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QLabel


def _mval(card: Any):
    # The value label carries its theme token as its object name
    # (DisplayLG / StateMD), so it is found by type, not by a fixed name.
    labels = [
        lbl for lbl in card.findChildren(QLabel) if lbl.objectName() in ("DisplayLG", "StateMD")
    ]
    return labels[0].text() if labels else None


def test_metric_cards_carry_no_tooltip(win):
    dash = win._dashboard
    for card in dash._metric_cards:
        assert card.toolTip() == "", "the card is a control, not a tooltip target"


def test_metric_card_children_are_mouse_transparent(win):
    """Presses on the icon/caption/value must reach the card's eventFilter."""
    dash = win._dashboard
    for card in dash._metric_cards:
        for child in card.findChildren(QLabel):
            assert child.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents), (
                f"{child.text()!r} would swallow the click"
            )


def _labelled_rows() -> Any:
    return [
        {"title": "a", "persistent_id": "p1", "state": "RELEASED", "curation_label": "In Review"},
        {"title": "b", "persistent_id": "p2", "state": "DRAFT"},
        {"title": "c", "persistent_id": "p3", "state": "DRAFT", "curation_label": "Needs Fix"},
    ]


def test_in_progress_card_counts_and_filters_any_label(win, monkeypatch):
    dash = win._dashboard
    dash._all_datasets = _labelled_rows()
    monkeypatch.setattr(dash, "_crawled", True)
    monkeypatch.setattr(dash, "_worker", None)
    dash._update_metrics()
    assert [_mval(c) for c in dash._metric_cards][2] == "2"
    try:
        dash._on_metric_clicked("progress")
        assert dash._state_filter.currentIndex() == 0, (
            "In Progress leaves the combo on All Datasets"
        )
        assert dash._labelled_only is True
        assert {d["persistent_id"] for d in dash._datasets} == {"p1", "p3"}
    finally:
        dash._labelled_only = False
        dash._state_filter.setCurrentIndex(0)
        dash._apply_filter()


def test_in_progress_never_calls_the_decided_cache(win, monkeypatch):
    """The In Progress card/filter must not consult _decided_ids at all."""
    dash = win._dashboard

    def _boom(ws):
        raise AssertionError("_decided_ids must not be called by the count or the filter")

    monkeypatch.setattr("ui.dashboard._decided_ids", _boom)
    monkeypatch.setattr(dash, "_decided_cache", None)
    dash._all_datasets = _labelled_rows()
    monkeypatch.setattr(dash, "_crawled", True)
    monkeypatch.setattr(dash, "_worker", None)
    dash._update_metrics()
    try:
        dash._on_metric_clicked("progress")
        dash._apply_filter()
        assert {d["persistent_id"] for d in dash._datasets} == {"p1", "p3"}
    finally:
        dash._labelled_only = False
        dash._state_filter.setCurrentIndex(0)
        dash._apply_filter()
    # restore the shared window's real cache for later tests
    monkeypatch.undo()


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
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    handled = dash.eventFilter(card, press)
    assert handled is True
    assert {d["persistent_id"] for d in dash._datasets} == {"p1", "p2"}


def test_theme_paints_a_metric_card_hover_state():
    from ui.theme import global_qss

    qss = global_qss()
    assert "#MetricCard:hover" in qss, "hover must signal the filter (dv-1k4)"
    hover = qss.split("#MetricCard:hover", 1)[1].split("}", 1)[0]
    assert "background" in hover
    assert "border" in hover


def test_caption_label_is_elided_not_truncated(win):
    """Guard the caption still elides (its tooltip is gone with the card's)."""
    dash = win._dashboard
    card = dash._metric_cards[0]
    captions = [lbl for lbl in card.findChildren(QLabel) if lbl.text().startswith("PENDING")]
    assert captions, "caption label missing"
