"""README section-depth check (dv-81q).

Presence is already covered by the ruleset's ``readme-present`` content rule.
This dataset-level check asks the next question: does the README carry the
standard sections a reuser needs (overview, file inventory, methods,
missing-data codes, sharing/access)? Section rules live in
``review_rules.DEFAULT_README_SECTIONS`` and may be overridden per ruleset
with ``"section_rules": [...]``.

The check is pure over the staged file list the runner passes in; the
dataset's ruleset rides the runner context so a customized section list is
honoured headless too.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, ClassVar

from engine.checks.base import Check, CheckResult

MAX_READ_BYTES = 256 * 1024
README_RE = re.compile(r"^readme(?:[._-].*)?$", re.IGNORECASE)
# Lines longer than this are prose, never a heading.
_MAX_HEADING_WORDS = 10


def is_readme(path: Path) -> bool:
    return bool(README_RE.match(path.name))


def _read_text(path: Path) -> str | None:
    try:
        with open(path, "rb") as handle:
            raw = handle.read(MAX_READ_BYTES)
    except OSError:
        return None
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def heading_lines(text: str) -> list[str]:
    """Lowercased heading-ish lines: markdown headings + short standalone lines.

    Markdown headings (``#``) always count. A plain-text heading is a short
    line (at most ten words) that does not end like a sentence; this covers
    both ALL-CAPS and Title Case section titles in ``.txt`` READMEs.
    """
    out: list[str] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            title = line.lstrip("#").strip()
            if title:
                out.append(title.lower())
            continue
        if line[-1] in ".!?;,":
            continue
        if len(line.split()) > _MAX_HEADING_WORDS:
            continue
        out.append(line.lower())
    return out


def analyse(text: str, sections: list[dict[str, Any]]) -> dict[str, Any]:
    """Score one README against the section rules."""
    headings = heading_lines(text)
    rows: list[dict[str, Any]] = []
    for section in sections or []:
        probes = [str(p).lower() for p in (section.get("probes") or []) if str(p).strip()]
        found = any(probe in line for line in headings for probe in probes)
        rows.append(
            {
                "id": str(section.get("id") or ""),
                "label": str(section.get("label") or section.get("id") or ""),
                "level": str(section.get("level") or "required"),
                "found": found,
            }
        )
    missing = [r["label"] for r in rows if not r["found"]]
    missing_required = [r["label"] for r in rows if not r["found"] and r["level"] == "required"]
    return {
        "sections": rows,
        "found": [r["label"] for r in rows if r["found"]],
        "missing": missing,
        "missing_required": missing_required,
    }


class ReadmeSectionsCheck(Check):
    """Dataset-level check for whether the README is any good, not just present."""

    check_id = "metadata.readme_sections"
    extensions: ClassVar[set[str]] = set()  # dataset-level

    def run(self, files: list[Path]) -> list[CheckResult]:
        return self.run_dataset(files, context=None)

    def run_dataset(
        self, files: list[Path], context: dict[str, Any] | None = None
    ) -> list[CheckResult]:
        from curation.review_rules import readme_sections

        context = context or {}
        sections = readme_sections(context.get("ruleset"))
        candidates = [p for p in (files or []) if is_readme(p)]
        if not candidates:
            return [
                CheckResult(
                    check_id=self.check_id,
                    level="info",
                    passed=True,
                    message="No README file — section depth not assessed",
                    details={"skipped": True, "reason": "no README file"},
                )
            ]

        best: tuple[Path, dict[str, Any]] | None = None
        for path in candidates:
            text = _read_text(path)
            if text is None:
                continue
            report = analyse(text, sections)
            if best is None or len(report["found"]) > len(best[1]["found"]):
                best = (path, report)
        if best is None:
            return [
                CheckResult(
                    check_id=self.check_id,
                    level="info",
                    passed=True,
                    message="README could not be read — section depth not assessed",
                    details={"skipped": True, "reason": "unreadable README"},
                )
            ]

        path, report = best
        details: dict[str, Any] = {
            "readme": path.name,
            "sections": report["sections"],
            "found": report["found"],
            "missing": report["missing"],
            "missing_required": report["missing_required"],
        }
        total = len(report["sections"])
        if not report["missing"]:
            return [
                CheckResult(
                    check_id=self.check_id,
                    level="info",
                    passed=True,
                    message=f"README covers all {total} standard sections",
                    details=details,
                )
            ]
        missing = report["missing"]
        level = "warning" if report["missing_required"] else "info"
        return [
            CheckResult(
                check_id=self.check_id,
                level=level,
                passed=not report["missing_required"],
                message=(
                    f"README is missing {len(missing)} of {total} standard section(s): "
                    + ", ".join(missing)
                ),
                details=details,
            )
        ]
