"""Front-matter and navigation invariants for the Diátaxis docs tree.

These are structural checks (the content of the pages is reviewed in PRs):
every published page declares one quadrant/governance type, names the TGDP
template it follows, and is reachable from the Zensical nav. Cheap, offline,
and deterministic — they run in the normal pytest suite.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
CONFIG = ROOT / "zensical.toml"

FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
FIELD = re.compile(r"^([a-z_]+):\s*(.+?)\s*$", re.MULTILINE)

ALLOWED_TYPES = {
    "tutorial",
    "how-to",
    "reference",
    "explanation",
    "troubleshooting",
    "home",
    "governance",
}
ALLOWED_TEMPLATES = {
    "Tutorial",
    "How-to",
    "Installation guide",
    "Reference",
    "Glossary",
    "Concept",
    "Explanation",
    "Troubleshooting",
    "Style guide",
    "Release notes",
    "Home",
    "README",
}


def _published_pages() -> list[Path]:
    """Markdown pages that the site builds (excluded folders omitted)."""
    pages = []
    for path in DOCS.rglob("*.md"):
        rel = path.relative_to(DOCS).as_posix()
        if rel.startswith(("adr/", "reports/", "html/", "proposals/")):
            continue
        pages.append(path)
    return sorted(pages)


def _front_matter(path: Path) -> dict[str, str]:
    match = FRONT_MATTER.match(path.read_text(encoding="utf-8"))
    assert match, f"{path.name}: missing YAML front matter"
    # Authors annotate the allowed values inline ("How-to  # ..."); YAML treats
    # everything after an unquoted " #" as a comment, so parse it the same way.
    return {name: value.split(" #", 1)[0].strip() for name, value in FIELD.findall(match.group(1))}


def test_every_published_page_declares_one_quadrant() -> None:
    pages = _published_pages()
    assert len(pages) >= 27, f"expected the full rewritten docs tree, found {len(pages)} pages"
    for path in pages:
        fields = _front_matter(path)
        page_type = fields.get("page_type", "")
        assert page_type in ALLOWED_TYPES, f"{path.name}: unknown page_type {page_type!r}"
        assert fields.get("tgdp_template", "") in ALLOWED_TEMPLATES, (
            f"{path.name}: unknown tgdp_template"
        )
        assert fields.get("audience", "") in {"curator", "developer", "contributor", "all"}, (
            f"{path.name}: unknown audience"
        )


def test_nav_lists_exactly_the_published_pages() -> None:
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    nav = config["project"]["nav"]

    def paths(entries: list[object]) -> list[str]:
        found: list[str] = []
        for entry in entries:
            if isinstance(entry, str):
                found.append(entry)
            elif isinstance(entry, dict):
                for value in entry.values():
                    found.extend(paths(value) if isinstance(value, list) else [str(value)])
        return found

    listed = paths(nav)
    assert len(listed) == len(set(listed)), "nav lists a page twice"
    on_disk = {p.relative_to(DOCS).as_posix() for p in _published_pages()}
    assert set(listed) == on_disk, (
        f"nav/file mismatch: missing from nav={sorted(on_disk - set(listed))}, "
        f"listed but absent={sorted(set(listed) - on_disk)}"
    )


def test_quadrant_audit_matches_front_matter() -> None:
    """The tracked quadrant audit must agree with the published pages."""
    audit = (DOCS / "reports" / "diataxis-audit.md").read_text(encoding="utf-8")
    rows = {}
    for line in audit.splitlines():
        if line.startswith("| `") and " | " in line:
            cells = [c.strip() for c in line.strip("|").split("|")]
            rows[cells[0].strip("`")] = cells[1:3]
    assert len(rows) >= 27, "the audit table is incomplete"

    for path in _published_pages():
        rel = path.relative_to(DOCS).as_posix()
        fields = _front_matter(path)
        assert rows.get(rel) == [fields["page_type"], fields["tgdp_template"]], (
            f"{rel}: audit says {rows.get(rel)}, front matter says "
            f"{[fields['page_type'], fields['tgdp_template']]}"
        )


def test_nav_is_grouped_by_quadrant() -> None:
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    groups: list[str] = []
    for entry in config["project"]["nav"]:
        if isinstance(entry, dict):
            groups.extend(entry.keys())
    assert groups[:5] == [
        "Home",
        "Tutorials",
        "How-to guides",
        "Reference",
        "Explanation",
    ], f"nav quadrants out of order: {groups}"
