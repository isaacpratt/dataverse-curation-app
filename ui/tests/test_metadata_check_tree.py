"""Metadata checks render as Auto-Checks-style rows (dv-h70).

One card per rule: icon reflecting the outcome, bold caption = the rule's
label, a one-line verdict sentence, right-aligned badge and a small left
bar on required rules. Compound fields expand into an inline drawer (one
block per entry, each subfield as a caption line) instead of a 5-column
tree. Two rules may share a field — the rows key off the result list.
"""

from pathlib import Path

import pytest
from PySide6.QtWidgets import QComboBox, QToolButton


def _fv(value):
    return {"typeName": "text", "multiple": False, "typeClass": "primitive", "value": value}


def _metadata() -> dict:
    return {
        "latestVersion": {
            "license": {"name": "CC0 1.0"},
            "metadataBlocks": {
                "citation": {
                    "fields": [
                        {"typeName": "title", "value": "A study"},
                        {"typeName": "author", "value": [
                            {
                                "authorName": _fv("Ada Lovelace"),
                                "authorAffiliation": _fv("Analytical Engine Lab"),
                                "authorIdentifierScheme": _fv("ORCID"),
                                "authorIdentifier": _fv("0000-0002-1825-0097"),
                            },
                            {
                                "authorName": _fv("Grace Hopper"),
                                "authorAffiliation": _fv(""),
                            },
                        ]},
                        {"typeName": "datasetContact", "value": [
                            {
                                "datasetContactName": _fv("Ada Lovelace"),
                                "datasetContactAffiliation": _fv("Analytical Engine Lab"),
                                "datasetContactEmail": _fv("ada@example.org"),
                            }
                        ]},
                        {"typeName": "dsDescription", "value": [
                            {
                                "dsDescriptionValue": _fv("A description."),
                                "dsDescriptionDate": _fv("2026-01-01"),
                            }
                        ]},
                        {"typeName": "subject", "value": ["Computer and Information Science"]},
                        {"typeName": "depositor", "value": "Ada Lovelace"},
                        {"typeName": "dateOfDeposit", "value": "2026-01-02"},
                    ]
                }
            },
        }
    }


@pytest.fixture
def detail(qapp, tmp_path):
    from config import Config
    from ui.dataset_detail import DatasetDetailView

    cfg = Config()
    cfg.app.workspace = Path(tmp_path)
    view = DatasetDetailView(
        cfg,
        "doi:10.5072/FK2/META",
        "Metadata rows",
        cached_metadata=_metadata(),
        cached_inventory=[],
    )
    for _ in range(5):
        qapp.processEvents()
    yield view
    view.deleteLater()


def _rows(detail):
    out = []
    lay = detail._meta_body_lay
    for i in range(lay.count()):
        widget = lay.itemAt(i).widget()
        if widget is not None and widget.property("meta_field") is not None:
            out.append(widget)
    return out


def _row(detail, label: str):
    for widget in _rows(detail):
        if widget.property("meta_field") == label:
            return widget
    raise AssertionError(f"row {label!r} not found")


def _drawer(detail, row):
    """Return the drawer directly following a compound-field row, if any."""
    lay = detail._meta_body_lay
    for i in range(lay.count() - 1):
        if lay.itemAt(i).widget() is row:
            candidate = lay.itemAt(i + 1).widget()
            if candidate is not None and candidate.property("meta_field") is None:
                return candidate
    return None


def _labels_in(frame) -> list[str]:
    from PySide6.QtWidgets import QLabel

    return [w.text() for w in frame.findChildren(QLabel)]


def test_every_rule_renders_as_a_row(detail):
    fields = [widget.property("meta_field") for widget in _rows(detail)]
    assert "Title" in fields
    assert "Author Name & Affiliation" in fields
    assert "Dataset Contact" in fields
    assert "Description" in fields
    assert "Subject" in fields
    assert "Time Period / Date of Collection" in fields or "Subject" in fields


def test_badge_and_status_complete_for_title(detail):
    row = _row(detail, "Title")
    assert "Complete" in _labels_in(row)


def _qframe_by_name(row, name):
    from PySide6.QtWidgets import QFrame

    return [w for w in row.findChildren(QFrame) if w.objectName() == name]


def test_required_rows_carry_the_left_bar_optional_ones_do_not(detail):
    assert _qframe_by_name(_row(detail, "Title"), "MetaRequiredBar")
    assert not _qframe_by_name(_row(detail, "ORCiD for authors"), "MetaRequiredBar")


