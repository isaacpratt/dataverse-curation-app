"""Dark mode theme switching tests.

Verifies that the app can switch between light and dark themes correctly,
and that role resolution works for both themes.
"""

import pytest

from ui.theme import (
    BADGE_CONTRAST_PAIRS,
    BADGE_CONTRAST_PAIRS_DARK,
    CONTRAST_PAIRS,
    CONTRAST_PAIRS_DARK,
    DARK_ROLE_TABLE,
    LIGHT_ROLE_TABLE,
    ROLE_TABLES,
    contrast_ratio,
    role,
    role_table,
    set_active_theme,
)


def test_role_tables_have_same_keys():
    """Light and dark role tables must have identical keys."""
    assert set(LIGHT_ROLE_TABLE.keys()) == set(DARK_ROLE_TABLE.keys())
    assert set(LIGHT_ROLE_TABLE.keys()) == set(ROLE_TABLES["light"].keys())
    assert set(DARK_ROLE_TABLE.keys()) == set(ROLE_TABLES["dark"].keys())


def test_role_resolution_works_for_both_themes():
    """role() function resolves correctly for both themes."""
    # Test a few key roles
    light_bg = role("SURFACE_CARD", "light")
    dark_bg = role("SURFACE_CARD", "dark")
    assert light_bg != dark_bg, "light and dark should differ"

    light_text = role("TEXT_PRIMARY", "light")
    dark_text = role("TEXT_PRIMARY", "dark")
    assert light_text != dark_text, "light and dark should differ"

    # Test that invalid role raises KeyError
    with pytest.raises(KeyError):
        role("NONEXISTENT_ROLE", "light")


def test_role_table_function():
    """role_table() returns correct table for each theme."""
    light_table = role_table("light")
    dark_table = role_table("dark")
    assert light_table is LIGHT_ROLE_TABLE
    assert dark_table is DARK_ROLE_TABLE

    with pytest.raises(KeyError):
        role_table("invalid_theme")


def test_set_active_theme_switches_globals():
    """set_active_theme() updates ACTIVE_THEME and globals."""
    import ui.theme as theme_module

    # Start with light
    set_active_theme("light")
    assert theme_module.ACTIVE_THEME == "light"

    # Switch to dark
    set_active_theme("dark")
    assert theme_module.ACTIVE_THEME == "dark"

    # Verify globals were updated
    from ui.theme import SURFACE_CARD, TEXT_PRIMARY
    assert role("TEXT_PRIMARY", "dark") == TEXT_PRIMARY
    assert role("SURFACE_CARD", "dark") == SURFACE_CARD


def test_contrast_ratios_both_themes():
    """Key contrast ratios pass for both themes."""
    # Test a few critical pairs
    critical_pairs = [
        ("TEXT_PRIMARY", "SURFACE_CARD"),
        ("TEXT_PRIMARY", "SURFACE_PAGE"),
        ("TEXT_MUTED", "SURFACE_CARD"),
        ("ACCENT_PRIMARY", "SURFACE_CARD"),
    ]

    for theme in ("light", "dark"):
        for fg_role, bg_role in critical_pairs:
            fg = role(fg_role, theme)
            bg = role(bg_role, theme)
            ratio = contrast_ratio(fg, bg)
            assert ratio >= 4.5, f"[{theme}] {fg_role} on {bg_role}: {ratio:.2f}:1 < 4.5:1"


def test_badge_contrast_both_themes():
    """Badge contrast passes for both themes."""
    for theme in ("light", "dark"):
        for label, fg_role, bg_role in (
            ("neutral badge", "BADGE_NEUTRAL_TEXT", "BADGE_NEUTRAL_BG"),
            ("green badge", "BADGE_GREEN_TEXT", "BADGE_GREEN_BG"),
            ("red badge", "BADGE_RED_TEXT", "BADGE_RED_BG"),
        ):
            fg = role(fg_role, theme)
            bg = role(bg_role, theme)
            ratio = contrast_ratio(fg, bg)
            assert ratio >= 4.5, f"[{theme}] {label}: {ratio:.2f}:1 < 4.5:1"


def test_dark_contrast_pairs_match_light_structure():
    """Dark contrast pairs have same structure as light pairs."""
    assert len(CONTRAST_PAIRS_DARK) == len(CONTRAST_PAIRS)
    assert len(BADGE_CONTRAST_PAIRS_DARK) == len(BADGE_CONTRAST_PAIRS)

    # Check that dark pairs use role names (strings) not colour values
    for label, fg, bg, _kind, _minimum in CONTRAST_PAIRS_DARK:
        assert isinstance(fg, str), f"Dark pair {label} fg should be str"
        assert fg.isupper(), f"Dark pair {label} fg should be role name"
        assert isinstance(bg, str), f"Dark pair {label} bg should be str"
        assert bg.isupper(), f"Dark pair {label} bg should be role name"

    for label, fg, bg in BADGE_CONTRAST_PAIRS_DARK:
        assert isinstance(fg, str), f"Dark badge {label} fg should be str"
        assert fg.isupper(), f"Dark badge {label} fg should be role name"
        assert isinstance(bg, str), f"Dark badge {label} bg should be str"
        assert bg.isupper(), f"Dark badge {label} bg should be role name"


def test_no_hardcoded_colours_in_dark_table():
    """Dark table should not contain light theme colour values."""
    light_values = set(LIGHT_ROLE_TABLE.values())
    dark_values = set(DARK_ROLE_TABLE.values())

    # Some values may overlap (e.g., pure white/black), but most should differ
    common = light_values & dark_values
    assert len(common) < len(light_values) * 0.5, "Dark table should be substantially different from light"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])