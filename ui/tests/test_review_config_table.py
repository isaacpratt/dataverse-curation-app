"""Review configuration: one row shape in the rules table (dv-7zv).

Every field row is 40px with two 32px dropdowns, vertically centred, in the
fixed order Field | Level | Check. The table has no header band, no reset
control and no user column sizing, and it never needs a horizontal
scrollbar — not on a 1440x900 window, not on a 960x720 one.

The dropdowns are the only way a rule's level and its check are edited, so
these tests also pin what each one writes: the Level column writes ``level``,
the Check column writes ``handler`` (seeding the ``looks_correct`` params),
and selecting a block or group heading can never turn into "the rule I am
editing".
"""

import copy

from PySide6.QtWidgets import QComboBox

LEVEL_COLUMN = 1
CHECK_COLUMN = 2


def _pump(qapp, rounds: int = 8) -> None:
    for _ in range(rounds):
        qapp.processEvents()


def _review(win, qapp, width: int = 1440, height: int = 900):
    """Show the review page at a given window size and return the view."""
    win._show_review_config()
    win.resize(width, height)
    _pump(qapp)
    rc = win._review_config
    rc._field_tree.updateGeometry()
    rc._field_tree.header().updateGeometry()
    _pump(qapp)
    return rc


def _first_row(rc):
    for item in rc._iter_rows():
        return item
    raise AssertionError("the rules table has no field row")


def _cells(rc, item):
    """(level combo, check combo) of one row, through their cell hosts."""
    return rc._cell_combo(item, LEVEL_COLUMN), rc._cell_combo(item, CHECK_COLUMN)


# -- the shape ---------------------------------------------------------------


def test_three_columns_in_field_level_check_order(win, qapp):
    rc = _review(win, qapp)
    tree = rc._field_tree
    assert tree.columnCount() == 3
    assert tree.isHeaderHidden(), "the dropdown columns label themselves (dv-7zv)"
    labels = [tree.headerItem().text(i) for i in range(3)]
    assert labels == ["Field", "Level", "Check"]


def test_no_user_column_sizing_is_left_to_reset(win, qapp):
    """Both dropdown columns are Fixed: no drag to persist, nothing to reset."""
    from PySide6.QtWidgets import QHeaderView

    rc = _review(win, qapp)
    header = rc._field_tree.header()
    assert header.sectionResizeMode(LEVEL_COLUMN) == QHeaderView.ResizeMode.Fixed
    assert header.sectionResizeMode(CHECK_COLUMN) == QHeaderView.ResizeMode.Fixed
    assert not hasattr(rc, "_fields_reset_btn")
    assert not hasattr(rc, "_fields_layout"), "no TableLayout owns this header"


def test_both_dropdowns_are_centred_in_the_row(win, qapp):
    from ui.review_config import _CELL_V_MARGIN

    rc = _review(win, qapp)
    item = _first_row(rc)
    for column in (LEVEL_COLUMN, CHECK_COLUMN):
        host = rc._field_tree.itemWidget(item, column)
        combo = rc._cell_combo(item, column)
        assert isinstance(combo, QComboBox)
        assert combo.height() == 32
        above = combo.geometry().top()
        below = host.height() - (combo.geometry().top() + combo.height())
        assert above == below == _CELL_V_MARGIN, (
            f"column {column}: {above}px above, {below}px below"
        )


def test_the_table_fits_without_a_horizontal_scrollbar(win, qapp):
    for width, height in ((1440, 900), (960, 720)):
        rc = _review(win, qapp, width, height)
        tree = rc._field_tree
        assert tree.viewport().width() > 300, "the tree was never laid out"
        bar = tree.horizontalScrollBar()
        assert bar.maximum() == 0, (
            f"at {width}x{height} the rules table needs {bar.maximum()}px of "
            "horizontal scroll: the two dropdown columns must fit in the pane"
        )
        header = tree.header()
        used = sum(header.sectionSize(i) for i in range(3))
        assert used <= tree.viewport().width(), (
            f"at {width}x{height} the columns total {used}px in a "
            f"{tree.viewport().width()}px viewport"
        )


# -- what each dropdown writes ----------------------------------------------


