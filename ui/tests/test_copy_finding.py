"""Per-row overflow copy was removed (dv-gfx.8).

The old ellipsis button on a finding row opened a one-item copy menu. The
revamp drops it: finding rows show their verdict, message, disposition and
note affordances only, and copying a finding is no longer an offer the page
makes.
"""

from pathlib import Path
from typing import Any

import pytest


def _fv(value: Any):
    return {"typeName": "text", "multiple": False, "typeClass": "primitive", "value": value}


def _metadata() -> dict[str, Any]:
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
                                },
                            ],
                        },
                        {
                            "typeName": "datasetContact",
                            "value": [{"datasetContactName": _fv("Ada Lovelace")}],
                        },
                        {"typeName": "subject", "value": ["Computer and Information Science"]},
                        {"typeName": "depositor", "value": "Ada Lovelace"},
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


def test_no_finding_row_offers_a_copy_button(view):
    from PySide6.QtWidgets import QPushButton

    for btn in view.findChildren(QPushButton):
        # The dataset's own DOI legitimately contains "FK2/COPY"; the
        # affordance's name was "Copy this finding's text".
        assert (btn.toolTip() or "") != "Copy this finding's text"
        assert (btn.accessibleName() or "") != "Copy this finding's text"


def test_the_overflow_button_helper_is_gone(view):
    assert not hasattr(view, "_finding_overflow_button")
    assert not hasattr(view, "_build_copy_menu")
    assert not hasattr(view, "_show_copy_menu")


def test_an_auto_check_row_has_no_overflow_button(view):
    from PySide6.QtWidgets import QPushButton

    row = view._auto_row("format.csv.pii", "PII found in sample", False, "warning")
    for btn in row.findChildren(QPushButton):
        assert (btn.toolTip() or "") != "Copy this finding's text"
