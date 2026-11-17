"""One row-selection / focus face across every table and tree (dv-0kq, dv-coj).

Guards:
- the shared header band has no vertical dividers between sections;
- every App* view paints the same selection tint, from one theme mixin;
- the tree's branch gutter does not paint a blue stripe beside the row;
- Qt's dotted per-item focus rectangle is suppressed by the shared delegate.
"""

from PySide6.QtWidgets import QStyle, QStyleOptionViewItem


def test_header_band_has_no_vertical_dividers():
    from ui.theme import header_section_qss

    qss = header_section_qss()
    assert "border-bottom" in qss, "the header keeps its bottom rule"
    assert "border-right" not in qss, "no vertical bar between sections (dv-0kq)"
    # Nor on the hover/pressed faces.
    for state in ("section:hover", "section:pressed"):
        block = qss.split(state, 1)[1].split("}", 1)[0]
        assert "border-right" not in block, f"{state} draws a divider"


def test_selection_mixin_is_the_single_source():
    from ui.theme import global_qss, selection_qss
    from ui.widgets import flush_table_style, tree_style

    mixin = selection_qss("QTableWidget")
    assert "::item:selected" in mixin
    assert "::item:hover" in mixin
    assert mixin in global_qss(), "app sheet uses the mixin"
    assert selection_qss("QTreeView") in tree_style()
    assert mixin in flush_table_style()


def test_tree_paints_its_own_branch_chevron(qapp):
    """The native Windows 11 branch chip (blue chevron) must not be used."""
    from ui.widgets import AppTree, AppTreeWidget, _BranchPainting

    for cls in (AppTree, AppTreeWidget):
        assert issubclass(cls, _BranchPainting), (
            f"{cls.__name__} would fall back to the native branch chip (dv-coj)"
        )
        assert cls.drawBranches is _BranchPainting.drawBranches


def test_branch_qss_is_gone_from_the_tree_sheet():
    """Regression: QSS branch rules did not stop the native chip at all."""
    from ui import icons
    from ui.widgets import tree_style

    assert not hasattr(icons, "tree_branch_qss")
    assert "QTreeView::branch" not in tree_style()


def test_selection_selector_has_no_descendant_space():
    """`QTreeView ::item` selects child widgets — the rules were dead."""
    from ui.theme import selection_qss

    qss = selection_qss("QTreeView")
    assert "QTreeView::item:selected" in qss
    assert "QTreeView ::item" not in qss


def test_every_app_view_uses_the_shared_delegate(qapp):
    from ui.widgets import AppTable, AppTree, AppTreeWidget, SelectionDelegate

    table = AppTable(["A", "B"])
    tree = AppTree()
    tree_widget = AppTreeWidget()
    for view in (table, tree, tree_widget):
        assert isinstance(view.itemDelegate(), SelectionDelegate), (
            f"{type(view).__name__} must paint through SelectionDelegate"
        )


def test_delegate_drops_the_dotted_focus_rect(qapp, monkeypatch):
    """The base paint never sees State_HasFocus, so no PE_FrameFocusRect."""
    from PySide6.QtGui import QPainter, QPixmap
    from PySide6.QtWidgets import QStyledItemDelegate

    from ui.widgets import AppTable, SelectionDelegate

    table = AppTable(["A", "B"])
    table.resize(320, 120)
    delegate = SelectionDelegate(table)
    seen: list[QStyleOptionViewItem] = []
    original = QStyledItemDelegate.paint

    def spy(self, painter, option, index):
        seen.append(QStyleOptionViewItem(option))
        return original(self, painter, option, index)

    monkeypatch.setattr(QStyledItemDelegate, "paint", spy)
    option = QStyleOptionViewItem()
    option.state = QStyle.StateFlag.State_Selected | QStyle.StateFlag.State_HasFocus
    option.rect = table.rect()
    pixmap = QPixmap(table.size())
    painter = QPainter(pixmap)
    try:
        delegate.paint(painter, option, table.model().index(0, 0))
    finally:
        painter.end()
    assert seen, "base paint ran"
    assert not (seen[0].state & QStyle.StateFlag.State_HasFocus), (
        "the dotted focus rect would still be drawn"
    )
    assert seen[0].state & QStyle.StateFlag.State_Selected, "the row stays selected"


def test_active_versus_inactive_selection_keeps_the_tint():
    from ui.theme import SECONDARY_CONTAINER, selection_qss

    assert "!active" in selection_qss("QTableWidget")
    assert SECONDARY_CONTAINER in selection_qss("QTableWidget")
    # Guard against the old per-face colours creeping back in the mixin.
    assert "selection-background-color" not in selection_qss()
