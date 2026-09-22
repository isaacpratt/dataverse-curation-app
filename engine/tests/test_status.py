"""Tests for the shared result taxonomy (engine.status)."""

from engine.checks._util import missing_library, skipped
from engine.checks.base import CheckResult
from engine.status import classify, file_status, status_label, summarize


def _info(check_id="format.csv.pii"):
    return CheckResult(check_id=check_id, level="info", passed=True, message="ok")


def _warn(check_id="format.csv.pii"):
    return CheckResult(check_id=check_id, level="warning", passed=False, message="issue")


def _err(check_id="format.csv.openable"):
    return CheckResult(check_id=check_id, level="error", passed=False, message="bad")


def test_classify_skipped_wins():
    assert classify(missing_library("format.xlsx.openable", "openpyxl")) == "skipped"
    assert classify(skipped("format.csv.pii", "n/a")) == "skipped"
    assert classify(_info()) == "passed"
    assert classify(_warn()) == "failed-warning"
    assert classify(_err()) == "failed-error"


def test_summarize_counts():
    summary = summarize([_info(), _warn(), _err(), missing_library("x", "y")])
    assert summary["passed"] == 1
    assert summary["failed-warning"] == 1
    assert summary["failed-error"] == 1
    assert summary["skipped"] == 1
    assert summary["failed"] == 2


def test_file_status_rank():
    assert file_status([]) == ("unchecked", 0)
    assert file_status([_info()])[0] == "clean"
    assert file_status([_warn()])[0] == "warning"
    assert file_status([_err()])[0] == "error"
    assert file_status([missing_library("x", "y")])[0] == "skipped"
    assert file_status([_info(), missing_library("x", "y")])[0] == "passed-skipped"


def test_status_label_mentions_counts():
    assert "4 passed" in status_label([_info(), _info(), _info(), _info()])
    assert status_label([]) == "No automated check"
    assert status_label([missing_library("x", "y")]).startswith("Skipped")
