"""Readiness verdict (dv-6nv): levels and reasons from crafted inputs."""

from curation.storage import finding_key as storage_finding_key
from engine.checks.base import CheckResult
from engine.report import DatasetReport, FileEntry
from engine.verdict import (
    LEVEL_BLOCKED,
    LEVEL_READY,
    LEVEL_REVISIONS,
    LEVEL_UNREVIEWED,
    REASON_ERRORS,
    REASON_OPTIONAL,
    REASON_REQUIRED,
    REASON_SENSITIVITY,
    REASON_TARGETS,
    REASON_WARNINGS,
    assess,
    finding_key,
    format_line,
)


def _report(*checks: tuple[str, str, bool, str], path: str = "a.csv") -> DatasetReport:
    """Report from (check_id, level, passed, message) tuples on one file."""
    return DatasetReport(
        persistent_id="doi:10.5072/FK2/EXAMPLE",
        label="Example",
        engine_version="test",
        files=[
            FileEntry(
                path=path,
                size_bytes=10,
                mime_type="text/csv",
                checks=[
                    CheckResult(check_id=cid, level=level, passed=passed, message=msg)
                    for cid, level, passed, msg in checks
                ],
            ),
        ],
    )


REQUIRED_ROW = {
    "field": "Affiliation",
    "rule_id": "authorAffiliation",
    "requirement": "McMaster — Recommended",
    "value": "—",
    "status": "incomplete",
    "level": "required",
    "pending": False,
}
OPTIONAL_ROW = {
    "field": "ORCiD",
    "rule_id": "orcid",
    "requirement": "optional",
    "value": "—",
    "status": "incomplete",
    "level": "optional",
    "pending": False,
}


SKIPPED_ROW = {
    "field": "Subject",
    "rule_id": "field:citation.subject",
    "requirement": "off",
    "value": "—",
    "status": "skipped",
    "level": "unchecked",
    "pending": False,
}


class TestSkippedRows:
    def test_an_all_skipped_list_is_unreviewed_not_ready(self):
        verdict = assess(None, [dict(SKIPPED_ROW)])
        assert verdict.level == LEVEL_UNREVIEWED

    def test_skipped_rows_never_count_as_findings(self):
        verdict = assess(None, [dict(SKIPPED_ROW), dict(OPTIONAL_ROW)])
        assert verdict.level == LEVEL_REVISIONS
        reasons = {r.key: r.count for r in verdict.reasons}
        assert reasons.get(REASON_OPTIONAL) == 1, (
            "the skipped row must not add to the optional-missing count"
        )
        assert REASON_REQUIRED not in reasons

    def test_a_complete_row_is_still_ready(self):
        ok_row = {**OPTIONAL_ROW, "status": "complete"}
        assert assess(None, [dict(SKIPPED_ROW), ok_row]).level == LEVEL_READY


class TestLevels:
    def test_nothing_loaded_is_unreviewed(self):
        assert assess(None, None).level == LEVEL_UNREVIEWED
        assert assess(None, []).level == LEVEL_UNREVIEWED

    def test_clean_dataset_is_ready(self):
        verdict = assess(_report(("format.csv.content", "info", True, "parsed")))
        assert verdict.level == LEVEL_READY
        assert verdict.reasons == ()

    def test_missing_required_rule_is_revisions(self):
        verdict = assess(None, [REQUIRED_ROW])
        assert verdict.level == LEVEL_REVISIONS
        assert REASON_REQUIRED in [r.key for r in verdict.reasons]

    def test_optional_missing_is_revisions(self):
        verdict = assess(None, [OPTIONAL_ROW])
        assert verdict.level == LEVEL_REVISIONS
        assert REASON_OPTIONAL in [r.key for r in verdict.reasons]

    def test_error_level_finding_is_blocked(self):
        verdict = assess(_report(("format.csv.pii", "error", False, "SIN pattern")))
        assert verdict.level == LEVEL_BLOCKED
        assert REASON_ERRORS in [r.key for r in verdict.reasons]

    def test_warning_finding_is_revisions(self):
        verdict = assess(_report(("format.csv.pii", "warning", False, "2 emails")))
        assert verdict.level == LEVEL_REVISIONS
        assert REASON_WARNINGS in [r.key for r in verdict.reasons]

    def test_sensitivity_pending_is_blocked(self):
        verdict = assess(
            _report(("format.csv.content", "info", True, "parsed")), sensitivity={"complete": False}
        )
        assert verdict.level == LEVEL_BLOCKED
        assert REASON_SENSITIVITY in [r.key for r in verdict.reasons]

    def test_resolved_findings_do_not_block(self):
        """A disposition-resolved error stops counting (dv-32x handoff)."""
        key = finding_key("format.csv.pii", "a.csv", "SIN pattern")
        verdict = assess(
            _report(("format.csv.pii", "error", False, "SIN pattern")),
            dispositions={key: {"disposition": "acknowledged", "note": ""}},
        )
        assert verdict.level == LEVEL_READY


class TestReasons:
    def test_counts_and_targets(self):
        verdict = assess(
            _report(
                ("format.csv.pii", "warning", False, "2 emails"),
                ("inventory.zero_byte", "error", False, "1 empty"),
            ),
            [REQUIRED_ROW, OPTIONAL_ROW],
        )
        by_key = {r.key: r for r in verdict.reasons}
        assert by_key[REASON_ERRORS].count == 1
        assert by_key[REASON_WARNINGS].count == 1
        assert by_key[REASON_REQUIRED].count == 1
        assert by_key[REASON_OPTIONAL].count == 1
        assert by_key[REASON_ERRORS].target == "_auto_card"
        assert by_key[REASON_REQUIRED].target == "_meta_card"

    def test_every_reason_has_a_target(self):
        verdict = assess(
            _report(("inventory.zero_byte", "error", False, "1 empty")),
            [REQUIRED_ROW],
            sensitivity={"complete": False},
        )
        for reason in verdict.reasons:
            assert reason.key in REASON_TARGETS
            assert reason.target


class TestLine:
    def test_format_line_tokens(self):
        line = format_line(assess(_report(("format.csv.pii", "error", False, "bad"))))
        assert line == "blocked — errors:1"

    def test_format_line_ready_has_no_reasons(self):
        assert format_line(assess(_report())) == "ready"


def test_finding_key_matches_storage():
    """The engine mirror must stay identical to storage.finding_key."""
    assert finding_key("format.csv.pii", "a.csv", "2  emails") == (
        storage_finding_key("format.csv.pii", "a.csv", "2 emails")
    )
