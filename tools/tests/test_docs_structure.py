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
ALLOWED_AUDIENCES = {"curator", "developer", "contributor", "all"}
PYPROJECT = ROOT / "pyproject.toml"
STYLE_GUIDE = DOCS / "internal" / "style-guide.md"


def _published_pages() -> list[Path]:
    """Markdown pages that the site builds (excluded folders omitted)."""
    pages = []
    for path in DOCS.rglob("*.md"):
        rel = path.relative_to(DOCS).as_posix()
        if rel.startswith(("adr/", "internal/", "reports/", "html/", "proposals/")):
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
    assert len(pages) >= 15, f"expected the public curator docs tree, found {len(pages)} pages"
    for path in pages:
        fields = _front_matter(path)
        page_type = fields.get("page_type", "")
        assert page_type in ALLOWED_TYPES, f"{path.name}: unknown page_type {page_type!r}"
        assert fields.get("tgdp_template", "") in ALLOWED_TEMPLATES, (
            f"{path.name}: unknown tgdp_template"
        )
        assert fields.get("audience", "") in ALLOWED_AUDIENCES, f"{path.name}: unknown audience"


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


def test_style_guide_documents_every_value_the_gate_accepts() -> None:
    """The style guide's allowed-values table must not drift from the gate."""
    text = STYLE_GUIDE.read_text(encoding="utf-8")
    documented: dict[str, set[str]] = {}
    for line in text.splitlines():
        match = re.match(r"^\|\s+`([a-z_]+)`\s+\|\s+(.+?)\s+\|\s*$", line)
        if match:
            documented[match.group(1)] = set(re.findall(r"`([^`]+)`", match.group(2)))

    used: dict[str, set[str]] = {"page_type": set(), "tgdp_template": set(), "audience": set()}
    for page in _published_pages():
        fields = _front_matter(page)
        for key in used:
            used[key].add(fields[key])

    for key, accepted in (
        ("page_type", ALLOWED_TYPES),
        ("tgdp_template", ALLOWED_TEMPLATES),
        ("audience", ALLOWED_AUDIENCES),
    ):
        assert documented.get(key), f"style-guide.md: no allowed-values row for {key}"
        assert documented[key] <= accepted, f"style-guide.md advertises invalid {key} values"
        assert used[key] <= documented[key], (
            f"style-guide.md omits {key} values used by pages: {sorted(used[key] - documented[key])}"
        )


def test_documented_poe_tasks_exist() -> None:
    """Every `poe <task>` quoted in the docs is a real task in pyproject.toml."""
    tasks = set(tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["tool"]["poe"]["tasks"])
    pages = [*_published_pages(), ROOT / "CONTRIBUTING.md"]
    # Prose such as "poe is the task runner" is not a command; skip those words.
    prose = {"is", "task", "tasks", "and", "the", "as", "for"}
    mentioned: dict[str, str] = {}
    for page in pages:
        for match in re.finditer(r"\bpoe\s+([a-z][a-z0-9-]*)\b", page.read_text(encoding="utf-8")):
            if match.group(1) not in prose:
                mentioned.setdefault(match.group(1), page.relative_to(ROOT).as_posix())
    assert mentioned
    missing = {task: source for task, source in mentioned.items() if task not in tasks}
    assert not missing, f"documented poe tasks that do not exist: {missing}"


def test_nav_is_grouped_by_quadrant() -> None:
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    groups: list[str] = []
    for entry in config["project"]["nav"]:
        if isinstance(entry, dict):
            groups.extend(entry.keys())
    assert groups[:4] == [
        "Home",
        "Tutorials",
        "How-to guides",
        "Reference",
    ], f"nav quadrants out of order: {groups}"
    assert "Explanation" not in groups, "explanation pages are internal, not published"