def _with_field_row(win, qapp, field="dateOfDeposit"):
    """Select a schema field with no rule yet (an 'unchecked' row)."""
    rc = _review(win, qapp)
    rs = rc._current_ruleset()
    snapshot = copy.deepcopy(rs.get("field_rules") or [])
    rs["field_rules"] = [
        r
        for r in snapshot
        if not (isinstance(r, dict) and r.get("block") == "citation" and r.get("field") == field)
    ]
    rc._refresh_field_table()
    for item in rc._iter_rows():
        data = rc._row_data(item)
        if data.get("block") == "citation" and data.get("field") == field:
            return rc, snapshot, item
    rs["field_rules"] = snapshot
    raise AssertionError(f"no row for citation.{field}")


def _restore(rc, snapshot):
    rc._current_ruleset()["field_rules"] = snapshot
    rc._refresh_field_table()
    rc._sel_kind, rc._sel_key = "field", ""
    rc._show_template_for_selection()
    rc._clear_dirty()


def test_a_new_row_is_unchecked_with_a_hidden_params_panel(win, qapp):
    rc, snapshot, item = _with_field_row(win, qapp)
    try:
        level, check = _cells(rc, item)
        assert level.currentData() == "unchecked"
        assert check.currentData() == "nonempty"
        assert rc._params_panel.isHidden()
    finally:
        _restore(rc, snapshot)


def test_the_level_column_writes_the_rules_level(win, qapp):
    rc, snapshot, item = _with_field_row(win, qapp)
    try:
        level, _check = _cells(rc, item)
        level.setCurrentIndex(level.findData("required"))
        rules = rc._current_ruleset().get("field_rules") or []
        rule = next(
            r for r in rules if r.get("block") == "citation" and r.get("field") == "dateOfDeposit"
        )
        assert rule["level"] == "required"
        # The row now edits a real rule, so a check change is allowed.
        assert rc._row_data(item).get("rule_kind") == "rule"

        level.setCurrentIndex(level.findData("optional"))
        assert rule["level"] == "optional"

        level.setCurrentIndex(level.findData("unchecked"))
        assert not [
            r
            for r in rc._current_ruleset().get("field_rules") or []
            if r.get("field") == "dateOfDeposit"
        ], "unchecking removes the rule"
        assert rc._row_data(item).get("rule_kind") == "new"
    finally:
        _restore(rc, snapshot)


def test_the_check_column_writes_the_handler_and_seeds_params(win, qapp):
    rc, snapshot, item = _with_field_row(win, qapp)
    try:
        level, check = _cells(rc, item)
        # On an unchecked row there is no rule to re-point at.
        check.setCurrentIndex(check.findData("looks_correct"))
        assert check.currentData() == "nonempty", "the pick reverts"
        assert rc._row_data(item).get("handler") == "nonempty"

        level.setCurrentIndex(level.findData("required"))
        check.setCurrentIndex(check.findData("looks_correct"))
        rule = next(
            r
            for r in rc._current_ruleset().get("field_rules") or []
            if r.get("block") == "citation" and r.get("field") == "dateOfDeposit"
        )
        assert rule["handler"] == "looks_correct"
        assert rule["params"] == {"not_common_placeholders": True}
        # Both dropdowns and the row itself now point at that rule.
        assert rc._row_data(item)["handler"] == "looks_correct"
        assert level.property("handler") == "looks_correct"
        assert check.property("handler") == "looks_correct"
        assert not rc._params_panel.isHidden()
    finally:
        _restore(rc, snapshot)


def test_a_block_heading_can_never_become_the_edited_rule(win, qapp):
    rc = _review(win, qapp)
    rc._sel_kind, rc._sel_key = "field", ""
    tree = rc._field_tree
    block_item = tree.topLevelItem(0)
    assert block_item is not None
    tree.clearSelection()
    rc._select_row(block_item)
    assert rc._row_data(block_item).get("kind") == "block"
    assert rc._sel_key == "", "a block heading is not a rule"
    # Nor is there a dropdown to hijack: the heading has no cell widget.
    assert tree.itemWidget(block_item, LEVEL_COLUMN) is None
    assert tree.itemWidget(block_item, CHECK_COLUMN) is None
