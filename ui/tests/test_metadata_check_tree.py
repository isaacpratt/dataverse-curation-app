"""Metadata checks show compound fields as an expandable tree.

A repeatable field (author, contact, description, keyword, publication)
gets one child row per entry and one grandchild per subfield, so an
affiliation is visible next to the author it belongs to instead of being
flattened into one semicolon-joined line.
"""

from pathlib import Path

import pytest
from PySide6.QtCore import Qt


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
        "Metadata tree",
        cached_metadata=_metadata(),
        cached_inventory=[],
    )
    for _ in range(5):
        qapp.processEvents()
    yield view
    view.deleteLater()


def _row(detail, label: str):
    for row in range(detail._meta_model.rowCount()):
        item = detail._meta_model.item(row, 0)
        if item is not None and item.text() == label:
            return item
    raise AssertionError(f"check {label!r} not found")


def _grandchild_labels(entry) -> list[str]:
    return [entry.child(i, 0).text() for i in range(entry.rowCount())]


def test_author_entries_expand_to_name_affiliation_and_identifier(detail):
    author = _row(detail, "Author Name & Affiliation")
    assert author.rowCount() == 2, "each author must be its own child row"
    first = author.child(0, 0)
    assert first.text() == "Author 1"
    assert _grandchild_labels(first) == [
        "Name",
        "Affiliation",
        "Identifier scheme",
        "Identifier",
    ]
    assert first.child(1, 2).text() == "Analytical Engine Lab"
    missing = author.child(1, 0)
    assert missing.text() == "Author 2"
    assert missing.child(1, 2).text() == "—", "an empty affiliation must be visible"


def test_contact_description_and_subject_are_readable(detail):
    contact = _row(detail, "Dataset Contact").child(0, 0)
    assert _grandchild_labels(contact) == ["Name", "Affiliation", "Email"]
    description = _row(detail, "Description").child(0, 0)
    assert _grandchild_labels(description) == ["Description", "Date"]
    subject = _row(detail, "Subject")
    assert subject.rowCount() == 1
    assert subject.child(0, 2).text() == "Computer and Information Science"


def test_complete_filter_rebuilds_the_tree(detail):
    detail._meta_filter.setCurrentIndex(
        detail._meta_filter.findData("incomplete")
    )
    texts = [
        detail._meta_model.item(r, 0).text()
        for r in range(detail._meta_model.rowCount())
    ]
    assert texts, "the incomplete filter must still show something"
    assert "Title" not in texts, "a complete check must be filtered out"


def test_no_inner_scrollbars(detail):
    tree = detail._meta_check_tree
    assert tree.verticalScrollBarPolicy() == Qt.ScrollBarAlwaysOff
    assert tree.horizontalScrollBarPolicy() == Qt.ScrollBarAlwaysOff
