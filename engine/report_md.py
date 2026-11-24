"""Markdown rendering of a DatasetReport (derived view; JSON is canonical).

Pure function with no Qt or I/O: render_markdown(report) -> str.
Lists in details are capped at 10 items with "+n more", matching the engine
messages. Skipped results (details.skipped) render as Skipped, never Pass.
"""

from typing import Any

from engine.report import DatasetReport
from engine.status import classify, summarize

_MAX_LISTED = 10


def _badge(result: Any) -> str:
    kind = classify(result)
    if kind == "passed":
        return "PASS"
    if kind == "failed-error":
        return "FAIL"
    if kind == "failed-warning":
        return "WARN"
    return "SKIPPED"


def _fmt_value(value: Any, depth: int = 0) -> str:
    if isinstance(value, dict):
        if not value:
            return "{}"
        items = list(value.items())[:_MAX_LISTED]
        inner = ", ".join(f"{k}: {_fmt_value(v, depth + 1)}" for k, v in items)
        extra = len(value) - len(items)
        if extra > 0:
            inner += f", +{extra} more"
        return "{" + inner + "}"
    if isinstance(value, (list, tuple)):
        items = list(value)[:_MAX_LISTED]
        inner = ", ".join(_fmt_value(v, depth + 1) for v in items)
        extra = len(value) - len(items)
        if extra > 0:
            inner += f", +{extra} more"
        return "[" + inner + "]"
    if isinstance(value, str) and len(value) > 200:
        return value[:200] + "…"
    return repr(value) if not isinstance(value, str) else value


def _details_lines(details: dict[str, Any]) -> list[str]:
    lines = []
    for key in sorted(details):
        if key in ("skipped",):
            continue
        lines.append(f"  - `{key}`: {_fmt_value(details[key])}")
    return lines


def _guidance_lines(result: Any) -> list[str]:
    """Why-this-matters / how-to-fix block for a failed result (dv-lfn)."""
    if classify(result) not in ("failed-error", "failed-warning"):
        return []
    from engine.checks.guidance import for_result

    rationale, remediation = for_result(result)
    lines: list[str] = []
    if rationale:
        lines.append(f"  - Why this matters: {rationale}")
    if remediation:
        lines.append(f"  - How to fix: {remediation}")
    return lines


def _header_lines(report: DatasetReport) -> list[str]:
    return [
        f"# Curation report — {report.label}",
        "",
        f"- Persistent ID: `{report.persistent_id}`",
        f"- Generated: {report.timestamp} (engine {report.engine_version})",
        f"- Files: {len(report.files)}",
        "",
    ]


def _summary_lines(report: DatasetReport) -> list[str]:
    all_results = list(report.dataset_checks) + [c for f in report.files for c in f.checks]
    summary = summarize(all_results)
    lines = [
        "## Summary",
        "",
        f"- Passed: {summary['passed']}",
        f"- Warnings: {summary['failed-warning']}",
        f"- Errors: {summary['failed-error']}",
        f"- Skipped: {summary['skipped']}",
    ]
    unchecked = [c for c in report.dataset_checks if c.check_id == "inventory.unchecked_types"]
    if unchecked:
        lines.append(f"- Unchecked types: {unchecked[0].message}")
    lines.append("")
    return lines


def _check_table(results: list[Any]) -> list[str]:
    lines = ["| Check | Result | Message |", "| --- | --- | --- |"]
    for result in results:
        msg = result.message.replace("|", "\\|").replace("\n", " ")
        lines.append(f"| `{result.check_id}` | {_badge(result)} | {msg} |")
    return lines


def _dataset_lines(report: DatasetReport) -> list[str]:
    lines = ["## Dataset checks", ""]
    if not report.dataset_checks:
        return ["No dataset-level checks ran.", ""]
    lines.extend(_check_table(report.dataset_checks))
    lines.append("")
    for result in report.dataset_checks:
        sub = _details_lines(result.details or {})
        guide = _guidance_lines(result)
        if sub or guide:
            lines.append(f"### `{result.check_id}` details")
            lines.append("")
            lines.extend(sub)
            lines.extend(guide)
            lines.append("")
    return lines


def _file_state(entry: Any, summary: dict[str, int]) -> str:
    if not entry.checks:
        return "No automated check"
    if summary["failed-error"]:
        return f"FAIL ({summary['failed-error']} error(s))"
    if summary["failed-warning"]:
        return f"WARN ({summary['failed-warning']} warning(s))"
    if summary["skipped"] and not summary["passed"]:
        return "SKIPPED"
    return f"PASS ({summary['passed']} passed)"


def _file_detail_lines(entry: Any) -> list[str]:
    lines: list[str] = []
    for result in entry.checks:
        sub = _details_lines(result.details or {})
        guide = _guidance_lines(result)
        if sub or guide:
            lines.append(f"- `{result.check_id}`:")
            lines.extend(sub)
            lines.extend(guide)
    if any((c.details or {}) for c in entry.checks) or any(
        classify(c) in ("failed-error", "failed-warning") for c in entry.checks
    ):
        lines.append("")
    return lines


def _file_lines(report: DatasetReport) -> list[str]:
    lines = ["## Files", ""]
    if not report.files:
        return ["No files staged.", ""]
    by_dir: dict[str, list[Any]] = {}
    for entry in report.files:
        parent = entry.path.rpartition("/")[0] if "/" in entry.path else "."
        by_dir.setdefault(parent, []).append(entry)
    for parent in sorted(by_dir):
        if parent != ".":
            lines.append(f"### `{parent}/`")
            lines.append("")
        for entry in sorted(by_dir[parent], key=lambda e: e.path):
            entry_summary = summarize(entry.checks)
            state = _file_state(entry, entry_summary)
            lines.append(
                f"#### `{entry.path}` — {entry_summary['total']} check(s), "
                f"{state} — {entry.size_bytes} bytes, {entry.mime_type}"
            )
            lines.append("")
            if not entry.checks:
                lines.append("Manual review required (no automated check for this format).")
                lines.append("")
                continue
            lines.extend(_check_table(entry.checks))
            lines.append("")
            lines.extend(_file_detail_lines(entry))
    return lines


def _skipped_lines(report: DatasetReport) -> list[str]:
    missing = [
        (f.path, c.check_id, (c.details or {}).get("required", ""))
        for f in report.files
        for c in f.checks
        if classify(c) == "skipped" and (c.details or {}).get("required")
    ]
    if not missing:
        return []
    lines = ["## Skipped (missing libraries)", ""]
    for path, check_id, lib in missing:
        lines.append(f"- `{path}` `{check_id}`: `{lib}` is not available in this build")
    lines.append("")
    return lines


def render_markdown(report: DatasetReport) -> str:
    lines: list[str] = []
    lines.extend(_header_lines(report))
    lines.extend(_summary_lines(report))
    lines.extend(_dataset_lines(report))
    lines.extend(_file_lines(report))
    lines.extend(_skipped_lines(report))
    lines.append("---")
    lines.append(
        "Generated by Dataverse Docent engine " + report.engine_version + " — "
        "JSON is canonical; this Markdown is a derived view."
    )
    lines.append("")
    return "\n".join(lines)
