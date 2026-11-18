"""Variable-metadata coverage (dv-tfy): dataset-level check + dictionary draft.

The check is pure: it reads the runner context — the same inventory the
access check consumes, plus ``variable_metadata`` (path -> {name:
{label, type}}) fetched by the UI from Dataverse's per-file DDI. Missing
context degrades to a skipped result (always-emit), never a silent pass.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, ClassVar

from engine.checks.base import Check, CheckResult

_MAX_LISTED = 5


def coverage_of(variables: dict[str, dict[str, str]] | None) -> tuple[int, int] | None:
    """(labeled, total) for one variable map; None when unknown."""
    if not isinstance(variables, dict) or not variables:
        return None
    total = len(variables)
    labeled = sum(
        1
        for meta in variables.values()
        if isinstance(meta, dict) and str(meta.get("label") or "").strip()
    )
    return (labeled, total)


def _pct(labeled: int, total: int) -> int:
    return round(100 * labeled / total) if total else 0


class VarCoverageCheck(Check):
    """Dataset-level check for whether a stranger can tell what each variable means."""

    check_id = "metadata.var_coverage"
    extensions: ClassVar[set[str]] = set()  # dataset-level

    def run(self, files: list[Path]) -> list[CheckResult]:
        return self.run_dataset(files, context=None)

    def run_dataset(
        self, files: list[Path], context: dict[str, Any] | None = None
    ) -> list[CheckResult]:
        context = context or {}
        inventory = context.get("inventory")
        variable_metadata = context.get("variable_metadata")
        if not isinstance(inventory, list):
            return [
                CheckResult(
                    check_id=self.check_id,
                    level="info",
                    passed=True,
                    message="variable-metadata coverage skipped (no inventory)",
                    details={"skipped": True, "required": "inventory"},
                )
            ]
        tabular = [e for e in inventory if isinstance(e, dict) and e.get("tabular")]
        if not tabular:
            return [
                CheckResult(
                    check_id=self.check_id,
                    level="info",
                    passed=True,
                    message="No tabular files — variable-metadata coverage not applicable",
                    details={"tabular_files": 0},
                )
            ]

        results: list[CheckResult] = []
        undocumented: list[str] = []
        partial: list[str] = []
        covered = 0
        coverage_map: dict[str, dict[str, int]] = {}
        variables_map: dict[str, dict[str, dict[str, str]]] = {}
        for entry in tabular:
            path = str(entry.get("path") or entry.get("label") or "")
            variables = variable_metadata.get(path) if isinstance(variable_metadata, dict) else None
            cov = coverage_of(variables)
            if cov is None:
                undocumented.append(path)
                continue
            labeled, total = cov
            coverage_map[path] = {"labeled": labeled, "total": total}
            # Full name -> {label, type} so the dictionary draft works
            # offline from the saved report; capped to bound report size.
            variables_map[path] = {
                str(name): {
                    "label": str((meta or {}).get("label") or ""),
                    "type": str((meta or {}).get("type") or ""),
                }
                for name, meta in list((variables or {}).items())[:500]
                if isinstance(meta, dict)
            }
            pct = _pct(labeled, total)
            if total and labeled == 0:
                undocumented.append(path)
            elif pct < 50:
                partial.append(f"{path} ({pct}%)")
                covered += 1
            else:
                covered += 1

        if tabular and covered == 0 and not undocumented:
            undocumented = [str(e.get("path") or "") for e in tabular]

        if undocumented:
            results.append(
                CheckResult(
                    check_id=self.check_id,
                    level="warning",
                    passed=False,
                    message=(
                        f"{len(undocumented)} tabular file(s) without variable "
                        "documentation: " + ", ".join(undocumented[:_MAX_LISTED])
                    ),
                    details={
                        "count": len(undocumented),
                        "files": undocumented[:_MAX_LISTED],
                    },
                )
            )
        else:
            results.append(
                CheckResult(
                    check_id=self.check_id,
                    level="info",
                    passed=True,
                    message=(f"Variable documentation present for all {covered} tabular file(s)"),
                    details={"tabular_files": covered},
                )
            )
        if partial:
            results.append(
                CheckResult(
                    check_id=self.check_id,
                    level="warning",
                    passed=False,
                    message=(
                        f"{len(partial)} tabular file(s) with under half the variables "
                        "labeled: " + ", ".join(partial[:_MAX_LISTED])
                    ),
                    details={
                        "count": len(partial),
                        "files": partial[:_MAX_LISTED],
                    },
                )
            )
        # Per-file coverage and the labels themselves ride on the first
        # result so the manifest can annotate file nodes and the dictionary
        # draft works offline from a saved report.
        results[0].details["coverage"] = coverage_map
        results[0].details["variables"] = variables_map
        return results


# -- dictionary draft ------------------------------------------------------

DRAFT_COLUMNS = ("variable", "label", "type")


def write_dictionary_draft(path: Path, variables: dict[str, dict[str, str]]) -> Path:
    """Write a HEAL-vlmd-shaped CSV draft (name + description minimum).

    Rows: one per variable (name, label, type). Curators hand the draft to
    the depositor to complete; filling the labels makes the coverage
    check pass.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(DRAFT_COLUMNS)
        for name, meta in sorted((variables or {}).items()):
            meta = meta if isinstance(meta, dict) else {}
            writer.writerow([name, str(meta.get("label") or ""), str(meta.get("type") or "")])
    return path
