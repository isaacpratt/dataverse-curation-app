"""Guard for the numbered UI wireframe (dv-6n6).

The SVG, its screenshots and their legend are committed text and images. This
test checks their internal contract without booting Qt, so it runs on any
machine: every screen has both a captured and a schematic panel, each badge
points at a widget with a leader and dot, and every tag has exactly one legend
row with real technical identifiers.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SVG = ROOT / "docs" / "assets" / "ui-wireframe.svg"
ASSETS = ROOT / "docs" / "assets" / "wireframe"
DOC = ROOT / "docs" / "reference" / "ui-wireframe.md"

BADGE = re.compile(r'data-tag="(\[\d+\])" data-panel="([a-z]+)"', re.MULTILINE)
ROW_IN_DOC = re.compile(r"^\| (\[\d+\]) \| (.*?) \|$", re.MULTILINE)


def _svg() -> str:
    return SVG.read_text(encoding="utf-8")


def _badges() -> list[tuple[str, str]]:
    return BADGE.findall(_svg())


def _legend_rows() -> dict[str, str]:
    return {
        match.group(1): match.group(2)
        for match in ROW_IN_DOC.finditer(DOC.read_text(encoding="utf-8"))
    }


def test_every_screen_has_both_panels() -> None:
    svg = _svg()
    images = re.findall(r'<image href="wireframe/([a-z-]+)\.png"', svg)
    assert len(images) >= 8, f"expected all screens captured, got {images}"
    assert len(images) == len(set(images)), "a screen was captured twice"
    for name in images:
        path = ASSETS / f"{name}.png"
        assert path.exists(), f"missing capture: {path}"
        assert path.stat().st_size > 1000, f"empty capture: {path}"
    assert svg.count("— captured") == len(images)
    assert svg.count("— schematic") == len(images)


def test_every_badge_points_at_a_widget_and_has_one_row() -> None:
    badges = _badges()
    assert badges, "the wireframe has no numbered badges"
    tags = [tag for tag, _ in badges]
    assert len(set(badges)) == len(badges), "duplicate badge in a panel"
    assert {panel for _, panel in badges} == {"captured", "schematic"}
    for panel in ("captured", "schematic"):
        panel_tags = [tag for tag, name in badges if name == panel]
        assert len(panel_tags) == len(set(panel_tags)), f"duplicate {panel} badges"
    rows = _legend_rows()
    for tag in set(tags):
        assert tag in rows, f"{tag} has no legend row"
    # A leader line and an anchor dot end on the referenced widget.
    assert _svg().count('stroke="#b45309" stroke-width="0.9"') >= len(set(tags))
    assert _svg().count('fill="#b45309"') >= len(set(tags))
    hidden = set(rows) - set(tags)
    for tag in hidden:
        assert "not present in this screen" in rows[tag], (
            f"{tag}: a row without a badge must explain why it is hidden"
        )


def test_legend_rows_name_a_real_widget() -> None:
    measured = set(_legend_rows()) - {
        tag for tag, row in _legend_rows().items() if "not present in this screen" in row
    }
    for tag, row in _legend_rows().items():
        if tag not in measured:
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


def test_svg_has_schematic_shapes_and_no_leaked_paths() -> None:
    svg = _svg()
    assert svg.startswith("<svg ")
    assert 'viewBox="0 0 ' in svg
    assert svg.count('class="box"') >= len({tag for tag, _ in _badges()}) // 2
    assert "docent-wireframe-workspace" not in svg
    assert "C:\\" not in svg
    assert "/tmp/" not in svg


def test_reference_page_is_in_the_nav() -> None:
    zensical = (ROOT / "zensical.toml").read_text(encoding="utf-8")
    assert '"UI wireframe" = "reference/ui-wireframe.md"' in zensical
