"""Check guidance (dv-lfn): conformance, old-payload tolerance, and the
render paths (Markdown report + response-draft {remediation})."""

import re
from pathlib import Path

from engine.checks import guidance
from engine.checks.base import CheckResult
from engine.report import DatasetReport, FileEntry
from engine.report_md import render_markdown
from response_draft import collect_filecheck_sections

CHECK_DIR = Path(__file__).resolve().parents[1] / "checks"
_ID_RE = re.compile(r'"((?:format|inventory|dataset|metadata|advice)\.[a-z0-9_.]+)"')
_SKIP_FILES = {"base.py", "_util.py", "guidance.py", "__init__.py"}


def _module_literals() -> dict[str, str]:
    """Every check-id-shaped literal in the check modules -> module name."""
    ids: dict[str, str] = {}
    for path in sorted(CHECK_DIR.glob("*.py")):
        if path.name in _SKIP_FILES:
            continue
        text = path.read_text(encoding="utf-8")
        for m in _ID_RE.finditer(text):
            ids.setdefault(m.group(1), path.name)
    return ids


class TestConformance:
    def test_every_emitted_check_id_has_guidance(self):
        missing = {
            cid: mod for cid, mod in _module_literals().items()
            if cid not in guidance.GUIDANCE
        }
        assert missing == {}, (
            "check ids without rationale/remediation: "
            + ", ".join(f"{cid} ({mod})" for cid, mod in sorted(missing.items()))
        )

    def test_guidance_entries_are_non_empty(self):
        for cid, (why, fix) in guidance.GUIDANCE.items():
            assert why.strip(), f"{cid}: empty rationale"
            assert fix.strip(), f"{cid}: empty remediation"

    def test_guidance_has_no_stale_entries(self):
        stale = sorted(set(guidance.GUIDANCE) - set(_module_literals()))
        assert stale == [], f"GUIDANCE keys no module emits: {stale}"


class TestCheckResultFields:
    def test_old_payload_loads_unchanged(self):
        result = CheckResult.from_dict({
            "check_id": "format.csv.content", "level": "warning",
            "passed": False, "message": "dupes",
        })
        assert result.rationale == ""
        assert result.remediation == ""

    def test_fields_round_trip(self):
        result = CheckResult("x", "warning", False, "m", {},
                             rationale="why", remediation="fix")
        data = result.to_dict()
        assert data["rationale"] == "why" and data["remediation"] == "fix"
        again = CheckResult.from_dict(data)
        assert (again.rationale, again.remediation) == ("why", "fix")

    def test_plain_payload_omits_fields(self):
        data = CheckResult("x", "info", True, "m").to_dict()
        assert "rationale" not in data and "remediation" not in data

    def test_for_result_prefers_bespoke(self):
        result = CheckResult("format.csv.content", "warning", False, "m",
                             rationale="bespoke why", remediation="")
        why, fix = guidance.for_result(result)
        assert why == "bespoke why"
        assert fix == guidance.GUIDANCE["format.csv.content"][1]


class TestRenderPaths:
    def _report(self) -> DatasetReport:
        return DatasetReport(
            persistent_id="p", label="l", engine_version="t",
            files=[FileEntry(path="a.csv", size_bytes=1, mime_type="text/csv",
                             checks=[CheckResult("format.csv.pii", "warning", False,
                                                 "2 emails")])],
        )

    def test_markdown_includes_guidance_for_failures(self):
        md = render_markdown(self._report())
        assert "Why this matters:" in md
        assert "How to fix:" in md
        assert "privacy incident" in md

    def test_markdown_omits_guidance_for_passes(self):
        report = DatasetReport(
            persistent_id="p", label="l", engine_version="t",
            files=[FileEntry(path="a.csv", size_bytes=1, mime_type="text/csv",
                             checks=[CheckResult("format.csv.content", "info", True,
                                                 "parsed")])],
        )
        md = render_markdown(report)
        assert "Why this matters:" not in md

    def test_response_template_remediation_placeholder(self):
        ruleset = {
            "filecheck_templates": {
                "format.csv.pii": "Please address {message}.\nSuggestion: {remediation}",
            },
        }
        sections = collect_filecheck_sections(ruleset, self._report())
        assert len(sections) == 1
        assert "Suggestion: Remove or de-identify" in sections[0]["message"]

    def test_response_template_without_placeholder_unchanged(self):
        sections = collect_filecheck_sections({}, self._report())
        assert "{remediation}" not in sections[0]["message"]
