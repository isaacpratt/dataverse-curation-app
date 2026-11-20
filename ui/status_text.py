"""Display strings for check results (kept out of the engine taxonomy).

``engine.status`` owns the PASS/WARN/FAIL/SKIPPED classification and remains
the source of truth for the report and headless output.  The GUI needs the
same taxonomy rendered as interface copy, so this module maps the stable
classifier keys onto catalogue entries instead of reading the engine's
English labels back as if they were data.
"""

from __future__ import annotations

from typing import Any

from engine.checks.base import CheckResult
from engine.status import classify, file_status, summarize
from ui.i18n import t

__all__ = ["badge_text", "status_text"]

_BADGE_KEYS = {
    "passed": "status.badges.passed",
    "failed-warning": "status.badges.warning",
    "failed-error": "status.badges.error",
    "skipped": "status.badges.skipped",
}


def badge_text(result: CheckResult) -> str:
    """Short badge in the Scan column: PASS / WARN / FAIL / SKIPPED."""
    return t(_BADGE_KEYS.get(classify(result), "status.badges.passed"))


def status_text(checks: list[Any]) -> str:
    """Human scan string for a file row, e.g. ``Clean · 4 passed``."""
    if not checks:
        return t("status.no_automated")
    summary = summarize(checks)
    label, _rank = file_status(checks)
    if label == "error":
        return t(
            "status.summary.error",
            errors=summary["failed-error"],
            passed=summary["passed"],
        )
    if label == "warning":
        return t(
            "status.summary.warning",
            warnings=summary["failed-warning"],
            passed=summary["passed"],
        )
    if label == "skipped":
        return t("status.summary.skipped", skipped=summary["skipped"])
    if label == "passed-skipped":
        return t(
            "status.summary.passed_skipped",
            passed=summary["passed"],
            skipped=summary["skipped"],
        )
    return t("status.summary.clean", passed=summary["passed"])
