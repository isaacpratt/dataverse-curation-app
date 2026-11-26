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
    assert "palette(tool-tip-base)" not in sheet
    assert "palette(tooltip-base)" in sheet


def test_palette_qss_does_not_patch_the_role_function(qapp):
    """Generation is re-entrant: the resolver is scoped, not a global swap."""
    import threading

    original = theme.role
    first = theme.palette_qss()
    assert theme.role is original

    # A failure mid-generation must also restore the resolver.
    def _boom(name, theme_name=None):
        raise RuntimeError("generation failed")

    token = theme._ROLE_RESOLVER.set(_boom)
    try:
        try:
            theme.palette_qss()
        except RuntimeError:
            pass
    finally:
        theme._ROLE_RESOLVER.reset(token)
    assert theme.role is original
    assert theme.role("SURFACE_PAGE", "light") == theme.role_table("light")["SURFACE_PAGE"]

    # Concurrent generations see their own resolver and produce the same sheet.
    sheets: list[str] = []

    def generate():
        sheets.append(theme.palette_qss())

    threads = [threading.Thread(target=generate) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sheets == [first] * 4
    assert theme.role is original
