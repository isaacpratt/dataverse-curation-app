"""Review configuration: the two-pane scroll idiom (dv-beu, dv-gcn).

The left pane holds two cards — Metadata Field Rules and Content-based
Rules — with every expanded rule block visible and no inner scrollbar;
each of the two panes scrolls on its own with the scrollbar at the pane's
right edge — the dataset page's two-column idiom.
"""

from typing import Any

from PySide6.QtWidgets import QFrame, QScrollArea, QSplitter


def _rc(win: Any):
    win._show_review_config()
    return win._review_config


def test_both_splitter_panes_are_noframe_scroll_areas(win):
    rc = _rc(win)
    splitter = next(iter(rc.findChildren(QSplitter)), None)
    assert splitter is not None, "the page must use a QSplitter"
    assert splitter.count() == 2
    for i in range(2):
        pane = splitter.widget(i)
        assert isinstance(pane, QScrollArea), "each pane scrolls on its own"
        assert pane.frameShape() == QFrame.Shape.NoFrame


def test_checks_tree_is_sized_to_its_content(win):
    rc = _rc(win)
    tree = rc._field_tree
    # Content-fit: the expanded tree needs no inner scrollbar.
    assert tree.verticalScrollBar().maximum() == 0
    assert tree.height() > 0


def _card_of(widget: Any):
    node = widget
    while node is not None and node.objectName() != "Card":
        node = node.parentWidget()
    return node


def test_the_two_rule_cards_are_siblings_in_the_left_pane(win):
    """The field table and the content rules no longer share a card."""
    rc = _rc(win)
    field_card = _card_of(rc._field_tree)
    content_card = _card_of(rc._content_list)
    assert field_card is not None
    assert content_card is not None
    assert field_card is not content_card, "two cards, not one card with a divider"
    host = field_card.parentWidget()
    assert host is content_card.parentWidget(), "both cards live in the pane's host"
    order = [host.layout().itemAt(i).widget() for i in range(host.layout().count())]
    assert order.index(field_card) < order.index(content_card), (
        "Metadata Field Rules comes before Content-based Rules"
    )
