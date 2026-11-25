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
