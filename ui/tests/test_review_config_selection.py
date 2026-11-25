"""A field row is chosen by a click, never by a hover (dv-ud0).

Two cues used to imply "this is the row being edited" without editing it:
the review tree's ``::item:hover`` band, and a selection change caused by a
pointer moving over a cell widget. Both are gone. A press on the field
name, on the padding around a dropdown, or on the dropdown itself makes
that row the one the Response pane edits; arrow keys do too.
"""

from typing import Any

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest

from ui.widgets import AppTreeWidget

_FIELD = "dateOfDeposit"


def _press_combo(rc, combo) -> None:
    """Deliver a real MouseButtonPress to the combo's routing filter.

    QTest.mouseClick would also open the popup, and the offscreen platform
    warns when a popup grabs the keyboard. The press routing is what this
    test covers, so deliver the press event straight to the filter.
    """
    point = QPointF(combo.rect().width() / 2, combo.rect().height() / 2)
    event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        point,
        point,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    rc.eventFilter(combo, event)


def _rows(rc: Any):
    return list(rc._iter_rows())


def _row(rc: Any, field: Any):
    for item in _rows(rc):
        if rc._row_data(item).get("field") == field:
            return item
    raise AssertionError(f"no row for {field}")


def _combo(rc: Any, item: Any, column: Any):
    return rc._cell_combo(item, column)


def _center_of(widget: Any, x_fraction: Any = 0.5, y_fraction: Any = 0.5):
    rect = widget.rect()
    return QPoint(
        int(rect.left() + rect.width() * x_fraction),
        int(rect.top() + rect.height() * y_fraction),
    )


def _click(view, widget, button=Qt.MouseButton.LeftButton):
    """Click a widget's centre with QTest (widget must be visible)."""
    QTest.mouseClick(widget, button, pos=_center_of(widget))


def _pump(qapp: Any, rounds: Any = 3):
    """Drain posted events; see test_review_config_table._pump for why 3."""
    for _ in range(rounds):
        qapp.processEvents()


def _show(win: Any, qapp: Any):
    win._show_review_config()
    win.resize(1440, 900)
    _pump(qapp)
    rc = win._review_config
    rc.show()
    _pump(qapp)
    return rc


def _choose(rc: Any, field: Any):
    rc._select_row(_row(rc, field))
    return rc._sel_key


def test_hover_does_not_choose_a_row(win, qapp):
    rc = _show(win, qapp)
    first = (
        _row(rc, "title")
        if any(rc._row_data(i).get("field") == "title" for i in _rows(rc))
        else _rows(rc)[0]
    )
    second = _row(rc, _FIELD)
    chosen = _choose(rc, rc._row_data(first).get("field"))
    label = rc._sel_label.text()
    before = list(rc._field_tree.selectedItems())

    for target in (
        _combo(rc, second, 1),
        _combo(rc, second, 2),
        rc._field_tree.itemWidget(second, 2),  # the transparent cell host
    ):
        QTest.mouseMove(target, pos=_center_of(target))
        _pump(qapp)
        assert rc._sel_key == chosen, "hover retargeted the Response pane"
        assert rc._sel_label.text() == label
    assert list(rc._field_tree.selectedItems()) == before, "hover changed the selection"


def test_click_on_text_or_padding_chooses_the_row(win, qapp):
    rc = _show(win, qapp)
    other = _rows(rc)[0]
    target = _row(rc, _FIELD)
    _choose(rc, rc._row_data(other).get("field"))
    viewport = rc._field_tree.viewport()

    # The field name is a tree cell; the 4px band above a combo is a child
    # widget inside the row but outside the dropdown.
    rect = rc._field_tree.visualItemRect(target)
    QTest.mouseClick(viewport, Qt.MouseButton.LeftButton, pos=rect.center())
    _pump(qapp)
    assert rc._sel_key == rc._rule_sel_key("citation", _FIELD, "nonempty")

    # The padding above the check combo is another press in the same row.
    host = rc._field_tree.itemWidget(target, 2)
    check = _combo(rc, target, 2)
    QTest.mouseClick(host, Qt.MouseButton.LeftButton, pos=_center_of(host, y_fraction=0.01))
    _pump(qapp)
    assert rc._sel_key == rc._rule_sel_key("citation", _FIELD, "nonempty")
    assert check.currentData() is not None


def test_press_on_a_dropdown_chooses_its_row_without_changing_the_value(win, qapp):
    rc = _show(win, qapp)
    target = _row(rc, _FIELD)
    other = _rows(rc)[0]
    _choose(rc, rc._row_data(other).get("field"))
    level = _combo(rc, target, 1)
    before = level.currentData()

    _press_combo(rc, level)
    _pump(qapp)
    handler = str(rc._row_data(target).get("handler") or "nonempty")
    assert rc._sel_key == rc._rule_sel_key("citation", _FIELD, handler)
    assert level.currentData() == before, "opening the popup changed the value"


def test_keyboard_navigation_follows_the_current_row(win, qapp):
    rc = _show(win, qapp)
    rows = _rows(rc)
    tree = rc._field_tree
    # _iter_rows walks a stack, so rows[-1] is the first visible field row;
    # rows[0] is the last one. Start at the top so Down has somewhere to go.
    top = rows[-1]
    rc._select_row(top)
    tree.setFocus()
    QTest.keyClick(tree, Qt.Key.Key_Down)
    _pump(qapp)
    current = tree.currentItem()
    assert current is not None
    assert current is not top, "Down moved the current row"
    data = rc._row_data(current)
    assert rc._sel_key == rc._rule_sel_key(
        str(data.get("block") or ""),
        str(data.get("field") or ""),
        str(data.get("handler") or "nonempty"),
    ), "the pane follows the keyboard's current row"
    QTest.keyClick(tree, Qt.Key.Key_Up)
    _pump(qapp)
    assert tree.currentItem() is top


def test_the_review_tree_has_no_hover_band_but_other_trees_do(win, qapp):
    rc = _show(win, qapp)
    from ui.theme import selection_qss

    assert "::item:hover" not in rc._field_tree.styleSheet()
    assert "::item:hover" in AppTreeWidget().styleSheet()  # default keeps the tint
    assert "::item:hover" in selection_qss("QTableWidget")


def test_clicking_a_check_combo_retargets_the_pane(win, qapp):
    rc = _show(win, qapp)
    target = _row(rc, _FIELD)
    other = _rows(rc)[0]
    _choose(rc, rc._row_data(other).get("field"))
    check = _combo(rc, target, 2)
    _press_combo(rc, check)
    _pump(qapp)
    assert rc._sel_key == rc._rule_sel_key("citation", _FIELD, check.currentData())
    check.hidePopup()
