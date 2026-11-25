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

# The pairs the app paints, as role NAMES, read straight from the theme's
# own dark contract. This used to be a hand-kept copy of the same list; a
# copy drifts the moment a pair is added (the warning-surface pairs were
# missing from it), so the contract is now the single source.
_TEXT_PAIRS: tuple[tuple[str, str, str, float], ...] = tuple(
    (label, foreground, background, minimum)
    for label, foreground, background, _kind, minimum in theme.CONTRAST_PAIRS_DARK
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
    """Restore the active theme so a swap cannot leak into the next test."""
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
    assert theme.DARK_ROLE_TABLE["TEXT_PRIMARY"] == theme.TEXT_PRIMARY


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
    assert (
        f"theme-role-table-{theme.ACTIVE_THEME}-roles-{len(theme.LIGHT_ROLE_TABLE)}" in logged[-1]
    )


def _luminance(value: str) -> float:
    """Relative luminance of a #rrggbb colour (WCAG 2.1)."""
    h = value.lstrip("#")
    channels = []
    for i in (0, 2, 4):
        c = int(h[i : i + 2], 16) / 255
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b
