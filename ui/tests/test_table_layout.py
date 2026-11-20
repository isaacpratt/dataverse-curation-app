"""Contract: the persisted column layout (ui.table_layout.TableLayout).

The rules this file protects:

* a *user* gesture (a dragged edge, a moved column) is persisted;
* a *programmatic* change (a content fit, a viewport refit) is not --
  otherwise the app's own refit overwrites the layout the user chose;
* restore re-applies the saved layout, reset clears it and puts the
  construction view back;
* a layout saved for a different column count is ignored, not misapplied.
"""

import json
from typing import Any

import pytest
from PySide6.QtWidgets import QHeaderView

from curation.storage import (
    TABLE_LAYOUT_VERSION,
    clear_table_state,
    table_layout_entry_valid,
)


@pytest.fixture
def header(qapp):
    """Build a table with three columns and a throwaway workspace."""
    import tempfile
    from pathlib import Path

    from ui.widgets import AppTable

    table = AppTable(["One", "Two", "Three"], widths={0: 100, 1: 100, 2: 100})
    table.setHorizontalHeaderLabels(["One", "Two", "Three"])
    ws = Path(tempfile.mkdtemp(prefix="layout_ws_"))
    return table, table.horizontalHeader(), ws


def _entry(ws: Any, key: Any = "probe"):
    path = ws / "table_layout.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8")).get(key)


def test_user_resize_is_persisted(header):
    from ui.table_layout import TableLayout

    _table, hdr, ws = header
    TableLayout(ws, "probe", hdr)
    hdr.resizeSection(0, 180)
    entry = _entry(ws)
    assert entry is not None, "a user resize must be saved"
    assert entry["widths"][0] == 180
    assert entry["v"] == TABLE_LAYOUT_VERSION


def test_programmatic_resize_is_not_persisted(header):
    from ui.table_layout import TableLayout

    _table, hdr, ws = header
    layout = TableLayout(ws, "probe", hdr)
    assert layout is not None
    with layout.suppressed():
        hdr.resizeSection(0, 180)
    assert _entry(ws) is None, "a programmatic resize must not be saved"


def test_restore_reapplies_the_saved_layout(header):
    from ui.table_layout import TableLayout
    from ui.widgets import AppTable

    _table, hdr, ws = header
    TableLayout(ws, "probe", hdr)
    hdr.resizeSection(1, 222)  # a user gesture -> saved

    # A fresh table (a new session) gets the saved layout back.
    fresh_table = AppTable(["One", "Two", "Three"], widths={0: 100, 1: 100, 2: 100})
    fresh = TableLayout(ws, "probe", fresh_table.horizontalHeader())
    assert fresh.restore() is True
    assert fresh_table.horizontalHeader().sectionSize(1) == 222


def test_reset_clears_the_saved_layout_and_restores_the_snapshot(header):
    from ui.table_layout import TableLayout

    _table, hdr, ws = header
    layout = TableLayout(ws, "probe", hdr)
    original = hdr.sectionSize(0)
    hdr.resizeSection(0, 240)
    assert layout.reset() is True
    assert hdr.sectionSize(0) == original
    assert _entry(ws) is None, "reset must clear the saved layout"


def test_reset_survives_a_restart(header):
    from ui.table_layout import TableLayout

    table, hdr, ws = header
    TableLayout(ws, "probe", hdr).reset()
    clear_table_state(ws, "probe")
    fresh = TableLayout(ws, "probe", table.horizontalHeader())
    assert fresh.restore() is False


def test_a_layout_for_another_column_count_is_ignored(header):
    from ui.table_layout import TableLayout

    _table, hdr, ws = header
    path = ws / "table_layout.json"
    path.write_text(
        json.dumps({"probe": {"v": TABLE_LAYOUT_VERSION, "widths": [10, 20, 30, 40, 50]}}),
        encoding="utf-8",
    )
    layout = TableLayout(ws, "probe", hdr)
    assert layout.restore() is False
    assert hdr.sectionSize(0) == 100, "the table keeps its own widths"


def test_entry_validation_rules():
    assert table_layout_entry_valid({"v": 1, "widths": [1, 2]}, 2) is True
    assert table_layout_entry_valid({"widths": [1, 2]}, 2) is True  # legacy entry
    assert table_layout_entry_valid({"v": 1, "widths": [1, 2]}, 3) is False
    assert table_layout_entry_valid({"v": 99, "widths": [1, 2]}, 2) is False
    assert table_layout_entry_valid({"v": 1}, 2) is False
    assert table_layout_entry_valid(None, 2) is False


def test_a_stretched_section_is_not_a_user_gesture(qapp):
    """A section the layout owns is never persisted as a user resize.

    The last section of a stretching header is re-sized by every window
    resize: saving that would rewrite the user's layout on every resize.
    """
    import tempfile
    from pathlib import Path

    from ui.table_layout import TableLayout
    from ui.widgets import AppTable

    table = AppTable(["One", "Two", "Three"])  # stretch_last defaults to True
    ws = Path(tempfile.mkdtemp(prefix="layout_ws_"))
    TableLayout(ws, "probe", table.horizontalHeader(), view=table)

    table.horizontalHeader().resizeSection(2, 250)  # the stretched section
    assert _entry(ws) is None, "a stretched section is not a user gesture"

    table.horizontalHeader().resizeSection(0, 180)  # an interactive section
    entry = _entry(ws)
    assert entry is not None, "an interactive section is a user gesture"
    assert entry["widths"][0] == 180


def test_the_tree_widget_reports_user_gestures(qapp):
    """AppTreeWidget (the metadata field tree) follows the same contract."""
    from ui.widgets import AppTreeWidget

    tree = AppTreeWidget(row_height=None, flush=False)
    tree.setColumnCount(2)
    tree.setHeaderLabels(["Field", "Check"])
    tree.header().setStretchLastSection(False)  # as the review page sets it
    seen = []
    tree.user_layout_changed.connect(lambda: seen.append(True))

    tree.header().resizeSection(1, 150)
    assert seen == [True], "dragging an interactive section is a user gesture"

    tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    seen.clear()
    tree.header().resizeSection(0, 300)
    assert seen == [], "a stretched section is not a user gesture"
