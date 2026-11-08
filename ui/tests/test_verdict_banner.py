"""Verdict banner (dv-6nv): the card renders levels + reason chips and a
chip routes to the card that owns the reason."""

import pytest

from engine.verdict import Verdict


@pytest.fixture()
def view(qapp):
    """A bare DatasetDetailView with just the verdict card wired."""
    from ui.dataset_detail import DatasetDetailView

    v = DatasetDetailView.__new__(DatasetDetailView)
    v._report = None
    v._completeness_full = []
    v._dispositions_cache = {}
    v._verdict_card = v._build_verdict_card()
    return v


def test_banner_starts_unreviewed(view):
    view._refresh_verdict()
    assert "Not yet reviewed" in view._verdict_label.text()


def test_banner_shows_ready_and_revisions(view, qapp):
    from PySide6.QtWidgets import QPushButton

    view._report = None
    view._completeness_full = [
        {"field": "Affiliation", "rule_id": "authorAffiliation",
         "requirement": "req", "status": "incomplete", "level": "required",
         "pending": False},
        {"field": "ORCiD", "rule_id": "orcid", "requirement": "opt",
         "status": "incomplete", "level": "optional", "pending": False},
    ]
    view._refresh_verdict()
    assert "Revisions needed" in view._verdict_label.text()
    chips = view._verdict_card.findChildren(QPushButton)
    labels = [c.text() for c in chips]
    assert "1 required metadata fields missing" in labels
    assert "1 recommended fields missing" in labels

    view._completeness_full = []
    view._report = _clean_report()
    view._refresh_verdict()
    qapp.processEvents()
    assert "Ready" in view._verdict_label.text()
    assert view._verdict_card.findChildren(QPushButton) == []


def test_chip_routes_to_owner(view, qapp):
    from PySide6.QtWidgets import QPushButton

    view._report = None
    view._completeness_full = [
        {"field": "Affiliation", "rule_id": "authorAffiliation",
         "requirement": "req", "status": "incomplete", "level": "required",
         "pending": False},
    ]
    view._refresh_verdict()
    chips = view._verdict_card.findChildren(QPushButton)
    assert chips, "a reason chip exists"

    visited = []
    view._goto_section = lambda attr: visited.append(attr)  # type: ignore[method-assign]
    view._show_response_page = lambda: visited.append("respond")  # type: ignore[method-assign]

    chips[0].click()
    assert visited == ["_meta_card"]

    # The sensitivity reason routes to the Response page (dv-3c2 hook).
    from engine.verdict import assess

    v = assess(_clean_report(), None, sensitivity={"complete": False})
    assert v.reasons and v.reasons[0].target == "respond"


def _clean_report():
    from engine.checks.base import CheckResult
    from engine.report import DatasetReport, FileEntry

    return DatasetReport(
        persistent_id="doi:10.5072/FK2/EXAMPLE",
        label="Example",
        engine_version="test",
        files=[
            FileEntry(path="a.csv", size_bytes=10, mime_type="text/csv",
                      checks=[CheckResult("format.csv.content", "info", True, "parsed")]),
        ],
    )


def test_verdict_dataclass_is_pure():
    v = Verdict("ready")
    assert v.reasons == ()
