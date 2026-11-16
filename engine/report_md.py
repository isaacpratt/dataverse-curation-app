"""Markdown rendering of a DatasetReport (derived view; JSON is canonical).

Pure function with no Qt or I/O: render_markdown(report) -> str.
Lists in details are capped at 10 items with "+n more", matching the engine
messages. Skipped results (details.skipped) render as Skipped, never Pass.
"""

from engine.report import DatasetReport
from engine.status import classify, summarize

_MAX_LISTED = 10


def _badge(result) -> str:
    kind = classify(result)
    if kind == "passed":
        return "PASS"
    if kind == "failed-error":
        return "FAIL"
    if kind == "failed-warning":
        return "WARN"
    return "SKIPPED"


def _fmt_value(value, depth: int = 0):
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


def _details_lines(details: dict) -> list[str]:
    lines = []
    for key in sorted(details):
        if key in ("skipped",):
            continue
        lines.append(f"  - `{key}`: {_fmt_value(details[key])}")
    return lines


def render_markdown(report: DatasetReport) -> str:
    lines: list[str] = []
    lines.append(f"# Curation report — {report.label}")
    lines.append("")
    lines.append(f"- Persistent ID: `{report.persistent_id}`")
    lines.append(f"- Generated: {report.timestamp} (engine {report.engine_version})")
    lines.append(f"- Files: {len(report.files)}")
    lines.append("")

    all_results = list(report.dataset_checks) + [c for f in report.files for c in f.checks]
    summary = summarize(all_results)
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Passed: {summary['passed']}")
    lines.append(f"- Warnings: {summary['failed-warning']}")
    lines.append(f"- Errors: {summary['failed-error']}")
    lines.append(f"- Skipped: {summary['skipped']}")
    unchecked = [c for c in report.dataset_checks if c.check_id == "inventory.unchecked_types"]
    if unchecked:
        lines.append(f"- Unchecked types: {unchecked[0].message}")
    lines.append("")

    lines.append("## Dataset checks")
    lines.append("")
    if report.dataset_checks:
        lines.append("| Check | Result | Message |")
        lines.append("| --- | --- | --- |")
        for result in report.dataset_checks:
            msg = result.message.replace("|", "\\|").replace("\n", " ")
            lines.append(f"| `{result.check_id}` | {_badge(result)} | {msg} |")
        lines.append("")
        for result in report.dataset_checks:
            sub = _details_lines(result.details or {})
            if sub:
                lines.append(f"### `{result.check_id}` details")
                lines.append("")
                lines.extend(sub)
                lines.append("")
    else:
        lines.append("No dataset-level checks ran.")
        lines.append("")

    lines.append("## Files")
    lines.append("")
    if not report.files:
        lines.append("No files staged.")
        lines.append("")
    by_dir: dict[str, list] = {}
    for entry in report.files:
        parent = entry.path.rpartition("/")[0] if "/" in entry.path else "."
        by_dir.setdefault(parent, []).append(entry)
    for parent in sorted(by_dir):
        if parent != ".":
            lines.append(f"### `{parent}/`")
            lines.append("")
        for entry in sorted(by_dir[parent], key=lambda e: e.path):
            entry_summary = summarize(entry.checks)
            if not entry.checks:
                state = "No automated check"
            elif entry_summary["failed-error"]:
                state = f"FAIL ({entry_summary['failed-error']} error(s))"
            elif entry_summary["failed-warning"]:
                state = f"WARN ({entry_summary['failed-warning']} warning(s))"
            elif entry_summary["skipped"] and not entry_summary["passed"]:
                state = "SKIPPED"
            else:
                state = f"PASS ({entry_summary['passed']} passed)"
            lines.append(
                f"#### `{entry.path}` — {entry_summary['total']} check(s), "
                f"{state} — {entry.size_bytes} bytes, {entry.mime_type}"
            )
            lines.append("")
            if not entry.checks:
                lines.append("Manual review required (no automated check for this format).")
                lines.append("")
                continue
            lines.append("| Check | Result | Message |")
            lines.append("| --- | --- | --- |")
            for result in entry.checks:
                msg = result.message.replace("|", "\\|").replace("\n", " ")
                lines.append(f"| `{result.check_id}` | {_badge(result)} | {msg} |")
            lines.append("")
            for result in entry.checks:
                sub = _details_lines(result.details or {})
                if sub:
                    lines.append(f"- `{result.check_id}`:")
                    lines.extend(sub)
            if any((c.details or {}) for c in entry.checks):
                lines.append("")

    missing = [
        (f.path, c.check_id, (c.details or {}).get("required", ""))
        for f in report.files
        for c in f.checks
        if classify(c) == "skipped" and (c.details or {}).get("required")
    ]
    if missing:
        lines.append("## Skipped (missing libraries)")
        lines.append("")
        for path, check_id, lib in missing:
            lines.append(f"- `{path}` `{check_id}`: install `{lib}` or use the full build")
        lines.append("")

    lines.append("---")
    lines.append(
        f"Generated by dataverse-curation-app engine {report.engine_version} — "
        "JSON is canonical; this Markdown is a derived view."
    )
    lines.append("")
    return "\n".join(lines)
