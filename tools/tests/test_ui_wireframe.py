"""Guard for the numbered UI wireframe (dv-6n6).

The SVG and its legend are committed text. This test checks their internal
contract without booting Qt, so it runs on any machine: every numbered badge
has exactly one legend row with real technical identifiers, tags are unique,
and the static state/constraint tables the diagram depends on are present.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SVG = ROOT / "docs" / "assets" / "ui-wireframe.svg"
DOC = ROOT / "docs" / "reference" / "ui-wireframe.md"

TAG_IN_SVG = re.compile(r'data-tag="(\[\d+\])"')
ROW_IN_DOC = re.compile(r"^\| (\[\d+\]) \| (.*?) \|$", re.MULTILINE)


def _svg_tags() -> list[str]:
    return TAG_IN_SVG.findall(SVG.read_text(encoding="utf-8"))


def _legend_rows() -> dict[str, str]:
    return {
        match.group(1): match.group(2)
        for match in ROW_IN_DOC.finditer(DOC.read_text(encoding="utf-8"))
    }


def test_every_badge_has_one_unique_legend_row() -> None:
    tags = _svg_tags()
    assert tags, "the wireframe has no numbered badges"
    assert len(tags) == len(set(tags)), f"duplicate badges: {sorted(tags)}"
    rows = _legend_rows()
    for tag in tags:
        assert tag in rows, f"{tag} has no legend row"
    # Tags follow registry order; a conditional widget that is hidden in the
    # capture keeps its number in the legend but has no badge in the SVG.
    assert tags == sorted(tags)
    hidden = set(rows) - set(tags)
    for tag in hidden:
        assert "not present in this screen" in rows[tag], (
            f"{tag}: a row without a badge must explain why it is hidden"
        )


def test_legend_rows_name_a_real_widget() -> None:
    # Only badges that actually appear in the SVG are required to name a
    # measured widget; hidden conditional rows are documented separately.
    for tag, row in _legend_rows().items():
        if tag not in set(_svg_tags()):
            continue
        cells = [cell.strip() for cell in row.split("|")]
        assert len(cells) >= 8, f"{tag}: too few columns ({row})"
        class_name, object_name, layout, size_policy = cells[2:6]
        assert class_name, f"{tag}: missing Qt class"
        assert class_name != "—", f"{tag}: missing Qt class"
        assert object_name.startswith("`"), f"{tag}: objectName must be a code span"
        assert object_name.endswith("`"), f"{tag}: objectName must be a code span"
        assert layout != "—" or size_policy != "—", f"{tag}: no layout or size policy"


def test_states_and_constraints_are_documented() -> None:
    text = DOC.read_text(encoding="utf-8")
    for heading in ("## Non-visible states", "## Bounding-box constraints"):
        assert heading in text
    states = text.split("## Non-visible states", 1)[1].split("##", 1)[0]
    for state in ("Loading", "Empty", "Error", "Disabled", "Hover / focus"):
        assert state in states, f"missing state column: {state}"
    constraints = text.split("## Bounding-box constraints", 1)[1]
    for constraint in ("Fixed dimensions", "Size policy", "Overflow rule", "Stacking"):
        assert constraint in constraints, f"missing constraint: {constraint}"
    for selector in ("#TopNav", "#WorkflowRail", "#DetailSideContainer"):
        assert selector in constraints, f"missing constraint for {selector}"


def test_svg_has_proportional_boxes_and_no_leaked_paths() -> None:
    svg = SVG.read_text(encoding="utf-8")
    assert svg.startswith("<svg ")
    assert 'viewBox="0 0 ' in svg
    assert svg.count('class="box') == len(_svg_tags())
    assert "docent-wireframe-workspace" not in svg
    assert "C:\\" not in svg
    assert "/tmp/" not in svg


def test_reference_page_is_in_the_nav() -> None:
    zensical = (ROOT / "zensical.toml").read_text(encoding="utf-8")
    assert '"UI wireframe" = "reference/ui-wireframe.md"' in zensical
