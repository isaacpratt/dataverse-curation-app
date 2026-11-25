"""The palette layer: generic colours live in QPalette so a switch is cheap."""

from PySide6.QtGui import QPalette

from ui import theme


def test_palette_maps_the_documented_roles(qapp):
    for name in ("light", "dark"):
        palette = theme.palette_for(name)
        assert isinstance(palette, QPalette)
        for role_name, qt_name in theme.PALETTE_ROLE_MAP.items():
            expected = theme.role(role_name, name)
            actual = palette.color(getattr(QPalette.ColorRole, qt_name)).name()
            assert actual == expected, f"{name}: {role_name} -> {qt_name}"


def test_light_and_dark_palettes_differ(qapp):
    light = theme.palette_for("light")
    dark = theme.palette_for("dark")
    assert light.color(QPalette.ColorRole.Window) != dark.color(QPalette.ColorRole.Window)
    assert light.color(QPalette.ColorRole.Highlight) != dark.color(QPalette.ColorRole.Highlight)


def test_app_sheet_is_static_and_palette_based(qapp):
    import inspect
    import re

    sheet = theme.palette_qss()
    assert "palette(window-text)" in sheet
    assert "palette(base)" in sheet
    # Qt does not resolve palette() in the background shorthand.
    assert "background: palette(" not in sheet
    assert "background-color: palette(" in sheet
    # No role colour is baked in: the same sheet serves both palettes.
    assert theme.role("SURFACE_PAGE", "light") not in sheet
    assert theme.role("SURFACE_PAGE", "dark") not in sheet

    source = inspect.getsource(theme.global_qss)
    used = set(re.findall(r"""role\(\s*["']([A-Z0-9_]+)""", source))
    mapped = set(theme.PALETTE_ROLE_MAP) | set(theme.PALETTE_QSS_FALLBACK)
    assert used <= mapped, f"app-sheet roles without a palette mapping: {sorted(used - mapped)}"
