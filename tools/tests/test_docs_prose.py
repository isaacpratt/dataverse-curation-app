"""Minimal prose checks for the published documentation (Vale without Vale).

This repo is uv-only, so the house style rules from ``docs/style-guide.md`` are
checked in Python rather than by adding a Go linter. The rules here are small
and deterministic on purpose: banned filler words, first person, undated or
stale verification claims, and backticked repository paths that no longer
exist. Content accuracy still needs human review.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"

BANNED = re.compile(r"\b(just|simply|obviously|easy)\b", re.IGNORECASE)
FIRST_PERSON = re.compile(r"\b(we|our)\b|\bI\b(?![/A-Za-z])")
VERIFICATION_CLAIM = re.compile(
    r"\b(live-verified|verified against|verification snapshot|as of)\b", re.IGNORECASE
)
YEAR = re.compile(r"\b(19|20)\d{2}\b")
PATH = re.compile(r"[A-Za-z0-9_./-]+\.(?:py|json|toml|md|yml|yaml)\b")
# Paths the docs mean as repository files; bare filenames and runtime files
# (config.json, state.db, dist/…, …/<placeholder>) are not checked here.
REPO_PREFIXES = (
    "engine/",
    "curation/",
    "ui/",
    "tools/",
    "docs/",
    ".github/",
    "pyproject.toml",
    "zensical.toml",
    ".pymarkdown.json",
    "config.example.json",
    "README.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    "SECURITY.md",
    "AGENTS.md",
)


def _published_pages() -> list[Path]:
    pages = []
    for path in DOCS.rglob("*.md"):
        rel = path.relative_to(DOCS).as_posix()
        if rel.startswith(("adr/", "reports/", "proposals/")):
            continue
        pages.append(path)
    return sorted(pages)


def _pages_and_lines(skip: set[str] | None = None) -> Iterator[tuple[str, int, str]]:
    for page in _published_pages():
        rel = page.relative_to(DOCS).as_posix()
        if skip and rel in skip:
            continue
        for number, line in enumerate(page.read_text(encoding="utf-8").splitlines(), 1):
            yield rel, number, line


def test_no_filler_words() -> None:
    """The style guide defines these words; it is allowed to quote them."""
    offenders = [
        f"{page}:{number}: {line.strip()[:100]}"
        for page, number, line in _pages_and_lines(skip={"style-guide.md"})
        if BANNED.search(line)
    ]
    assert not offenders, f"filler words in docs: {offenders}"


def test_no_first_person_narration() -> None:
    """Docs address the reader as 'you', even in explanation pages."""
    offenders = [
        f"{page}:{number}: {line.strip()[:100]}"
        for page, number, line in _pages_and_lines()
        if FIRST_PERSON.search(line) and not line.strip().startswith("| I want to")
    ]
    assert not offenders, f"first-person prose in docs: {offenders}"


def test_verification_claims_are_dated_and_recent() -> None:
    """A 'verified' claim needs a year, and old observations need a warning."""
    current = datetime.now().year
    offenders = []
    for page, number, line in _pages_and_lines():
        if not VERIFICATION_CLAIM.search(line):
            continue
        years = [int(match.group(0)) for match in YEAR.finditer(line)]
        if not years:
            offenders.append(f"{page}:{number}: undated claim: {line.strip()[:100]}")
        elif max(years) < current - 2:
            offenders.append(f"{page}:{number}: stale claim ({max(years)}): {line.strip()[:100]}")
    assert not offenders, f"verification claims need a recent date: {offenders}"


def test_cited_repository_paths_exist() -> None:
    """A backticked repo path in a published page must resolve on disk."""
    missing = set()
    for _page, _number, line in _pages_and_lines():
        for span in re.findall(r"`([^`]+)`", line):
            if "://" in span or "<" in span or "*" in span:
                continue
            for candidate in PATH.findall(span):
                if not candidate.startswith(REPO_PREFIXES) or candidate.startswith("../"):
                    continue
                if not (ROOT / candidate).exists():
                    missing.add(candidate)
    assert not missing, f"documented repository paths that do not exist: {sorted(missing)}"
