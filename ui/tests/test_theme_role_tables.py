"""Contract: the role layer is a table per theme, not a pile of aliases.

The palette says what a colour IS; the role says what it is FOR. Dark
mode is planned in five steps, and this is step one: the role layer is
a mapping, so a theme change is a table swap rather than a re-skin of
every view.

These tests hold that contract:

* the light table is exactly what the app paints today (the existing
  mappings did not move);
* both tables declare the same role names, so a swap cannot miss one;
* the same role resolves to the light surface's ink in light and to the
  dark surface's ink in dark;
* the dark table is legible on its own surfaces (the pairs the app
  actually paints clear their WCAG floors);
* the live role table is named in the Log.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from ui import theme
from ui.theme import contrast_ratio

_THEME_PATH = pathlib.Path(theme.__file__).resolve()
_ROLE_MARKER = "# --- Semantic roles: what a colour is FOR"

# The role names the app paints, in the order the theme declares them.
_ROLE_NAMES = theme._ROLE_NAMES

# The pairs the app paints, as role NAMES: the light contract in
# ui/theme.py carries the same list as colours, and the dark table has
# to clear the same floors on its own surfaces.
_TEXT_PAIRS: tuple[tuple[str, str, str, float], ...] = (
    ("body text on a card", "TEXT_PRIMARY", "SURFACE_CARD", 4.5),
    ("body text on the page", "TEXT_PRIMARY", "SURFACE_PAGE", 4.5),
    ("muted text on a card", "TEXT_MUTED", "SURFACE_CARD", 4.5),
    ("muted text on the page", "TEXT_MUTED", "SURFACE_PAGE", 4.5),
    ("muted text on a tinted panel", "TEXT_MUTED", "SURFACE_TINT", 4.5),
    ("muted text on a raised panel", "TEXT_MUTED", "SURFACE_RAISED", 4.5),
    ("subtle hint text on a card", "TEXT_SUBTLE", "SURFACE_CARD", 4.5),
    ("subtle hint text on the page", "TEXT_SUBTLE", "SURFACE_PAGE", 4.5),
    ("subtle hint text on a raised panel", "TEXT_SUBTLE", "SURFACE_RAISED", 4.5),
    ("text on the brand fill", "TEXT_ON_ACCENT", "ACCENT_PRIMARY", 4.5),
    ("text on a tint", "TEXT_ON_TINT", "SURFACE_TINT", 4.5),
    ("text on the secondary fill", "TEXT_ON_SECONDARY", "ACCENT_SECONDARY", 4.5),
    ("text on the error fill", "TEXT_ON_ERROR", "STATE_ERROR_GRAPHIC", 4.5),
    ("error text on a card", "TEXT_DANGER", "SURFACE_CARD", 4.5),
    ("error text on the error surface", "STATE_ERROR_TEXT", "STATE_ERROR_SURFACE", 4.5),
    ("success text on a card", "TEXT_SUCCESS", "SURFACE_CARD", 4.5),
    ("warning text on a card", "TEXT_WARNING", "SURFACE_CARD", 4.5),
    ("amber text on a card", "TEXT_AMBER", "SURFACE_CARD", 4.5),
    ("brand text on a card", "ACCENT_PRIMARY", "SURFACE_CARD", 4.5),
    ("brand text on the page", "ACCENT_PRIMARY", "SURFACE_PAGE", 4.5),
    ("blocked step text on a card", "TEXT_BLOCKED", "SURFACE_CARD", 4.5),
    ("blocked step text on the page", "TEXT_BLOCKED", "SURFACE_PAGE", 4.5),
    ("disabled text on a card", "TEXT_DISABLED", "SURFACE_CARD", 3.0),
    ("disabled text on the page", "TEXT_DISABLED", "SURFACE_PAGE", 3.0),
    ("success icon on a card", "STATE_SUCCESS_GRAPHIC", "SURFACE_CARD", 3.0),
    ("warning icon on a card", "STATE_WARNING_GRAPHIC", "SURFACE_CARD", 3.0),
    ("error icon on a card", "STATE_ERROR_GRAPHIC", "SURFACE_CARD", 3.0),
    ("brand icon on a card", "ACCENT_PRIMARY", "SURFACE_CARD", 3.0),
    ("tertiary icon on a card", "ACCENT_TERTIARY", "SURFACE_CARD", 3.0),
    ("control edge on a card", "BORDER_CONTROL", "SURFACE_CARD", 3.0),
    ("control edge on the page", "BORDER_CONTROL", "SURFACE_PAGE", 3.0),
    ("focus ring on a card", "ACCENT_FOCUS_RING", "SURFACE_CARD", 3.0),
)

_BADGE_FAMILIES: tuple[str, ...] = (
    "NEUTRAL",
    "BLUE",
    "GREEN",
    "RED",
    "RED_SOFT",
    "GREY",
    "GREEN_SOFT",
    "INDIGO",
    "ORANGE",
    "VIOLET",
    "AMBER",
    "TEAL",
    "PINK",
    "LIME",
    "SKY",
    "SAND",
)


@pytest.fixture(autouse=True)
def _restore_the_active_theme():
    """A swapped theme must not leak into the next test."""
    yield
    theme.set_active_theme("light")


def _declared_role_names() -> set[str]:
    """Every colour-valued module-level name in the theme's role region."""
    source = _THEME_PATH.read_text(encoding="utf-8")
    marker_line = source[: source.index(_ROLE_MARKER)].count("\n") + 1
    tree = ast.parse(source)

    assignments: dict[str, ast.expr] = {}
    declared: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            assignments[target.id] = node.value
            if getattr(node, "lineno", 0) >= marker_line:
                declared.add(target.id)

    def resolves_to_colour(name: str, seen: frozenset[str] = frozenset()) -> bool:
        if name in seen:
            return False
        value = assignments.get(name)
        if isinstance(value, ast.Constant):
            return isinstance(value.value, str) and value.value.startswith("#")
        if isinstance(value, ast.Name):
            return resolves_to_colour(value.id, seen | {name})
        return False

    return {name for name in declared if resolves_to_colour(name)}


