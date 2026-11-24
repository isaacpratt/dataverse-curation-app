"""Cheap contract-edge tests for the engine (dv-3wd)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.checks import _util
from engine.checks.base import Check, CheckResult
from engine.report import DatasetReport, FileEntry
from engine.runner import run_report_to_file
from engine.verdict import Verdict, format_line


def test_report_format_branches(tmp_path: Path) -> None:
    ds = tmp_path / "ds"
    ds.mkdir()
    (ds / "a.txt").write_text("hello\n", encoding="utf-8")

    json_path = tmp_path / "out.json"
    run_report_to_file(ds, json_path, fmt="json", persistent_id="doi:1")
    assert json_path.exists()
    assert json.loads(json_path.read_text(encoding="utf-8"))["persistent_id"] == "doi:1"

    md_path = tmp_path / "out.md"
    run_report_to_file(ds, md_path, fmt="md")
    assert md_path.exists()
    assert md_path.read_text(encoding="utf-8").startswith("# Curation report")

    both = tmp_path / "both.json"
    run_report_to_file(ds, both, fmt="both")
    assert both.exists()
    assert both.with_suffix(".md").exists()


def test_report_from_dict_rejects_corrupt_payloads() -> None:
    with pytest.raises(ValueError, match="must be an object"):
        CheckResult.from_dict("bad")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="missing required field"):
        CheckResult.from_dict({"check_id": "x"})
    with pytest.raises(ValueError, match="details must be an object"):
        CheckResult.from_dict(
            {"check_id": "x", "level": "info", "passed": True, "message": "m", "details": []}
        )
    with pytest.raises(ValueError, match="must be an object"):
        FileEntry.from_dict("bad")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="invalid field"):
        FileEntry.from_dict({"path": "a", "size_bytes": "not a number"})
    with pytest.raises(ValueError, match="must be a list"):
        FileEntry.from_dict({"path": "a", "size_bytes": 1, "checks": {}})


def test_report_roundtrip_keeps_guidance_and_details() -> None:
    report = DatasetReport(
        "doi:1",
        "Roundtrip",
        "0",
        dataset_checks=[
            CheckResult(
                "format.csv",
                "error",
                False,
                "ragged rows",
                details={"extensions": ["csv"]},
                rationale="Why",
                remediation="How",
            )
        ],
        files=[FileEntry("a.csv", 5, "text/csv", [CheckResult("format.csv", "info", True, "ok")])],
    )
    restored = DatasetReport.from_dict(json.loads(json.dumps(report.to_dict())))
    assert restored.label == "Roundtrip"
    assert restored.dataset_checks[0].rationale == "Why"
    assert restored.files[0].checks[0].passed is True


def test_sqlite_uri_and_quoted_ident(tmp_path: Path) -> None:
    path = tmp_path / "a b.sqlite"
    assert _util.sqlite_uri(path).startswith("file:")
    assert "a%20b" in _util.sqlite_uri(path)
    assert _util.quoted_ident('a"b') == '"a""b"'


def test_guidance_and_verdict_fallbacks() -> None:
    from engine.checks.guidance import for_check, title_for

    rationale, remediation = for_check("unknown.check")
    assert isinstance(rationale, str)
    assert isinstance(remediation, str)
    assert title_for("unknown.check") == ""
    assert format_line(Verdict("ready")) == "ready"


def test_run_per_file_isolates_a_failing_check(tmp_path: Path) -> None:
    calls: list[str] = []

    class _Boom(Check):
        check_id = "test.boom"

    def _handler(path: Path) -> list[CheckResult]:
        calls.append(str(path))
        raise RuntimeError("kaboom")

    results = _util.run_per_file(_Boom(), [tmp_path / "a.txt"], _handler)
    assert len(calls) == 1
    assert results
    assert results[0].level == "error"
    assert "kaboom" in results[0].message


def test_verdict_unreviewed_without_signals() -> None:
    from engine.verdict import assess

    verdict = assess()
    assert verdict.level == "unreviewed"
    assert verdict.reasons == ()
