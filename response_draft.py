"""Assemble the depositor response draft from rule findings + file checks.

Pure functions (no Qt / I/O): the Response pane calls `build_response` after
every metadata load / check run, and `render_response` whenever the curator
toggles findings in/out. Placeholders supported in every template:

  {field} {rule_label} {value} {message} {path} {check_id}
  {dataset_title} {persistent_id}
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple


def _fmt(template: str, ctx: Dict[str, Any]) -> str:
    try:
        return str(template or "").format_map(_SafeDict(ctx))
    except Exception:
        return str(template or "")


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _is_skipped(result: Any) -> bool:
    try:
        return bool((getattr(result, "details", None) or {}) .get("skipped"))
    except Exception:
        try:
            return bool((result.get("details") or {}).get("skipped"))
        except Exception:
            return False


def collect_metadata_sections(ruleset: Dict[str, Any],
                               completeness: List[Dict[str, Any]],
                               dataset_title: str = "",
                               persistent_id: str = "") -> List[Dict[str, Any]]:
    """One section per incomplete, non-pending rule finding."""
    sections: List[Dict[str, Any]] = []
    for r in completeness or []:
        try:
            if not isinstance(r, dict):
                continue
            if r.get("status") == "complete" or r.get("pending"):
                continue
            label = str(r.get("field") or r.get("rule_id") or "Item")
            template = str(r.get("response_template") or "")
            if not template:
                template = "Please address {field}: current value is '{value}'."
            ctx = {
                "field": label, "rule_label": label,
                "value": str(r.get("value") or "—"),
                "message": str(r.get("value") or "—"),
                "dataset_title": dataset_title, "persistent_id": persistent_id,
            }
            sections.append({
                "id": str(r.get("rule_id") or label),
                "kind": "metadata",
                "label": label,
                "level": str(r.get("level") or "required"),
                "requirement": str(r.get("requirement") or ""),
                "message": _fmt(template, ctx),
                "template": template,
                "included": True,
            })
        except Exception:
            continue
    return sections


def collect_filecheck_sections(ruleset: Dict[str, Any], report: Any) -> List[Dict[str, Any]]:
    """One section per failed warning/error file or dataset check."""
    sections: List[Dict[str, Any]] = []
    if report is None:
        return sections
    templates = {}
    try:
        templates = dict((ruleset or {}).get("filecheck_templates") or {})
    except Exception:
        templates = {}
    fallback = str(templates.get("*") or "{check_id}: {message}")

    def _one(check_id: str, level: str, message: str, path: str) -> None:
        template = str(templates.get(check_id) or fallback)
        ctx = {"check_id": check_id, "message": message, "path": path or "dataset"}
        rendered = _fmt(template, ctx)
        if "{path}" not in template and path:
            rendered = f"{rendered} (file: {path})" if not rendered.endswith(f"({path})") else rendered
        sections.append({
            "id": f"filecheck:{check_id}:{path}",
            "kind": "filecheck",
            "label": f"{check_id} — {path or 'dataset'}",
            "level": "error" if level == "error" else "warning",
            "requirement": f"Automated check {check_id} ({level})",
            "message": rendered,
            "template": template,
            "included": True,
        })

    try:
        for c in list(getattr(report, "dataset_checks", None) or []):
            try:
                if getattr(c, "passed", True) or _is_skipped(c):
                    continue
                if str(getattr(c, "level", "")) not in ("warning", "error"):
                    continue
                _one(str(c.check_id), str(c.level), str(c.message), "")
            except Exception:
                continue
        for f in list(getattr(report, "files", None) or []):
            try:
                path = str(getattr(f, "path", "") or "")
                for c in list(getattr(f, "checks", None) or []):
                    try:
                        if getattr(c, "passed", True) or _is_skipped(c):
                            continue
                        if str(getattr(c, "level", "")) not in ("warning", "error"):
                            continue
                        _one(str(c.check_id), str(c.level), str(c.message), path)
                    except Exception:
                        continue
            except Exception:
                continue
    except Exception:
        pass
    return sections


def _severity_tag(level: str) -> str:
    """Human severity label for a section level ('' when not a warning)."""
    l = str(level or "").lower()
    if l == "error":
        return "Error"
    if l == "warning":
        return "Warning"
    if l == "required":
        return "Required"
    if l in ("optional", "recommended"):
        return "Recommended"
    return ""


def render_response(ruleset: Dict[str, Any],
                    sections: List[Dict[str, Any]],
                    dataset_title: str = "",
                    persistent_id: str = "") -> str:
    """Markdown draft from header + included sections + footer.

    Every included item carries its severity up front (e.g. **Warning:**)
    so warnings/errors read at a glance — file-check severities come from
    the run, metadata severities from the active ruleset.
    """
    try:
        header = _fmt(str((ruleset or {}).get("response_header") or ""),
                      {"dataset_title": dataset_title, "persistent_id": persistent_id})
        footer = _fmt(str((ruleset or {}).get("response_footer") or ""),
                      {"dataset_title": dataset_title, "persistent_id": persistent_id})
    except Exception:
        header, footer = "", ""
    lines: List[str] = []
    if header.strip():
        lines += [header.strip(), ""]
    included = [s for s in (sections or []) if isinstance(s, dict) and s.get("included")]
    if not included:
        lines += ["No outstanding items — the dataset looks ready for the next step.", ""]
    else:
        for i, s in enumerate(included, 1):
            try:
                msg = str(s.get("message") or "").strip()
                tag = _severity_tag(str(s.get("level") or ""))
                lines.append(f"{i}. **{tag}:** {msg}" if tag else f"{i}. {msg}")
            except Exception:
                continue
        lines.append("")
    if footer.strip():
        lines += [footer.strip(), ""]
    return "\n".join(lines).strip() + "\n"


def build_response(ruleset: Dict[str, Any],
                   completeness: List[Dict[str, Any]] | None,
                   report: Any = None,
                   dataset_title: str = "",
                   persistent_id: str = "") -> Tuple[str, List[Dict[str, Any]]]:
    """Assemble sections + rendered markdown. Never raises."""
    try:
        sections = collect_metadata_sections(ruleset or {}, completeness or [],
                                             dataset_title, persistent_id)
        sections += collect_filecheck_sections(ruleset or {}, report)
        return render_response(ruleset or {}, sections, dataset_title, persistent_id), sections
    except Exception:
        return "", []
