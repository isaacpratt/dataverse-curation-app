"""Human-facing check names, verdict lines and prose tooltips (dv-r0z, dv-dcd).

A check is named once, in :data:`engine.checks.guidance.TITLES` beside its
curator guidance, so the File Manifest, the Auto-Checks card, the Markdown
report and the checks reference all say the same thing and the engine's
conformance test keeps the map complete. This module turns a
:class:`engine.checks.base.CheckResult` into the three pieces the interface
needs:

- :func:`check_title` — the name of the check (``CSV Openable``).
- :func:`check_summary` — one sentence saying what was verified, with the
  filename prefix the engine puts on every message stripped (the row already
  names the file).
- :func:`format_details_tooltip` — prose: name, state, sentence, the
  important details, and (for findings) why it matters / how to fix it.

The wording around those names lives in the strings catalogue, so this
module carries no interface copy of its own — ``ui/tests/test_strings.py``
enforces that, and it is why the titles sit in the engine rather than here.
"""

from __future__ import annotations

from typing import Any

from engine.checks.guidance import title_for
from ui.i18n import t

_EMPTY_DETAIL_KEYS = frozenset({"skipped", "reason", "required", "samples"})


def check_title(check_id: str) -> str:
    """Human name for a check id, e.g. ``CSV Openable``."""
    cid = str(check_id or "").strip()
    return title_for(cid) or t("checks.check_text.unknown_check", id=cid)


def _result_get(result: Any, key: str, default=None):
    if isinstance(result, dict):
        return result.get(key, default)
    try:
        return getattr(result, key, default)
    except Exception:
        return default


def _details(result: Any) -> dict[str, Any]:
    details = _result_get(result, "details", {})
    return details if isinstance(details, dict) else {}


def _base_name(path: str) -> str:
    text = str(path or "").strip()
    if not text:
        return ""
    return text.replace("\\", "/").rsplit("/", 1)[-1]


def strip_filename_prefix(message: str, path: str = "") -> str:
    """Drop the ``name.csv: `` prefix the engine puts on per-file messages."""
    text = str(message or "").strip()
    base = _base_name(path)
    if base and text.startswith(base + ": "):
        return text[len(base) + 2 :].strip()
    head, sep, tail = text.partition(": ")
    if sep and " " not in head:
        return tail.strip()
    return text


def check_summary(result: Any, path: str = "") -> str:
    """One sentence saying what the check found, without the filename."""
    text = strip_filename_prefix(str(_result_get(result, "message", "") or ""), path)
    text = " ".join(text.split())
    if not text:
        return t("common.em_dash")
    return text[:1].upper() + text[1:]


def check_state(result: Any) -> str:
    """Return the outcome in words: Complete / Needs attention / Skipped / Did not run."""
    details = _details(result)
    level = str(_result_get(result, "level", "") or "").lower()
    passed = bool(_result_get(result, "passed", True))
    if details.get("skipped"):
        return t("checks.check_text.state_skipped")
    if not passed and level in ("warning", "error"):
        return t("checks.check_text.state_attention")
    if passed:
        return t("checks.check_text.state_complete")
    return t("checks.check_text.state_not_run")


def _pretty_label(key: str) -> str:
    words = str(key).replace("_", " ").split()
    if not words:
        return str(key)
    return " ".join([words[0].capitalize(), *words[1:]])


def _render_value(value: Any) -> str:
    if isinstance(value, bool):
        return t("checks.check_text.yes") if value else t("checks.check_text.no")
    if isinstance(value, dict):
        pairs = [f"{k}: {v}" for k, v in list(value.items())[:6]]
        if len(value) > 6:
            pairs.append(t("checks.check_text.more_entries", count=len(value) - 6))
        return ", ".join(pairs)
    if isinstance(value, list):
        shown = ", ".join(str(item) for item in value[:6])
        if len(value) > 6:
            shown += " " + t("checks.check_text.more_entries", count=len(value) - 6)
        return shown
    if value is None:
        return t("checks.check_text.nothing")
    return str(value)


def detail_lines(result: Any, max_items: int = 8) -> list[str]:
    """Render the important ``details`` of a result, one readable line each."""
    out: list[str] = []
    for key, value in _details(result).items():
        if key in _EMPTY_DETAIL_KEYS:
            continue
        out.append(
            t(
                "checks.check_text.detail_line",
                label=_pretty_label(key),
                value=_render_value(value),
            )
        )
        if len(out) >= max_items:
            out.append(t("common.ellipsis"))
            break
    return out


def format_details_tooltip(result: Any, path: str = "") -> str:
    """Prose tooltip: never a raw id, never a JSON dump."""
    parts = [
        t(
            "checks.tooltip_head",
            title=check_title(str(_result_get(result, "check_id", "") or "")),
            state=check_state(result),
        )
    ]
    summary = check_summary(result, path)
    if summary != t("common.em_dash"):
        parts.append(summary)
    details = _details(result)
    if details.get("skipped"):
        reason = details.get("reason") or details.get("required") or ""
        if reason:
            parts.append(t("checks.skipped_reason", reason=reason))
    lines = detail_lines(result)
    if lines:
        parts.append("")
        parts.extend(lines)
    # Curator guidance (dv-lfn): why it matters, and what to do about it.
    from engine.status import classify

    if classify(result) in ("failed-error", "failed-warning"):
        from engine.checks.guidance import for_result

        rationale, remediation = for_result(result)
        if rationale:
            parts.append(t("checks.guidance_why", text=rationale))
        if remediation:
            parts.append(t("checks.guidance_fix", text=remediation))
    return "\n".join(parts)