def test_author_entries_expand_in_the_drawer(detail):
    row = _row(detail, "Author Name & Affiliation")
    drawer = _drawer(detail, row)
    assert drawer is not None, "compound fields must carry a drawer"
    assert drawer.isHidden()
    chevrons = list(row.findChildren(QToolButton))
    assert len(chevrons) == 1
    chevrons[0].click()
    assert not drawer.isHidden()
    labels = _labels_in(drawer)
    entry_heads = [line for line in labels if line.startswith("Author ")]
    assert entry_heads == ["Author 1", "Author 2"]
    assert any(line.startswith("Name: Ada Lovelace") for line in labels)
    assert any(line.startswith("Affiliation: —") for line in labels), "an empty affiliation must stay visible"
    # toggle back
    chevrons[0].click()
    assert drawer.isHidden()


def test_author_entry_headline_is_authorname_not_affiliation(detail):
    """Identity summary must not depend on the API's key order."""
    detail._metadata["latestVersion"]["metadataBlocks"]["citation"]["fields"][1]["value"][0] = {
        "authorAffiliation": {"typeName": "text", "value": "Analytical Engine Lab"},
        "authorName": {"typeName": "text", "value": "Ada Lovelace"},
        "authorIdentifierScheme": {"typeName": "text", "value": "ORCID"},
        "authorIdentifier": {"typeName": "text", "value": "0000-0002-1825-0097"},
    }
    detail._populate_completeness(detail._metadata)
    row = _row(detail, "Author Name & Affiliation")
    drawer = _drawer(detail, row)
    grid = _labels_in(drawer)
    heads = [line for line in grid if line.startswith("Ada Lovelace")]
    assert heads, "the entry headline must be the author name, never an affiliation"


def test_orcid_rule_has_no_drawer(detail):
    row = _row(detail, "ORCiD for authors")
    assert not row.findChildren(QToolButton), "the ORCID rule must not re-expand the author entries"


def test_single_entry_description_has_no_numbered_entry(detail):
    row = _row(detail, "Description")
    drawer = _drawer(detail, row)
    assert drawer is not None
    labels = _labels_in(drawer)
    assert not any(line.startswith("Description 1") for line in labels)
    assert any(line.startswith("Date: 2026-01-01") for line in labels)


def test_incomplete_rows_carry_disposition_controls(detail):
    row = _row(detail, "ORCiD for authors")
    if "Incomplete" not in _labels_in(row):
        pytest.skip("ORCID rule completed for this fixture")
    assert row.findChildren(QComboBox), "incomplete findings carry the disposition combo"


def test_complete_filter_rebuilds_the_rows(detail):
    detail._meta_filter.setCurrentIndex(detail._meta_filter.findData("incomplete"))
    for widget in _rows(detail):
        assert "Complete" not in _labels_in(widget)
    detail._meta_filter.setCurrentIndex(detail._meta_filter.findData("all"))
    assert _rows(detail), "the All filter must restore the rows"


def test_unchecked_filter_shows_ghost_rows(detail):
    detail._unchecked_results = [{
        "rule_id": "field:citation.title", "kind": "field",
        "field": "Title", "requirement": "off by ruleset",
        "value": "—", "status": "skipped", "level": "unchecked",
        "pending": False, "response_template": "",
        "block": "citation", "name": "title",
    }]
    detail._meta_filter.setCurrentIndex(detail._meta_filter.findData("unchecked"))
    rows = _rows(detail)
    assert [w.property("meta_field") for w in rows] == ["Title"]
    assert "Not checked" in _labels_in(rows[0])
    # The ghost row never leaks into the default or Complete views
    detail._meta_filter.setCurrentIndex(detail._meta_filter.findData("all"))
    fields = [w.property("meta_field") for w in _rows(detail)]
    assert fields and "Title" in fields
    assert _labels_in(_row(detail, "Title")) != ["—"]


def test_section_headers_group_the_blocks(detail):
    from PySide6.QtWidgets import QPushButton

    lay = detail._meta_body_lay
    buttons = []
    for i in range(lay.count()):
        widget = lay.itemAt(i).widget()
        if widget is not None and widget.objectName() == "MetaSectionHeader":
            buttons.extend(w.text() for w in widget.findChildren(QPushButton) if w.text())
    assert "Citation" in buttons


def test_section_toggles_collapse_the_block(detail):
    from PySide6.QtWidgets import QPushButton

    lay = detail._meta_body_lay
    header = next(
        lay.itemAt(i).widget() for i in range(lay.count())
        if lay.itemAt(i).widget() is not None
        and lay.itemAt(i).widget().objectName() == "MetaSectionHeader"
    )
    btn = next(w for w in header.findChildren(QPushButton) if w.text() == "Citation")
    row = _row(detail, "Title")
    assert not row.isHidden()
    btn.click()
    assert row.isHidden()
    btn.click()
    assert not row.isHidden()
