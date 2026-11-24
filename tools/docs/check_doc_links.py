"""Offline link checker for the Markdown documentation tree.

Documentation as code means a broken link fails the build. Zensical's strict
build already catches broken links in published pages; this checker is the
offline, dependency-free companion used by ``poe docs-links``. It resolves
relative ``.md`` links and heading fragments without touching the network.
External URLs, mailto/tel/data links and code blocks are skipped.

Exit 0 when every internal link resolves, 1 when one is broken, 2 on a usage
error (the docs tree is missing).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

DOCS = Path(__file__).resolve().parents[2] / "docs"
SKIP = re.compile(r"^(?:https?://|mailto:|tel:|data:|javascript:|about:)", re.IGNORECASE)
LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
FENCE_RE = re.compile(r"^(```|~~~)")
HEADING_RE = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$")
INLINE_CODE_RE = re.compile(r"`[^`]*`")


def slugify(heading: str) -> str:
    """Return the anchor Python-Markdown gives a heading: lower-case, hyphenated."""
    heading = INLINE_CODE_RE.sub("", heading)
    heading = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", heading)
    heading = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading)
    heading = re.sub(r"<[^>]+>", "", heading)
    heading = heading.strip().lower()
    heading = re.sub(r"[^\w\s-]", "", heading, flags=re.UNICODE)
    return re.sub(r"\s+", "-", heading)


def anchors_in(path: Path) -> set[str]:
    """Heading anchors of one Markdown page, with ``-1``/``-2`` duplicates."""
    found: set[str] = set()
    counts: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = HEADING_RE.match(line)
        if not match:
            continue
        base = slugify(match.group(1))
        if not base:
            continue
        counts[base] = counts.get(base, 0) + 1
        found.add(base if counts[base] == 1 else f"{base}-{counts[base] - 1}")
    return found


def links_in(path: Path) -> list[str]:
    """Relative link targets in one Markdown page, ignoring code fences."""
    refs: list[str] = []
    in_fence = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if FENCE_RE.match(line.strip()):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        line = INLINE_CODE_RE.sub("", line)
        refs.extend(LINK_RE.findall(line))
    return refs


def check_docs(docs: Path = DOCS) -> list[str]:
    """Return one message per broken internal link or missing anchor."""
    broken: list[str] = []
    pages = sorted(docs.rglob("*.md"))
    for page in pages:
        for ref in links_in(page):
            if SKIP.match(ref):
                continue
            target_part, _, fragment = ref.partition("#")
            if not target_part:
                target = page
            else:
                target = (page.parent / target_part).resolve()
                if not target.exists():
                    broken.append(f"{page.relative_to(docs)}: missing file: {ref}")
                    continue
            if fragment and fragment not in anchors_in(target):
                broken.append(f"{page.relative_to(docs)}: missing anchor: {ref}")
    return broken


def main() -> int:
    """Check every Markdown page under docs/; exit 1 on any broken link."""
    if not DOCS.is_dir():
        print(f"docs-links: {DOCS} not found", file=sys.stderr)
        return 2
    broken = check_docs()
    if broken:
        print("docs-links: BROKEN links:")
        for line in broken:
            print(f"  {line}")
        return 1
    pages = len(list(DOCS.rglob("*.md")))
    print(f"docs-links: OK ({pages} Markdown files checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
