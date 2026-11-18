"""Contract: every colour pairing the app paints is legible.

The theme owns the contrast contract (``theme.CONTRAST_PAIRS`` and
``theme.BADGE_CONTRAST_PAIRS``): the role pairs the app actually paints,
with the ratio each must clear. This test reads that table, so a palette
change that breaks legibility fails the build instead of shipping.

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
    CONTRAST_PAIRS,
    contrast_ratio,
)

_KIND_FLOORS = {
    "text": 4.5,
    "graphic": 3.0,
    "disabled": 3.0,
}


def test_every_declared_pair_clears_its_floor():
    failures = []
    for label, fg, bg, kind, minimum in CONTRAST_PAIRS:
        ratio = contrast_ratio(fg, bg)
        floor = max(minimum, _KIND_FLOORS.get(kind, 4.5))
        if ratio < floor:
            failures.append(f"{label}: {ratio:.2f}:1 ({fg} on {bg}), needs {floor}:1")
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
    checked = {label for label, _fg, _bg in BADGE_CONTRAST_PAIRS}
    missing = []
    for role in _BADGE_ROLES:
        if not any(role.replace("-soft", "") in name for name in checked):
            missing.append(role)
    assert not missing, f"badge roles with no contrast check: {missing}"


def test_the_roles_resolve_to_real_colours():
    """A role that is not a colour would silently paint nothing."""
    import re

    bad = []
    for label, fg, bg, _kind, _min in CONTRAST_PAIRS:
        for value in (fg, bg):
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
                bad.append(f"{label}: {value!r}")
    for label, fg, bg in BADGE_CONTRAST_PAIRS:
        for value in (fg, bg):
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
                bad.append(f"{label}: {value!r}")
    assert not bad, f"roles that are not colours: {bad}"


def test_the_contract_is_not_empty():
    """An empty contract would pass every check it makes."""
    assert len(CONTRAST_PAIRS) >= 15
    assert len(BADGE_CONTRAST_PAIRS) >= 10
