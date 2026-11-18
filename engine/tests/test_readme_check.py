"""README section-depth check + {readme_sections} placeholder (dv-81q)."""

import tempfile
from pathlib import Path

import curation.review_rules as rr
from curation.response_draft import collect_filecheck_sections
from engine.checks.readme_check import (
    ReadmeSectionsCheck,
    analyse,
    heading_lines,
    is_readme,
)
from engine.report import DatasetReport

_COMPLETE_MD = """# My dataset

## Dataset & file overview
Two CSV files of survey responses.

## File inventory & naming
- survey.csv
- codebook.csv

## Methodology
Collected by telephone in 2024.

## Missing-data codes
-999 means missing.

## Sharing, access & licensing
CC-BY-4.0.
"""

_SKELETON_MD = """# README

This dataset contains the files for the project.
"""

_PARTIAL_MD = """# README

## Dataset & file overview
Survey responses.

## File inventory
survey.csv and codebook.csv.
"""

_COMPLETE_TXT = """MY DATASET

DATASET AND FILE OVERVIEW
Two files.

FILE INVENTORY AND NAMING
survey.csv, codebook.csv.

METHODOLOGY
Telephone survey.

MISSING DATA CODES
-999 means missing.

SHARING, ACCESS AND LICENSING
CC-BY-4.0.
"""


def _run(tmp: str, name: str, text: str, ruleset=None):
    staged = Path(tmp)
    (staged / name).write_text(text, encoding="utf-8")
    files = sorted(p for p in staged.rglob("*") if p.is_file())
    return ReadmeSectionsCheck().run_dataset(files, {"ruleset": ruleset})


def test_is_readme_matches_common_names():
    assert is_readme(Path("README"))
    assert is_readme(Path("readme.md"))
    assert is_readme(Path("README_data.txt"))
    assert not is_readme(Path("read_me.md"))
    assert not is_readme(Path("codebook.md"))


def test_heading_lines_keeps_markdown_and_short_lines():
    lines = heading_lines("# Methods\n\nA sentence that ends with a period.\n\nAccess\n")
    assert "methods" in lines
    assert "access" in lines
    assert not any("period" in line for line in lines)


def test_complete_markdown_passes():
    with tempfile.TemporaryDirectory() as tmp:
        results = _run(tmp, "README.md", _COMPLETE_MD)
    result = results[0]
    assert result.passed
    assert result.level == "info"
    assert "all 5 standard sections" in result.message
    assert result.details["missing"] == []
    assert len(result.details["found"]) == 5


def test_complete_txt_passes():
    with tempfile.TemporaryDirectory() as tmp:
        results = _run(tmp, "README.txt", _COMPLETE_TXT)
    assert results[0].passed
    assert results[0].details["missing"] == []


def test_skeleton_warns_with_every_section_missing():
    with tempfile.TemporaryDirectory() as tmp:
        results = _run(tmp, "README.md", _SKELETON_MD)
    result = results[0]
    assert not result.passed
    assert result.level == "warning"
    assert len(result.details["missing"]) == 5
    assert result.details["sections"][0]["found"] is False


def test_partial_reports_found_and_missing():
    with tempfile.TemporaryDirectory() as tmp:
        results = _run(tmp, "README.md", _PARTIAL_MD)
    result = results[0]
    assert not result.passed
    found = {s["id"] for s in result.details["sections"] if s["found"]}
    assert found == {"overview", "files"}
    assert "Methodology" in result.details["missing"]
    assert "Dataset & file overview" not in result.details["missing"]


def test_optional_section_alone_does_not_fail():
    text = _COMPLETE_MD.replace("## Missing-data codes\n-999 means missing.\n", "")
    with tempfile.TemporaryDirectory() as tmp:
        results = _run(tmp, "README.md", text)
    result = results[0]
    assert result.passed
    assert result.details["missing"] == ["Missing-data codes"]
    assert result.details["missing_required"] == []


def test_check_without_readme_is_skipped_not_passed_silently():
    results = ReadmeSectionsCheck().run_dataset([Path("data.csv")], None)
    assert len(results) == 1
    assert results[0].passed
    assert results[0].details["skipped"] is True
    assert results[0].details["reason"] == "no README file"


def test_ruleset_can_override_sections():
    ruleset = {
        "section_rules": [
            {"id": "overview", "label": "Overview", "level": "required", "probes": ["overview"]},
            {
                "id": "ethics",
                "label": "Ethics statement",
                "level": "required",
                "probes": ["ethics"],
            },
        ]
    }
    with tempfile.TemporaryDirectory() as tmp:
        results = _run(tmp, "README.md", "# README\n\n## Overview\nText.\n", ruleset)
    assert results[0].details["missing"] == ["Ethics statement"]


def test_best_readme_wins():
    with tempfile.TemporaryDirectory() as tmp:
        staged = Path(tmp)
        (staged / "README.md").write_text(_SKELETON_MD, encoding="utf-8")
        (staged / "README.txt").write_text(_COMPLETE_TXT, encoding="utf-8")
        files = sorted(p for p in staged.rglob("*") if p.is_file())
        results = ReadmeSectionsCheck().run_dataset(files, None)
    assert results[0].passed
    assert results[0].details["readme"] == "README.txt"


def test_default_ruleset_exposes_section_rules():
    rs = rr.get_ruleset("mcmaster-default")
    sections = rr.readme_sections(rs)
    assert [s["id"] for s in sections] == ["overview", "files", "methods", "missing", "access"]
    assert rr.readme_sections({})[0]["id"] == "overview"


def test_response_letter_lists_missing_sections():
    with tempfile.TemporaryDirectory() as tmp:
        results = _run(tmp, "README.md", _PARTIAL_MD)
    report = DatasetReport(persistent_id="p", label="l", engine_version="t", dataset_checks=results)
    sections = collect_filecheck_sections(rr.get_ruleset("mcmaster-default"), report)
    assert len(sections) == 1
    message = sections[0]["message"]
    assert "missing these standard sections" in message
    assert "Methodology" in message
    assert "Dataset & file overview" not in message


def test_analyse_flags_unknown_sections_as_missing():
    report = analyse("", rr.readme_sections({}))
    assert len(report["missing"]) == 5
