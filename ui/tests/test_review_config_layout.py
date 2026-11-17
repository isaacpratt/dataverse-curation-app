"""Review configuration: the two-pane scroll idiom (dv-beu).

The Checks card shows every expanded rule block with no inner scrollbar,
and each of the two panes scrolls on its own with the scrollbar at the
pane's right edge — the dataset page's two-column idiom.
"""

from PySide6.QtWidgets import QFrame, QScrollArea, QSplitter


def _rc(win):
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
        assert pane.frameShape() == QFrame.NoFrame


def test_checks_tree_is_sized_to_its_content(win):
    rc = _rc(win)
    tree = rc._field_tree
    # Content-fit: the expanded tree needs no inner scrollbar.
    assert tree.verticalScrollBar().maximum() == 0
    assert tree.height() > 0


def test_text_rules_section_is_below_the_tree(win):
    rc = _rc(win)
    tree = rc._field_tree
    scroll_content = tree.parentWidget()
    assert scroll_content is not None, "tree must live in the scroll pane's content widget"
    layout = scroll_content.layout()
    assert layout is not None
    order = [layout.itemAt(i).widget() for i in range(layout.count())]
    rules_section = rc._content_list.parentWidget()
    assert order.index(tree) < order.index(rules_section), (
        "Text Rules must sit below the tree, not beside it"
    )
