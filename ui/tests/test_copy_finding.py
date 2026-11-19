"""Per-row overflow copy (dv-18z): the ellipsis glyph on each finding row copies it."""

from pathlib import Path

import pytest


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
                        {
                            "typeName": "author",
                            "value": [
                                {
                                    "authorName": _fv("Ada Lovelace"),
                                    "authorAffiliation": _fv("Lab"),
                                    "authorIdentifierScheme": _fv("ORCID"),
                                    "authorIdentifier": _fv("0000-0002-1825-0097"),
                                },
                            ],
                        },
                        {
                            "typeName": "datasetContact",
                            "value": [
                                {"datasetContactName": _fv("Ada Lovelace")},
                            ],
                        },
                        {
                            "typeName": "dsDescription",
                            "value": [
                                {
                                    "dsDescriptionValue": _fv("Desc."),
                                    "dsDescriptionDate": _fv("2026-01-01"),
                                },
                            ],
                        },
                        {"typeName": "subject", "value": ["Computer and Information Science"]},
                        {"typeName": "depositor", "value": "Ada Lovelace"},
                        {"typeName": "dateOfDeposit", "value": "2026-01-02"},
                    ]
                }
            },
        }
    }


@pytest.fixture
def view(qapp, tmp_path):
    from curation.config import Config
    from ui.dataset import DatasetDetailView

    cfg = Config()
    cfg.app.workspace = Path(tmp_path)
    v = DatasetDetailView(
        cfg,
        "doi:10.5072/FK2/COPY",
        "Copy test",
        cached_metadata=_metadata(),
        cached_inventory=[],
    )
    for _ in range(5):
        qapp.processEvents()
    yield v
    v.deleteLater()


def _overflow_button(row):
    """Return the row's overflow button: the ellipsis glyph, named for the action."""
    from PySide6.QtWidgets import QPushButton

    from ui.i18n import t

    wanted = t("detail.copy_finding.action")
    for btn in row.findChildren(QPushButton):
        if btn.accessibleName() == wanted:
            return btn
    return None


def _meta_row(view, label: str):
    lay = view._meta_body_lay
    for i in range(lay.count()):
        widget = lay.itemAt(i).widget()
        if widget is not None and widget.property("meta_field") == label:
            return widget
    raise AssertionError(f"row {label!r} not found")


def test_meta_row_overflow_button_invokes_copy_menu(view):
    """Clicking the row's ellipsis must ask the view to show the menu."""
    opened = []
    view._show_copy_menu = lambda btn, text: opened.append((btn, text))

    row = _meta_row(view, "Title")
    btn = _overflow_button(row)
    assert btn is not None, "the row must offer an overflow copy action"

    btn.click()
    assert len(opened) == 1
    text = opened[0][1]
    assert "Title" in text
    assert "A study" in text


def test_meta_row_copy_menu_copies_single_line(view):
    from PySide6.QtWidgets import QApplication

    menu = view._build_copy_menu("Title — A study  (McMaster — Required)")
    actions = menu.actions()
    assert len(actions) == 1
    actions[0].trigger()
    assert QApplication.clipboard().text() == "Title — A study  (McMaster — Required)"


def test_auto_row_overflow_button_invokes_copy_menu(view):
    row = view._auto_row(
        "format.csv.pii",
        "PII found in sample",
        False,
        "warning",
    )
    btn = _overflow_button(row)
    assert btn is not None, "an auto-check row must offer an overflow copy action"

    opened = []
    view._show_copy_menu = lambda b, text: opened.append((b, text))
    btn.click()
    assert len(opened) == 1
    text = opened[0][1]
    assert "format.csv.pii" in text
    assert "PII found in sample" in text


def test_auto_row_copy_menu_copies_single_line(view):
    from PySide6.QtWidgets import QApplication

    menu = view._build_copy_menu("format.csv.pii — PII found in sample")
    actions = menu.actions()
    assert len(actions) == 1
    actions[0].trigger()
    assert QApplication.clipboard().text() == "format.csv.pii — PII found in sample"
