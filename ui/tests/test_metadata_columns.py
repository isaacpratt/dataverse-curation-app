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
    for col in range(5):
        assert hdr.sectionResizeMode(col) == QHeaderView.Interactive, (
            f"column {col} cannot be dragged (dv-dmv)"
        )
    assert not hdr.stretchLastSection()
    assert hdr.count() == 5, "Check | Level | Block | Value | Status"


def test_value_status_boundary_resizes(detail):
    hdr = detail._meta_check_tree.header()
    before = hdr.sectionSize(4)
    hdr.resizeSection(4, before + 60)
    assert hdr.sectionSize(4) == before + 60, "Status must follow a drag"
    value_before = hdr.sectionSize(3)
    hdr.resizeSection(3, value_before + 50)
    assert hdr.sectionSize(3) == value_before + 50, "Value must follow a drag"


def test_value_column_fills_the_leftover_width(detail):
    tree = detail._meta_check_tree
    hdr = tree.header()
    detail._fit_meta_value_column()
    others = sum(hdr.sectionSize(i) for i in range(hdr.count()) if i != 3)
    expected = max(48, tree.viewport().width() - others)
    assert hdr.sectionSize(3) == expected, "Value takes the slack"


def test_level_column_shows_ruleset_levels(detail):
    """The Level column states required vs optional per the active ruleset."""
    detail._meta_model.removeRows(0, detail._meta_model.rowCount())

    results = [
        {
            "field": "Title",
            "block": "citation",
            "status": "complete",
            "level": "required",
            "requirement": "",
            "value": "t",
            "rule_id": "field:citation.title",
        },
        {
            "field": "ORCiD for authors",
            "block": "citation",
            "status": "incomplete",
            "level": "optional",
            "requirement": "",
            "value": "—",
            "rule_id": "field:citation.author:orcid",
        },
    ]
    detail._meta_results = results
    detail._build_meta_tree(results)
    model = detail._meta_model
    assert model.horizontalHeaderItem(1).text() == "Level"
    assert [model.item(r, 1).text() for r in range(2)] == ["Required", "Optional"]
    assert model.item(0, 1).font().bold()
    assert not model.item(1, 1).font().bold()
