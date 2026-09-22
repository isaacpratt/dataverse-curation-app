"""Shared result taxonomy: passed / warning / error / skipped.

Single source of truth for the tree view, Markdown export and headless
summaries. Wire-compatible: SKIPPED is warning+passed with
details.skipped=True (see _util.missing_library/skipped), so old payloads
without the flag keep their previous meaning.
"""

from engine.checks.base import CheckResult


def is_skipped(result: CheckResult) -> bool:
    try:
        return bool((result.details or {}).get("skipped"))
    except Exception:
        return False


def classify(result: CheckResult) -> str:
    """One of: passed | failed-error | failed-warning | skipped."""
    if is_skipped(result):
        return "skipped"
    if result.passed:
        return "passed"
    if result.level == "error":
        return "failed-error"
    return "failed-warning"


def summarize(results: list) -> dict:
    counts = {"passed": 0, "failed-error": 0, "failed-warning": 0, "skipped": 0}
    for result in results:
        counts[classify(result)] += 1
    counts["failed"] = counts["failed-error"] + counts["failed-warning"]
    counts["total"] = len(results)
    return counts


def file_status(checks: list) -> tuple[str, int]:
    """Aggregate label + rank for a file's checks.

    Rank (higher = worse): error(4) > warning-fail(3) > skipped-only(2) >
    clean(1) > unchecked/no-checks(0). Empty checks -> ("unchecked", 0).
    """
    if not checks:
        return ("unchecked", 0)
    kinds = {classify(c) for c in checks}
    if "failed-error" in kinds:
        return ("error", 4)
    if "failed-warning" in kinds:
        return ("warning", 3)
    if kinds == {"skipped"}:
        return ("skipped", 2)
    if kinds <= {"passed", "skipped"}:
        if "skipped" in kinds:
            return ("passed-skipped", 2)
        return ("clean", 1)
    return ("clean", 1)


def status_label(checks: list) -> str:
    """Human scan string for tree file nodes, e.g. 'Clean · 4 passed'."""
    if not checks:
        return "No automated check"
    summary = summarize(checks)
    label, _rank = file_status(checks)
    if label == "error":
        return f"Error · {summary['failed-error']} error(s), {summary['passed']} passed"
    if label == "warning":
        return f"Warning · {summary['failed-warning']} warning(s), {summary['passed']} passed"
    if label == "skipped":
        return f"Skipped · {summary['skipped']} skipped"
    if label == "passed-skipped":
        return f"Clean · {summary['passed']} passed, {summary['skipped']} skipped"
    return f"Clean · {summary['passed']} passed"
