"""Metadata check table: the Value|Status boundary is draggable (dv-dmv)."""

import pytest
from PySide6.QtWidgets import QHeaderView


@pytest.fixture(scope="module")
def detail(win, qapp):
    win._open_dataset("doi:10.5072/FK2/METACOLS", "Metadata columns (tests)")
    det = None
    for _ in range(120):
        qapp.processEvents()
        det = getattr(win, "_detail", None)
        if det is not None and getattr(det, "_meta_check_tree", None) is not None:
            break
    assert det is not None, "detail view did not open"
    win._stack.setCurrentWidget(det)
    for _ in range(30):
        qapp.processEvents()
    return det


def test_every_metadata_column_is_interactive(detail):
    hdr = detail._meta_check_tree.header()
    for col in range(4):
        assert hdr.sectionResizeMode(col) == QHeaderView.Interactive, (
            f"column {col} cannot be dragged (dv-dmv)"
        )
    assert not hdr.stretchLastSection()


def test_value_status_boundary_resizes(detail):
    hdr = detail._meta_check_tree.header()
    before = hdr.sectionSize(3)
    hdr.resizeSection(3, before + 60)
    assert hdr.sectionSize(3) == before + 60, "Status must follow a drag"
    value_before = hdr.sectionSize(2)
    hdr.resizeSection(2, value_before + 50)
    assert hdr.sectionSize(2) == value_before + 50, "Value must follow a drag"


def test_value_column_fills_the_leftover_width(detail):
    tree = detail._meta_check_tree
    hdr = tree.header()
    detail._fit_meta_value_column()
    others = sum(hdr.sectionSize(i) for i in range(hdr.count()) if i != 2)
    expected = max(48, tree.viewport().width() - others)
    assert hdr.sectionSize(2) == expected, "Value takes the slack"
