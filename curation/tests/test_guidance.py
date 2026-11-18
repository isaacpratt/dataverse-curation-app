"""Check guidance (dv-lfn): conformance, old-payload tolerance, and the render paths (Markdown report + response-draft {remediation})."""

import re
from pathlib import Path

from curation.response_draft import collect_filecheck_sections
from engine.checks import guidance
from engine.checks.base import CheckResult
from engine.report import DatasetReport, FileEntry
from engine.report_md import render_markdown

_ROOT = Path(__file__).resolve().parents[2]
CHECK_DIR = _ROOT / "engine" / "checks"
_RUNNER = _ROOT / "engine" / "runner.py"
_ID_RE = re.compile(r'"((?:format|inventory|dataset|metadata|advice)\.[a-z0-9_.]+)"')
_SKIP_FILES = {"base.py", "_util.py", "guidance.py", "__init__.py"}


def _module_literals() -> dict[str, str]:
    """Every check-id-shaped literal in the check modules -> module name.

    engine/runner.py is included because it synthesizes the dataset-level
    ``inventory.unchecked_types`` result itself (no check class emits it),
    so a conformance sweep of engine/checks alone would silently miss it.
    """
    ids: dict[str, str] = {}
    paths = [path for path in sorted(CHECK_DIR.glob("*.py")) if path.name not in _SKIP_FILES]
    paths.append(_RUNNER)
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for m in _ID_RE.finditer(text):
            ids.setdefault(m.group(1), path.name)
    return ids


class TestConformance:
    def test_every_emitted_check_id_has_guidance(self):
        missing = {
            cid: mod for cid, mod in _module_literals().items() if cid not in guidance.GUIDANCE
        }
        assert missing == {}, "check ids without rationale/remediation: " + ", ".join(
            f"{cid} ({mod})" for cid, mod in sorted(missing.items())
        )

    def test_guidance_entries_are_non_empty(self):
        for cid, (why, fix) in guidance.GUIDANCE.items():
            assert why.strip(), f"{cid}: empty rationale"
            assert fix.strip(), f"{cid}: empty remediation"

    def test_guidance_has_no_stale_entries(self):
        stale = sorted(set(guidance.GUIDANCE) - set(_module_literals()))
        assert stale == [], f"GUIDANCE keys no module emits: {stale}"


class TestTitles:
    """dv-r0z/dv-dcd: every check has a human name, and only checks do."""

    def test_every_emitted_check_id_has_a_title(self):
        missing = {
            cid: mod for cid, mod in _module_literals().items() if cid not in guidance.TITLES
        }
        assert missing == {}, "check ids with no human title: " + ", ".join(
            f"{cid} ({mod})" for cid, mod in sorted(missing.items())
        )

    def test_titles_have_no_stale_entries(self):
        stale = sorted(set(guidance.TITLES) - set(_module_literals()))
        assert stale == [], f"TITLES keys no module emits: {stale}"

    def test_titles_and_guidance_cover_the_same_checks(self):
        assert set(guidance.TITLES) == set(guidance.GUIDANCE)

    def test_titles_read_as_names_not_ids(self):
        for cid, title in guidance.TITLES.items():
            assert title.strip(), f"{cid}: empty title"
            assert "." not in title, f"{cid}: title leaks a namespace: {title!r}"
            assert title[0].isupper(), f"{cid}: title not sentence-cased: {title!r}"

    def test_title_for_is_total(self):
        assert guidance.title_for("format.csv.openable") == "CSV Openable"
        assert guidance.title_for("inventory.zero_byte") == "Zero-Byte Files"
        assert guidance.title_for("not.a.check") == ""
        assert guidance.title_for("") == ""


class TestCheckResultFields:
    def test_old_payload_loads_unchanged(self):
        result = CheckResult.from_dict(
            {
                "check_id": "format.csv.content",
                "level": "warning",
                "passed": False,
                "message": "dupes",
            }
        )
        assert result.rationale == ""
        assert result.remediation == ""

    def test_fields_round_trip(self):
        result = CheckResult("x", "warning", False, "m", {}, rationale="why", remediation="fix")
        data = result.to_dict()
        assert data["rationale"] == "why"
        assert data["remediation"] == "fix"
        again = CheckResult.from_dict(data)
        assert (again.rationale, again.remediation) == ("why", "fix")

    def test_plain_payload_omits_fields(self):
        data = CheckResult("x", "info", True, "m").to_dict()
        assert "rationale" not in data
        assert "remediation" not in data

    def test_for_result_prefers_bespoke(self):
        result = CheckResult(
            "format.csv.content", "warning", False, "m", rationale="bespoke why", remediation=""
        )
        why, fix = guidance.for_result(result)
        assert why == "bespoke why"
        assert fix == guidance.GUIDANCE["format.csv.content"][1]


class TestRenderPaths:
    def _report(self) -> DatasetReport:
        return DatasetReport(
            persistent_id="p",
            label="l",
            engine_version="t",
            files=[
                FileEntry(
                    path="a.csv",
                    size_bytes=1,
                    mime_type="text/csv",
                    checks=[CheckResult("format.csv.pii", "warning", False, "2 emails")],
                )
            ],
        )

    def test_markdown_includes_guidance_for_failures(self):
        md = render_markdown(self._report())
        assert "Why this matters:" in md
        assert "How to fix:" in md
        assert "privacy incident" in md

    def test_markdown_omits_guidance_for_passes(self):
        report = DatasetReport(
            persistent_id="p",
            label="l",
            engine_version="t",
            files=[
                FileEntry(
                    path="a.csv",
                    size_bytes=1,
                    mime_type="text/csv",
                    checks=[CheckResult("format.csv.content", "info", True, "parsed")],
                )
            ],
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
