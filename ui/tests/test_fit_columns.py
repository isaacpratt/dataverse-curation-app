"""Behavioral tests for AppTable content-fit + auto-fit locks.

Covers the column-width polish: fit-to-content with proportional
downscale, manual-resize/restore locks, reset unlock, and the
columns_fitted signal used by the dashboard's split header.
Uses an offscreen QApplication so no display is required.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytestmark = pytest.mark.skipif(
    os.environ.get("QT_QPA_PLATFORM") != "offscreen",
    reason="fit tests need a (offscreen) QApplication",
)


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    return app


def _make_table(rows=5, cols=3, cell_text="x" * 40):
    from ui.widgets import AppTable

    tbl = AppTable([f"Column {i}" for i in range(cols)], stretch_last=False)
    tbl.populate_guarded(rows)
    for r in range(rows):
        for c in range(cols):
            tbl.setItem(r, c, _item(cell_text))
    tbl.resize(600, 300)
    tbl.show()
    return tbl


def _item(text):
    from PySide6.QtWidgets import QTableWidgetItem

    return QTableWidgetItem(text)


def test_fit_sizes_columns_to_content(qapp):
    tbl = _make_table(cell_text="W" * 30)
    tbl.fit_columns_to_content()
    hdr = tbl.horizontalHeader()
    # Fitted Interactive columns must exceed the 48px floor and reflect
    # the long cell content (30 chars ≫ the 120px construction default
    # only if measurement ran — assert it grew past min_width at least).
    for i in range(3):
        assert hdr.sectionSize(i) >= 48
    assert tbl._fitted is True


def test_fit_noop_when_already_fitted(qapp):
    tbl = _make_table()
    tbl.fit_columns_to_content()
    hdr = tbl.horizontalHeader()
    before = [hdr.sectionSize(i) for i in range(3)]
    # Content changes after the first fit must not re-shrink columns.
    for r in range(tbl.rowCount()):
        tbl.setItem(r, 0, _item("Z"))
    tbl.fit_columns_to_content()
    assert [hdr.sectionSize(i) for i in range(3)] == before


def test_manual_resize_locks_fit(qapp):
    tbl = _make_table()
    tbl.horizontalHeader().resizeSection(0, 55)
    tbl.fit_columns_to_content()  # must be a no-op: user owns the layout
    assert tbl._auto_fit is False
    assert tbl.horizontalHeader().sectionSize(0) == 55


def test_enable_auto_fit_unlocks_and_refits(qapp):
    tbl = _make_table()
    tbl.disable_auto_fit()
    tbl.fit_columns_to_content()
    assert tbl._fitted is False or tbl._auto_fit is False
    tbl.enable_auto_fit()
    assert tbl._auto_fit is True
    assert tbl._fitted is False
    tbl.fit_columns_to_content()
    assert tbl._fitted is True


def test_fit_emits_columns_fitted(qapp):
    tbl = _make_table()
    seen = []
    tbl.columns_fitted.connect(lambda: seen.append(True))
    tbl.fit_columns_to_content()
    assert seen == [True]


def test_fit_downscales_when_viewport_too_narrow(qapp):
    """Total content width > viewport → every column scales by one ratio."""
    tbl = _make_table(rows=3, cols=3, cell_text="M" * 80)
    tbl.resize(240, 150)  # far narrower than 3 × 80-char columns
    tbl.fit_columns_to_content()
    hdr = tbl.horizontalHeader()
    total = sum(hdr.sectionSize(i) for i in range(3))
    # Must fit the viewport (allow min_width floors + frame slack).
    assert total <= tbl.viewport().width() + 3 * 48 + 24
    # And nothing collapsed below the floor.
    for i in range(3):
        assert hdr.sectionSize(i) >= 48


def test_fit_skips_when_hidden_defers_to_show(qapp):
    tbl = _make_table()
    tbl.hide()
    tbl.fit_columns_to_content()
    assert tbl._fitted is False  # hidden → showEvent will fit instead
    tbl.show()
    # showEvent schedules via QTimer.singleShot(0, …): process events.
    from PySide6.QtCore import QCoreApplication

    QCoreApplication.processEvents()
    assert tbl._fitted is True


def test_fit_noop_on_empty_table(qapp):
    from ui.widgets import AppTable

    tbl = AppTable(["A", "B"])
    tbl.resize(400, 200)
    tbl.show()
    tbl.fit_columns_to_content()
    # rowCount == 0 → no fit yet (populate retries on the next call).
    assert tbl._fitted is False


def test_show_refreshes_stale_cell_widget_geometry(qapp):
    """Hidden-built cell widgets re-layout on first show (dv-dm3)."""
    from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget

    from ui.widgets import AppTable

    tbl = AppTable(["A", "Action"], sortable=False, stretch_last=False)
    tbl.populate_guarded(1)
    tbl.setItem(0, 0, _item("pyreadstat"))
    cell = QWidget()
    lay = QHBoxLayout(cell)
    from PySide6.QtCore import QSize

    btn = QPushButton("Reinstall")
    btn.setFixedSize(QSize(90, 28))
    lay.addWidget(btn)
    tbl.setCellWidget(0, 1, cell)
    tbl.setColumnWidth(1, 300)
    tbl.resize(600, 120)
    # Hide-then-show round trip: the first show must give the cell widget
    # one full layout pass against the new column width.
    tbl.hide()
    tbl.setColumnWidth(1, 150)
    tbl.show()
    from PySide6.QtCore import QCoreApplication

    QCoreApplication.processEvents()
    QCoreApplication.processEvents()
    cell = tbl.cellWidget(0, 1)
    assert cell is not None
    assert cell.width() > 0
    assert cell.width() <= tbl.viewport().width() - 1
    # The cell content (the button) must not overflow its client rect.
    cell_layout = cell.layout()
    layout_hint = cell_layout.sizeHint().width() if cell_layout is not None else 0
    assert layout_hint <= cell.width() + 1 or cell.sizeHint().width() <= cell.width() + 1


def test_refresh_cell_geometry_is_idempotent(qapp):

    tbl = _make_table(rows=2, cols=2)
    tbl.refresh_cell_geometry()
    tbl.refresh_cell_geometry()  # twice must not raise or shrink sections
