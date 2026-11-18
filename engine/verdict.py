"""Readiness verdict: one synthesized answer from the review signals.

Pure function of the data the dataset page already holds — the checks
report, the rule-completeness results, stored dispositions — no Qt, no
I/O, following the ui/workflow.py derivation pattern. The GUI renders
the Verdict as a banner with reason chips; headless runs print it; the
verdict is computed, never stored as truth.

Levels:
  unreviewed  nothing loaded yet (no report, no completeness results)
  ready       nothing outstanding
  revisions   outstanding warnings or incomplete metadata rules
  blocked     outstanding error-level findings (the deposit is unusable
              as-is) or a pending sensitivity review

Disposition semantics are duplicated from storage.py (engine stays
import-free of the app's local-state layer); test_dispositions and
test_verdict assert the two stay identical.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from engine.status import classify

LEVEL_READY = "ready"
LEVEL_REVISIONS = "revisions"
LEVEL_BLOCKED = "blocked"
LEVEL_UNREVIEWED = "unreviewed"

# Reason keys: stable identifiers the UI maps to copy + a scroll target.
REASON_REQUIRED = "required-missing"
REASON_OPTIONAL = "optional-missing"
REASON_ERRORS = "errors"
REASON_WARNINGS = "warnings"
REASON_SENSITIVITY = "sensitivity"

# Where each reason lives on the dataset page: a card attribute on the
# Review page, or the literal "respond" for the Response page.
REASON_TARGETS = {
    REASON_REQUIRED: "_meta_card",
    REASON_OPTIONAL: "_meta_card",
    REASON_ERRORS: "_auto_card",
    REASON_WARNINGS: "_auto_card",
    REASON_SENSITIVITY: "respond",
}

RESOLVED_DISPOSITIONS = frozenset({"acknowledged", "wontfix"})


def finding_key(check_id: str, path: str = "", message: str = "") -> str:
    """Mirror of storage.finding_key (kept identical; guard-tested)."""
    import hashlib

    normalized = " ".join(str(message or "").split())
    raw = "\x1f".join([str(check_id or ""), str(path or ""), normalized])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Reason:
    key: str
    count: int = 0
    target: str = ""


@dataclass(frozen=True)
class Verdict:
    level: str
    reasons: tuple[Reason, ...] = ()


def _disposition_of(dispositions: dict[str, Any] | None, key: str) -> str:
    try:
        return str((dispositions or {}).get(key, {}).get("disposition") or "")
    except Exception:
        return ""


def _is_resolved(dispositions: dict[str, Any] | None, key: str) -> bool:
    return _disposition_of(dispositions, key) in RESOLVED_DISPOSITIONS


def assess(  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
    report: Any = None,
    completeness: list[dict[str, Any]] | None = None,
    dispositions: dict[str, Any] | None = None,
    sensitivity: dict[str, Any] | None = None,
) -> Verdict:
    """Derive the verdict from in-memory review signals. Never raises.

    completeness: rule-evaluation rows (status, level, rule_id, field,
    requirement). dispositions: {finding_key: {disposition, note}} as
    stored by dv-32x; findings resolved by a disposition stop counting.
    sensitivity: optional {"complete": bool} — an incomplete review blocks.
    """
    try:
        has_report = report is not None
        # Synthesized "skipped" rows from include_unchecked carry no verdict;
        # a completeness list containing only those counts as unreviewed.
        evaluable = [
            r for r in (completeness or []) if isinstance(r, dict) and r.get("status") != "skipped"
        ]
        has_meta = bool(evaluable)
        if not has_report and not has_meta:
            return Verdict(LEVEL_UNREVIEWED)

        # Unresolved check findings (dataset-level and per-file).
        errors = warnings = 0
        if report is not None:
            try:
                entries = [(c, "") for c in list(getattr(report, "dataset_checks", None) or [])] + [
                    (c, str(getattr(f, "path", "") or ""))
                    for f in list(getattr(report, "files", None) or [])
                    for c in list(getattr(f, "checks", None) or [])
                ]
                for c, path in entries:
                    kind = classify(c)
                    if kind not in ("failed-error", "failed-warning"):
                        continue
                    key = finding_key(
                        str(getattr(c, "check_id", "") or ""),
                        path,
                        str(getattr(c, "message", "") or ""),
                    )
                    if _is_resolved(dispositions, key):
                        continue
                    if kind == "failed-error":
                        errors += 1
                    else:
                        warnings += 1
            except Exception:
                pass

        # Incomplete metadata rules, resolved ones discounted.
        # Synthesized "skipped" rows (unchecked rules) carry no verdict.
        required_missing = optional_missing = 0
        for r in evaluable:
            try:
                if not isinstance(r, dict):
                    continue
                if r.get("status") == "complete" or r.get("pending"):
                    continue
                rule_id = str(r.get("rule_id") or r.get("field") or "")
                message = str(r.get("requirement") or r.get("field") or "")
                if _is_resolved(dispositions, finding_key(rule_id, "", message)):
                    continue
                if str(r.get("level") or "required") == "required":
                    required_missing += 1
                else:
                    optional_missing += 1
            except Exception:
                continue

        sensitivity_pending = bool(
            isinstance(sensitivity, dict) and sensitivity.get("complete") is False
        )

        reasons: list[Reason] = []
        if errors:
            reasons.append(Reason(REASON_ERRORS, errors, REASON_TARGETS[REASON_ERRORS]))
        if required_missing:
            reasons.append(
                Reason(REASON_REQUIRED, required_missing, REASON_TARGETS[REASON_REQUIRED])
            )
        if warnings:
            reasons.append(Reason(REASON_WARNINGS, warnings, REASON_TARGETS[REASON_WARNINGS]))
        if optional_missing:
            reasons.append(
                Reason(REASON_OPTIONAL, optional_missing, REASON_TARGETS[REASON_OPTIONAL])
            )
        if sensitivity_pending:
            reasons.append(Reason(REASON_SENSITIVITY, 1, REASON_TARGETS[REASON_SENSITIVITY]))

        if errors or sensitivity_pending:
            level = LEVEL_BLOCKED
        elif warnings or required_missing or optional_missing:
            level = LEVEL_REVISIONS
        else:
            level = LEVEL_READY
        return Verdict(level, tuple(reasons))
    except Exception:
        return Verdict(LEVEL_UNREVIEWED)


def format_line(verdict: Verdict) -> str:
    """Render a machine-facing verdict summary for headless stdout.

    The catalogue's ``app.cli.verdict_line`` supplies "Verdict: ...".
    """
    if not verdict.reasons:
        return verdict.level
    return verdict.level + " — " + "; ".join(f"{r.key}:{r.count}" for r in verdict.reasons)
