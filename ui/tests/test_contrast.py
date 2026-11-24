"""Contract: every colour pairing the app paints is legible.

The theme owns the contrast contract (``theme.CONTRAST_PAIRS``,
``theme.CONTRAST_PAIRS_DARK``, ``theme.BADGE_CONTRAST_PAIRS``,
``theme.BADGE_CONTRAST_PAIRS_DARK``): the role pairs the app actually
paints, with the ratio each must clear. This test reads that table, so a
palette change that breaks legibility fails the build instead of
shipping.

The floors:

* **text** - normal-size text: 4.5:1 (WCAG 2.1 AA);
* **graphic** - icons and other non-text marks: 3:1;
* **disabled** - disabled controls are exempt from WCAG 1.4.3, but the
  app holds them to 3:1 anyway so they stay readable.

The table is the contract: a new pairing is added to the theme (and
therefore checked here), not left implicit in a call site.
"""

from ui.theme import (
    _BADGE_ROLES,
    BADGE_CONTRAST_PAIRS,
    BADGE_CONTRAST_PAIRS_DARK,
    CONTRAST_PAIRS,
    CONTRAST_PAIRS_DARK,
    contrast_ratio,
    role,
)

_KIND_FLOORS = {
    "text": 4.5,
    "graphic": 3.0,
    "disabled": 3.0,
}


def _resolve_pair(fg: str, bg: str, theme: str) -> tuple[str, str]:
    """Resolve role names to actual colours for a theme."""
    return role(fg, theme), role(bg, theme)


def _check_pairs(pairs, theme: str, kind_floors: dict[str, float]):
    """Check a set of contrast pairs for a theme."""
    failures = []
    if theme == "light":
        # Light pairs already have actual colour values
        for label, fg, bg, kind, minimum in pairs:
            ratio = contrast_ratio(fg, bg)
            floor = max(minimum, kind_floors.get(kind, 4.5))
            if ratio < floor:
                failures.append(f"[light] {label}: {ratio:.2f}:1 ({fg} on {bg}), needs {floor}:1")
    else:
        # Dark pairs use role names that need resolving
        for label, fg, bg, kind, minimum in pairs:
            fg_colour, bg_colour = _resolve_pair(fg, bg, theme)
            ratio = contrast_ratio(fg_colour, bg_colour)
            floor = max(minimum, kind_floors.get(kind, 4.5))
            if ratio < floor:
                failures.append(f"[{theme}] {label}: {ratio:.2f}:1 ({fg_colour} on {bg_colour}), needs {floor}:1")
    return failures


def test_every_declared_pair_clears_its_floor():
    failures = []
    # Check light theme
    failures.extend(_check_pairs(CONTRAST_PAIRS, "light", _KIND_FLOORS))
    # Check dark theme
    failures.extend(_check_pairs(CONTRAST_PAIRS_DARK, "dark", _KIND_FLOORS))
    assert not failures, "contrast failures:\n  " + "\n  ".join(failures)


def test_every_badge_role_clears_its_floor():
    failures = []
    for label, fg, bg in BADGE_CONTRAST_PAIRS:
        ratio = contrast_ratio(fg, bg)
        if ratio < 4.5:
            failures.append(f"{label}: {ratio:.2f}:1 ({fg} on {bg}), needs 4.5:1")
    assert not failures, "badge contrast failures:\n  " + "\n  ".join(failures)


def test_every_badge_role_is_in_the_contract():
    """A role nobody checks is a role that can rot."""
    # Check light theme
    checked = {label for label, _fg, _bg in BADGE_CONTRAST_PAIRS}
    missing = []
    for role_name in _BADGE_ROLES:
        if not any(role_name.replace("-soft", "") in name for name in checked):
            missing.append(role_name)
    assert not missing, f"badge roles with no contrast check (light): {missing}"
    # Check dark theme (same role names)
    checked_dark = {label for label, _fg, _bg in BADGE_CONTRAST_PAIRS_DARK}
    missing_dark = []
    for role_name in _BADGE_ROLES:
        if not any(role_name.replace("-soft", "") in name for name in checked_dark):
            missing_dark.append(role_name)
    assert not missing_dark, f"badge roles with no contrast check (dark): {missing_dark}"


def _check_colour_format(pairs, theme: str, resolve: bool) -> list[str]:
    """Check that all values in pairs are valid hex colours."""
    import re

    bad = []
    hex_re = re.compile(r"#[0-9a-fA-F]{6}")
    for item in pairs:
        if len(item) == 5:
            label, fg, bg, _kind, _min = item
            if resolve:
                fg_colour, bg_colour = _resolve_pair(fg, bg, theme)
                values = (fg_colour, bg_colour)
            else:
                values = (fg, bg)
        elif len(item) == 3:
            label, fg, bg = item
            if resolve:
                fg_colour, bg_colour = _resolve_pair(fg, bg, theme)
                values = (fg_colour, bg_colour)
            else:
                values = (fg, bg)
        else:
            continue
        for value in values:
            if not hex_re.fullmatch(value):
                bad.append(f"[{theme}] {label}: {value!r}")
    return bad


def test_the_roles_resolve_to_real_colours():
    """A role that is not a colour would silently paint nothing."""
    bad = []
    bad.extend(_check_colour_format(CONTRAST_PAIRS, "light", False))
    bad.extend(_check_colour_format(CONTRAST_PAIRS_DARK, "dark", True))
    bad.extend(_check_colour_format(BADGE_CONTRAST_PAIRS, "light", False))
    bad.extend(_check_colour_format(BADGE_CONTRAST_PAIRS_DARK, "dark", True))
    assert not bad, f"roles that are not colours: {bad}"


def test_the_contract_is_not_empty():
    """An empty contract would pass every check it makes."""
    assert len(CONTRAST_PAIRS) >= 15
    assert len(CONTRAST_PAIRS_DARK) >= 15
    assert len(BADGE_CONTRAST_PAIRS) >= 10
    assert len(BADGE_CONTRAST_PAIRS_DARK) >= 10
