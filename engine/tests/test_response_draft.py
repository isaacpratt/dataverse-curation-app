"""Tests for the depositor response assembler (response_draft)."""

import review_rules as rr
from engine.checks.base import CheckResult
from engine.report import DatasetReport, FileEntry
from response_draft import build_response, render_response


def _ruleset():
    return rr.get_ruleset("mcmaster-default")


def test_empty_findings_gives_ready_note():
    md, sections = build_response(_ruleset(), [], None, "T", "doi:x")
    assert sections == []
    assert "ready" in md.lower()


def test_incomplete_metadata_uses_templates_and_placeholders():
    completeness = [
        {"rule_id": "field:citation.title", "kind": "field", "field": "Title",
         "requirement": "R", "value": "—", "status": "incomplete",
         "level": "required", "pending": False,
         "response_template": "Missing {field} in {dataset_title} ({persistent_id})."},
        {"rule_id": "field:citation.subject", "kind": "field", "field": "Subject",
         "requirement": "R", "value": "—", "status": "complete",
         "level": "required", "pending": False, "response_template": "nope"},
        {"rule_id": "c:readme", "kind": "content", "field": "README file",
         "requirement": "R", "value": "— (load file list to check)", "status": "incomplete",
         "level": "required", "pending": True, "response_template": "add readme"},
    ]
    md, sections = build_response(_ruleset(), completeness, None, "My DS", "doi:1")
    assert len(sections) == 1  # pending finding is skipped
    assert "Missing Title in My DS (doi:1)." in md


def test_filecheck_failures_included_passes_and_skips_excluded():
    report = DatasetReport(
        persistent_id="doi:1", label="x", engine_version="t",
        dataset_checks=[
            CheckResult(check_id="inventory.zero_byte", level="error", passed=False,
                        message="1 zero-byte file(s): empty.csv", details={}),
            CheckResult(check_id="inventory.extensions", level="info", passed=True,
                        message="3 files", details={}),
        ],
        files=[
            FileEntry(path="a.csv", size_bytes=10, mime_type="text/csv", checks=[
                CheckResult(check_id="format.csv.openable", level="warning", passed=False,
                            message="a.csv: blank header", details={}),
                CheckResult(check_id="format.csv.pii", level="info", passed=True,
                            message="ok", details={}),
            ]),
            FileEntry(path="b.csv", size_bytes=10, mime_type="text/csv", checks=[
                CheckResult(check_id="format.csv.pii", level="warning", passed=True,
                            message="skipped", details={"skipped": True}),
            ]),
        ],
    )
    md, sections = build_response(_ruleset(), [], report, "T", "doi:1")
    ids = sorted(s["id"] for s in sections)
    assert any("inventory.zero_byte" in i for i in ids)
    assert any("format.csv.openable" in i for i in ids)
    assert not any("extensions" in i or "b.csv" in i for i in ids)
    # zero_byte has a specific template mentioning the file
    assert "empty.csv" in md or "zero-byte" in md or "empty" in md


def test_render_respects_inclusion_flags():
    rs = _ruleset()
    sections = [
        {"id": "a", "kind": "metadata", "label": "Title", "level": "required",
         "requirement": "", "message": "First item", "template": "", "included": True},
        {"id": "b", "kind": "metadata", "label": "Subject", "level": "required",
         "requirement": "", "message": "Second item", "template": "", "included": False},
    ]
    md = render_response(rs, sections, "T", "doi:1")
    assert "First item" in md and "Second item" not in md


def test_items_raise_severity_tags():
    """Warnings/errors/required items are tagged up front in the draft."""
    md, sections = build_response(_ruleset(), [], None, "T", "doi:1")
    report = DatasetReport(
        persistent_id="doi:1", label="x", engine_version="t",
        dataset_checks=[
            CheckResult(check_id="inventory.zero_byte", level="error", passed=False,
                        message="empty.csv is empty", details={}),
        ],
        files=[
            FileEntry(path="a.csv", size_bytes=10, mime_type="text/csv", checks=[
                CheckResult(check_id="format.csv.openable", level="warning", passed=False,
                            message="a.csv: blank header", details={}),
            ]),
        ],
    )
    completeness = [
        {"rule_id": "field:citation.title", "kind": "field", "field": "Title",
         "requirement": "R", "value": "?", "status": "incomplete",
         "level": "required", "pending": False,
         "response_template": "Missing {field}."},
        {"rule_id": "field:citation.subject", "kind": "field", "field": "Subject",
         "requirement": "R", "value": "?", "status": "incomplete",
         "level": "optional", "pending": False,
         "response_template": "Consider adding {field}."},
    ]
    md, sections = build_response(_ruleset(), completeness, report, "T", "doi:1")
    assert "**Error:**" in md and "zero-byte" not in md
    assert "**Warning:**" in md
    assert "**Required:**" in md
    assert "**Recommended:**" in md
    # severity tags ride on the ruleset-driven messages
    err_line = next(line for line in md.splitlines() if "**Error:**" in line)
    assert "empty" in err_line  # ruleset's zero_byte template ("The file '{path}' is empty…")


def test_filecheck_level_flows_to_section():
    """Each file-check finding carries warning/error severity for the UI."""
    report = DatasetReport(
        persistent_id="doi:1", label="x", engine_version="t",
        dataset_checks=[],
        files=[
            FileEntry(path="a.pdf", size_bytes=10, mime_type="application/pdf", checks=[
                CheckResult(check_id="format.pdf.openable", level="error", passed=False,
                            message="a.pdf: corrupt", details={}),
            ]),
        ],
    )
    _md, sections = build_response(_ruleset(), [], report, "T", "doi:1")
    (section,) = sections
    assert section["kind"] == "filecheck"
    assert section["level"] == "error"
