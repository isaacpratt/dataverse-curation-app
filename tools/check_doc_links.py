"""Offline link/anchor checker for docs/html/*.html.

No network: only local files and in-page anchors are verified. External
URLs, mailto/tel/data/javascript are skipped. Exit 1 when a broken
internal link or missing anchor is found.
"""

from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "docs" / "html"
ATTRS = ("href", "src")
SKIP = re.compile(r"^(?:https?://|mailto:|tel:|data:|javascript:|about:)", re.IGNORECASE)
ID_RE = re.compile(r"""\bid\s*=\s*[\"']([^\"']+)[\"']|\bname\s*=\s*[\"']([^\"']+)[\"']""")


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.refs: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name in ATTRS and value:
                self.refs.append((name, value.strip()))


def anchors_in(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    found: set[str] = set()
    for m in ID_RE.finditer(text):
        found.add(m.group(1) or m.group(2))
    return found


def main() -> int:
    if not DOCS.is_dir():
        print(f"docs-links: {DOCS} not found", file=sys.stderr)
        return 2

    broken: list[str] = []
    pages = sorted(DOCS.glob("*.html"))
    for page in pages:
        parser = LinkParser()
        parser.feed(page.read_text(encoding="utf-8", errors="ignore"))
        for _attr, ref in parser.refs:
            if SKIP.match(ref):
                continue
            target_part, _, fragment = ref.partition("#")
            target = (page.parent / target_part).resolve() if target_part else page
            if target_part and not target.exists():
                broken.append(f"{page.name}: missing file: {ref}")
                continue
            if fragment:
                try:
                    if fragment not in anchors_in(target):
                        broken.append(f"{page.name}: missing anchor: {ref}")
                except OSError:
                    broken.append(f"{page.name}: unreadable target: {ref}")

    if broken:
        print("docs-links: BROKEN links:")
        for line in broken:
            print(f"  {line}")
        return 1
    print(f"docs-links: OK ({len(pages)} pages checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