# ---------------------------------------------------------------- the tables


def test_the_light_table_is_the_app_today():
    """The light mappings did not move: the table is the aliases."""
    for name in _ROLE_NAMES:
        assert theme.LIGHT_ROLE_TABLE[name] == getattr(theme, name), name
    assert theme.LIGHT_ROLE_TABLE["TEXT_PRIMARY"] == "#131b2e"
    assert theme.LIGHT_ROLE_TABLE["SURFACE_CARD"] == "#ffffff"
    assert theme.LIGHT_ROLE_TABLE["ACCENT_PRIMARY"] == "#004ccd"


def test_every_role_the_theme_declares_is_in_the_table():
    """A role nobody tabulated cannot be swapped with the theme."""
    declared = _declared_role_names()
    assert declared, "the role region could not be read"
    missing = sorted(declared - set(theme.LIGHT_ROLE_TABLE))
    assert not missing, f"roles with no table entry: {missing}"
    unknown = sorted(set(theme.LIGHT_ROLE_TABLE) - declared)
    assert not unknown, f"table entries that are not roles: {unknown}"


def test_both_tables_declare_the_same_roles():
    """A table swap must not miss a role."""
    assert set(theme.LIGHT_ROLE_TABLE) == set(theme.DARK_ROLE_TABLE)
    assert set(theme.ROLE_TABLES) == {"light", "dark"}


def test_every_table_value_is_a_colour():
    import re

    pattern = re.compile(r"#[0-9a-fA-F]{6}")
    for name, table in theme.ROLE_TABLES.items():
        for role_name, value in table.items():
            assert pattern.fullmatch(value), f"{name}: {role_name} -> {value!r}"


# --------------------------------------------------------------- the swap


def test_a_role_resolves_to_light_ink_in_light_and_dark_ink_in_dark():
    light = theme.role("TEXT_PRIMARY", "light")
    dark = theme.role("TEXT_PRIMARY", "dark")
    assert light == "#131b2e"
    assert dark != light
    # The ink flips: dark ink on the light surface, light ink on the dark.
    assert contrast_ratio(light, theme.role("SURFACE_CARD", "light")) >= 4.5
    assert contrast_ratio(dark, theme.role("SURFACE_CARD", "dark")) >= 4.5
    assert _luminance(dark) > _luminance(light)


def test_switching_the_active_table_swaps_the_resolved_role():
    theme.set_active_theme("dark")
    assert theme.role("TEXT_PRIMARY") == theme.DARK_ROLE_TABLE["TEXT_PRIMARY"]
    assert theme.ACTIVE_THEME == "dark"
    # The theme's own rules read the module's role values, so they
    # follow the swap.
    assert theme.TEXT_PRIMARY == theme.DARK_ROLE_TABLE["TEXT_PRIMARY"]


def test_an_unknown_theme_or_role_is_refused():
    with pytest.raises(KeyError):
        theme.role_table("sepia")
    with pytest.raises(KeyError):
        theme.role("TEXT_NOT_A_ROLE", "dark")
    with pytest.raises(KeyError):
        theme.set_active_theme("sepia")


# ------------------------------------------------------------ legibility


def test_the_dark_table_clears_the_same_floors_as_the_light_one():
    failures = []
    table = theme.DARK_ROLE_TABLE
    for label, foreground, background, minimum in _TEXT_PAIRS:
        ratio = contrast_ratio(table[foreground], table[background])
        if ratio < minimum:
            failures.append(f"{label}: {ratio:.2f}:1, needs {minimum}:1")
    assert not failures, "dark table contrast failures:\n  " + "\n  ".join(failures)


def test_the_dark_badges_are_legible():
    failures = []
    table = theme.DARK_ROLE_TABLE
    for family in _BADGE_FAMILIES:
        text = table[f"BADGE_{family}_TEXT"]
        fill = table[f"BADGE_{family}_BG"]
        ratio = contrast_ratio(text, fill)
        if ratio < 4.5:
            failures.append(f"{family.lower()} badge: {ratio:.2f}:1, needs 4.5:1")
    assert not failures, "dark badge contrast failures:\n  " + "\n  ".join(failures)


# ------------------------------------------------------------------- log


def test_the_active_role_table_is_logged(qapp):
    from curation.applog import lines

    theme.apply_theme(qapp)
    logged = [line for line in lines() if "theme-role-table" in line]
    assert logged, "the active role table was not logged"
    assert f"theme-role-table-{theme.ACTIVE_THEME}-roles-{len(theme.LIGHT_ROLE_TABLE)}" in logged[-1]


def _luminance(value: str) -> float:
    """Relative luminance of a #rrggbb colour (WCAG 2.1)."""
    h = value.lstrip("#")
    channels = []
    for i in (0, 2, 4):
        c = int(h[i : i + 2], 16) / 255
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b
