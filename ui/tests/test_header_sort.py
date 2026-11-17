"""Contract: clicking the sort arrow in a header sorts the column.

``QTest.mouseClick`` on a ``QHeaderView`` never reached the header in
this harness - no ``sectionClicked``, stock ``QTableWidget`` included -
so the click test drives the event the way the app receives it:

* the kit paints the sort arrow itself, on a child label over the
  section (``SortArrowHeaderView``);
* that label is transparent for mouse events, so the widget under the
  arrow is the header's viewport - the click is not swallowed by the
  arrow;
* a press/release on the viewport at the arrow's position sorts the
  column, exactly as a curator's click does.

The test therefore needs the arrow: without ``SortArrowHeaderView``
there is no arrow to click, and the end-to-end test fails.
"""

from __future__ import annotations

import logging

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QHeaderView, QLabel, QTableWidgetItem, QWidget

from ui.widgets import AppTable, SortArrowHeaderView


def _arrow_label(header: QHeaderView) -> QLabel | None:
    """The arrow the kit paints over the sorted section (a child label)."""
    for label in header.findChildren(QLabel):
        if label.isVisible():
            return label
    return None


def _click(widget: QWidget, pos: QPoint) -> None:
    """A press and a release at a point, sent the way the app receives them."""
    app = QApplication.instance()
    assert app is not None
    press = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(pos),
        QPointF(pos),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    release = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        QPointF(pos),
        QPointF(pos),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    app.sendEvent(widget, press)
    app.sendEvent(widget, release)
    app.processEvents()


def _titles(table: AppTable) -> list[str]:
    return [table.item(row, 0).text() for row in range(table.rowCount())]


@pytest.fixture
def queue_table(qapp):
    """A shown queue table with three rows and the first column sorted."""
    host = QWidget()
    table = AppTable(["Alpha", "Beta"], parent=host)
    table.setRowCount(3)
    for row, (title, size) in enumerate((("beta", "2"), ("alpha", "1"), ("gamma", "3"))):
        table.setItem(row, 0, QTableWidgetItem(title))
        table.setItem(row, 1, QTableWidgetItem(size))
    table.setSortingEnabled(True)
    table.sortItems(0, Qt.SortOrder.AscendingOrder)
    header = table.horizontalHeader()
    header.setSortIndicator(0, Qt.SortOrder.AscendingOrder)
    header.setSortIndicatorShown(True)
    host.resize(400, 200)
    host.show()
    qapp.processEvents()
    header.repaint()
    qapp.processEvents()
    yield table
    host.close()


def test_the_kit_installs_the_sort_arrow_header(qapp):
    """The kit owns the header that paints the arrow."""
    host = QWidget()
    table = AppTable(["Alpha"], parent=host)
    assert isinstance(table.horizontalHeader(), SortArrowHeaderView)
    host.close()


def test_the_dashboard_queue_uses_the_sort_arrow_header(win):
    """The real queue is covered, not only the kit in isolation."""
    assert isinstance(win._dashboard._table.horizontalHeader(), SortArrowHeaderView)


def test_clicking_the_sort_arrow_sorts_the_column(queue_table, qapp, caplog):
    """A click on the arrow sorts the column - the whole path, end to end."""
    table = queue_table
    header = table.horizontalHeader()

    arrow = _arrow_label(header)
    assert arrow is not None, "the sorted section has no arrow to click"

    # The arrow is transparent for mouse events: the click lands on the
    # header's viewport, not on the label that draws the arrow.
    centre = arrow.geometry().center()
    receiver = QApplication.widgetAt(header.mapToGlobal(centre))
    assert receiver is header.viewport(), (
        f"the arrow swallowed the click: {type(receiver).__name__} is under the arrow"
    )

    clicks: list[int] = []
    header.sectionClicked.connect(clicks.append)
    assert _titles(table) == ["alpha", "beta", "gamma"]

    with caplog.at_level(logging.INFO, logger="curation_app"):
        _click(receiver, receiver.mapFromGlobal(header.mapToGlobal(centre)))
        # The sort result, logged so a failure says what happened.
        logging.getLogger("curation_app").info(
            "header-click sort result: section=%s order=%s rows=%s",
            header.sortIndicatorSection(),
            header.sortIndicatorOrder(),
            _titles(table),
        )

    assert clicks == [0], "the click did not reach the header"
    assert header.sortIndicatorSection() == 0
    assert header.sortIndicatorOrder() == Qt.SortOrder.DescendingOrder
    assert _titles(table) == ["gamma", "beta", "alpha"], "the column did not sort"
    assert "header-click sort result" in caplog.text


def test_a_stock_header_has_no_arrow_to_click(qapp):
    """Why the end-to-end test needs ``SortArrowHeaderView``.

    Without the kit's header there is no arrow over the section, so the
    click test above has nothing to click and fails - the regression
    guard bites only because the kit owns the arrow.
    """
    host = QWidget()
    table = AppTable(["Alpha"], parent=host)
    table.setHorizontalHeader(QHeaderView(Qt.Orientation.Horizontal, table))
    assert _arrow_label(table.horizontalHeader()) is None
    host.close()
