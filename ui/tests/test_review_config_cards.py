"""Review configuration: two titled cards in the left pane (dv-gcn).

The field table and the text-search rules used to share one "Checks" card
with a divider and an in-card heading. They are now sibling cards —
Metadata Field Rules and Content-based Rules — with their own titles,
(i) tips and summaries; the tools row follows the field card's name.
"""

from PySide6.QtWidgets import QFrame, QLabel


def _card_of(widget):
    node = widget
    while node is not None and node.objectName() != "Card":
        node = node.parentWidget()
    return node


def _titles(rc):
    return [label.text() for label in rc.findChildren(QLabel, "CardTitle")]


def test_two_sibling_cards_in_the_field_rules_order(win):
    win._show_review_config()
    rc = win._review_config
    left = rc._field_tree.parentWidget()
    while left is not None and left.objectName() != "ReviewConfigView":
        parent = left.parentWidget()
        if parent is not None and parent.objectName() == "Card":
            left = parent.parentWidget()
            break
        left = parent
    cards = [c for c in (rc.findChildren(QFrame, "Card")) if c.parentWidget() is left]
    assert len(cards) >= 2, "the left pane holds two cards"
    titles = [label.text() for card in cards for label in card.findChildren(QLabel, "CardTitle")]
    assert titles[:2] == ["Metadata Field Rules", "Content-based Rules"], titles
    assert _card_of(rc._field_tree) is cards[0]
    assert _card_of(rc._content_list) is cards[1]


def test_no_divider_or_retired_copy(win):
    win._show_review_config()
    rc = win._review_config
    assert not list(rc.findChildren(QFrame, "ReviewSectionDivider"))
    texts = [label.text() for label in rc.findChildren(QLabel)]
    assert "Checks" not in texts
    assert not [text for text in texts if text.startswith("Text rules")]


def test_both_cards_carry_an_info_tip_and_the_field_tools_are_renamed(win):
    win._show_review_config()
    rc = win._review_config
    field_card = _card_of(rc._field_tree)
    content_card = _card_of(rc._content_list)
    from PySide6.QtWidgets import QToolButton

    for card in (field_card, content_card):
        assert any(button.objectName() == "InfoTip" for button in card.findChildren(QToolButton)), (
            f"{card.objectName()} needs an (i) tip"
        )
    from PySide6.QtWidgets import QWidget

    tools = [w for w in rc.findChildren(QWidget) if w.objectName() == "FieldRulesTools"]
    assert len(tools) == 1
    assert not [w for w in rc.findChildren(QWidget) if w.objectName() == "ChecksTools"]


def test_the_content_summary_counts_the_rules(win):
    win._show_review_config()
    rc = win._review_config
    rules = [r for r in rc._current_ruleset().get("content_rules") or [] if isinstance(r, dict)]
    assert rc._content_summary.text() == f"{len(rules)} rule(s)"
    assert rc._content_summary.parentWidget() is not None
