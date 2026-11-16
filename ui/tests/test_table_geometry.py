"""Contract: a table's columns fit the view that shows them.

The queue has no horizontal scrollbar, so the visible column widths have
to add up to the viewport width: when they do not, the right-hand
columns are cut off and the last label drifts off-centre. These tests
pin that invariant for the three interactions that used to break it (a
dragged edge, a moved column, a resized window).
"""

import pytest


@pytest.fixture
def dash(win, qapp):
    """Return the dashboard, on screen (the fit needs a visible table)."""
    win._show_dashboard()
    for _ in range(8):
        qapp.processEvents()
    return win._dashboard


def _visible_total(header) -> int:
    return sum(
        header.sectionSize(i) for i in range(header.count()) if not header.isSectionHidden(i)
    )


def _last_visible_logical(header) -> int:
    last = -1
    for v in range(header.count()):
        logical = header.logicalIndex(v)
        if not header.isSectionHidden(logical):
            last = logical
    return last


def _settle(qapp, rounds=8):
    for _ in range(rounds):
        qapp.processEvents()


def test_queue_columns_fill_the_viewport(dash, qapp):
    table = dash._table
    hdr = table.horizontalHeader()
    _settle(qapp)
    assert _visible_total(hdr) == table.viewport().width()


def test_no_visible_column_is_empty(dash, qapp):
    hdr = dash._table.horizontalHeader()
    _settle(qapp)
    for i in range(hdr.count()):
        if hdr.isSectionHidden(i):
            continue
        assert hdr.sectionSize(i) > 0, f"column {i} has no width"


def test_columns_still_fit_after_a_drag(dash, qapp):
    table = dash._table
    hdr = table.horizontalHeader()
    _settle(qapp)
    hdr.resizeSection(0, hdr.sectionSize(0) + 60)
    _settle(qapp)
    assert _visible_total(hdr) == table.viewport().width()


def test_columns_still_fit_after_a_move(dash, qapp):
    table = dash._table
    hdr = table.horizontalHeader()
    _settle(qapp)
    hdr.moveSection(0, 3)
    _settle(qapp)
    assert _visible_total(hdr) == table.viewport().width()


def test_columns_still_fit_after_a_window_resize(win, dash, qapp):
    table = dash._table
    hdr = table.horizontalHeader()
    _settle(qapp)
    win.resize(940, 800)
    _settle(qapp, 12)
    assert _visible_total(hdr) == table.viewport().width()
    assert _visible_total(hdr) <= table.viewport().width()


def test_the_last_visible_column_keeps_a_width(dash, qapp):
    hdr = dash._table.horizontalHeader()
    _settle(qapp)
    last = _last_visible_logical(hdr)
    assert last >= 0
    assert hdr.sectionSize(last) >= hdr.minimumSectionSize()
