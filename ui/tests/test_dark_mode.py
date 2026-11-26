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

    try:
        # Start with light
        set_active_theme("light")
        assert theme_module.ACTIVE_THEME == "light"

        # Switch to dark
        set_active_theme("dark")
        assert theme_module.ACTIVE_THEME == "dark"

        # Verify globals were updated
        assert role("TEXT_PRIMARY", "dark") == theme_module.TEXT_PRIMARY
        assert role("SURFACE_CARD", "dark") == theme_module.SURFACE_CARD
    finally:
        # The swap rebinds module globals, so leaving the app on dark would
        # make every later test (and the "light table is the aliases" guard)
        # read the dark palette.
        set_active_theme("light")


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
    assert len(common) < len(light_values) * 0.5, (
        "Dark table should be substantially different from light"
    )


# --- Per-theme stylesheets (dv-4jm.1) ------------------------------------


def test_every_qss_generator_accepts_a_theme():
    """A generator that cannot be told a theme paints one palette forever."""
    from collections.abc import Callable

    from ui import theme

    cases: dict[str, Callable[[str], str]] = {
        "global_qss": lambda t: theme.global_qss(t),
        "button_qss": lambda t: theme.button_qss("primary", theme=t),
        "header_section_qss": lambda t: theme.header_section_qss(theme=t),
        "selection_qss": lambda t: theme.selection_qss("QTableWidget", theme=t),
        "input_qss": lambda t: theme.input_qss("QLineEdit", theme=t),
        "workflow_step_qss": lambda t: theme.workflow_step_qss("current", theme=t),
        "workflow_rail_qss": lambda t: theme.workflow_rail_qss(theme=t),
        "page_background_qss": lambda t: theme.page_background_qss("X", theme=t),
    }
    # Caller-supplied palettes: the fill/edge/text arrive as arguments, so
    # the theme only records which table they were resolved against.
    caller_colours: dict[str, Callable[[str], str]] = {
        "surface_frame_qss": lambda t: theme.surface_frame_qss("#000", "#111", theme=t),
        "band_qss": lambda t: theme.band_qss("#000", "#111", theme=t),
        "status_strip_qss": lambda t: theme.status_strip_qss("#000", "#111", "#222", theme=t),
        "badge_qss": lambda t: theme.badge_qss("#000", "#111", "#222", theme=t),
    }
    for name, build in caller_colours.items():
        assert build("light") == build("dark"), f"{name} should pass its colours through"
    # Generators whose whole job is "paint nothing": identical by design.
    colour_free: dict[str, Callable[[str], str]] = {
        "scrollbar_lane_qss": lambda t: theme.scrollbar_lane_qss("QTreeView", theme=t),
        "transparent_qss": lambda t: theme.transparent_qss("QLabel", theme=t),
        "transparent_surface_qss": lambda t: theme.transparent_surface_qss("X", theme=t),
    }
    for name, build in cases.items():
        light, dark = build("light"), build("dark")
        assert isinstance(light, str), f"{name} returned a non-string for light"
        assert light, f"{name} returned nothing for light"
        assert isinstance(dark, str), f"{name} returned a non-string for dark"
        assert dark, f"{name} returned nothing for dark"
        assert light != dark, f"{name} ignores the theme argument"

    for name, build in colour_free.items():
        assert build("light") == build("dark"), f"{name} should be colour-free"


def test_generators_default_to_the_active_theme():
    """Omitting the theme must follow a live switch, not a frozen palette."""
    from ui import theme

    try:
        set_active_theme("light")
        light_sheet = theme.global_qss()
        light_button = theme.button_qss("primary")

        set_active_theme("dark")
        assert theme.global_qss() != light_sheet
        assert theme.button_qss("primary") != light_button
    finally:
        set_active_theme("light")


def test_explicit_theme_beats_the_active_one():
    """The gallery's two columns pass a theme, and must get that palette."""
    from ui import theme

    try:
        set_active_theme("dark")
        # Explicit light wins even while the app is painting dark.
        assert theme.role("SURFACE_PAGE", theme.ACTIVE_THEME) == theme.role("SURFACE_PAGE", "dark")
        assert "#faf8ff" in theme.page_background_qss("X", theme="light")
    finally:
        set_active_theme("light")


def test_light_output_is_unchanged_by_the_refactor():
    """The refactor moved no light colour: the table still is the aliases.

    Guards the "table swap, not a re-skin" promise: the light sheet must
    be what it was before the generators became theme-aware.
    """
    from ui import theme

    assert role("SURFACE_PAGE", "light") == theme.BACKGROUND
    assert role("SURFACE_CARD", "light") == theme.SURFACE_CONTAINER_LOWEST
    assert role("TEXT_PRIMARY", "light") == theme.ON_SURFACE
    assert role("ACCENT_PRIMARY", "light") == theme.PRIMARY
    assert role("ACCENT_FOCUS_TINT", "light") == theme.PRIMARY_FIXED_DIM


def test_set_active_theme_does_not_change_generator_defaults():
    """A default-theme generator follows the active table, not a frozen one."""
    from ui import theme

    try:
        set_active_theme("dark")
        assert "#6ea8ff" in theme.button_qss("primary")
        set_active_theme("light")
        assert theme.PRIMARY in theme.button_qss("primary")
    finally:
        set_active_theme("light")


# --- OS auto-detection (dv-4jm.2) ---------------------------------------


def test_qt_color_scheme_is_the_primary_os_source(monkeypatch):
    """Qt's native scheme wins; platform probes are the fallback only."""
    from ui import theme

    monkeypatch.setattr(theme, "_qt_color_scheme", lambda: "dark")
    assert theme.detect_os_theme() == "dark"
    monkeypatch.setattr(theme, "_qt_color_scheme", lambda: "light")
    assert theme.detect_os_theme() == "light"

    # When Qt cannot answer (headless/offscreen), the old probes decide.
    monkeypatch.setattr(theme, "_qt_color_scheme", lambda: None)
    import subprocess
    import sys

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: type("R", (), {"stdout": "prefer-dark", "returncode": 0})(),
    )
    assert theme.detect_os_theme() == "dark"


def test_os_theme_watcher_only_repaints_in_auto_mode(win, monkeypatch):
    """A live OS scheme change is ignored when the curator picked a theme."""
    from ui import theme

    calls = []
    monkeypatch.setattr(theme, "detect_os_theme", lambda: "dark")
    monkeypatch.setattr(theme, "set_active_theme", lambda name: calls.append(name))
    monkeypatch.setattr(
        theme,
        "apply_theme",
        lambda app, name, **kw: calls.append((name, kw.get("retheme"))),
    )

    win._config.app.theme_mode = "dark"
    win._on_os_theme_changed()
    assert calls == []

    win._config.app.theme_mode = "auto"
    win._on_os_theme_changed()
    assert calls == ["dark", ("dark", True)]
    win._config.app.theme_mode = "dark"


def test_resolve_theme_mode_passes_explicit_modes_through(monkeypatch):
    """An explicit light/dark must never touch the OS."""
    from ui import theme

    def _boom() -> str:
        raise AssertionError("detect_os_theme() must not be called")

    monkeypatch.setattr(theme, "detect_os_theme", _boom)
    assert theme.resolve_theme_mode("light") == "light"
    assert theme.resolve_theme_mode("dark") == "dark"


def test_resolve_theme_mode_asks_the_os_for_auto(monkeypatch):
    """'auto' (and junk) resolve through the OS probe."""
    from ui import theme

    monkeypatch.setattr(theme, "detect_os_theme", lambda: "dark")
    assert theme.resolve_theme_mode("auto") == "dark"
    monkeypatch.setattr(theme, "detect_os_theme", lambda: "light")
    assert theme.resolve_theme_mode("nonsense") == "light"


def test_detect_os_theme_defaults_to_light_on_failure(monkeypatch):
    """A failed probe must leave the curator on a readable palette."""
    import subprocess
    import sys

    from ui import theme

    monkeypatch.setattr(sys, "platform", "linux")

    def _timeout(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd="gsettings", timeout=3)

    monkeypatch.setattr(subprocess, "run", _timeout)
    assert theme.detect_os_theme() == "light"


def test_detect_os_theme_reads_gnome_colour_scheme(monkeypatch):
    """GNOME's color-scheme key decides light/dark on Linux."""
    import subprocess
    import sys

    from ui import theme

    monkeypatch.setattr(sys, "platform", "linux")

    class _Result:
        def __init__(self, stdout: str, returncode: int = 0) -> None:
            self.stdout = stdout
            self.returncode = returncode

    monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: _Result("'prefer-dark'\n"))
    assert theme.detect_os_theme() == "dark"

    monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: _Result("'prefer-light'\n"))
    assert theme.detect_os_theme() == "light"


def test_detect_os_theme_reads_macos_interface_style(monkeypatch):
    """MacOS prints 'Dark' in dark mode and exits non-zero in light."""
    import subprocess
    import sys

    from ui import theme

    monkeypatch.setattr(sys, "platform", "darwin")

    class _Result:
        def __init__(self, stdout: str, returncode: int) -> None:
            self.stdout = stdout
            self.returncode = returncode

    monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: _Result("Dark\n", 0))
    assert theme.detect_os_theme() == "dark"

    # Light mode: the key is absent, so `defaults` exits non-zero.
    monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: _Result("", 1))
    assert theme.detect_os_theme() == "light"


def test_detect_os_theme_falls_back_for_unknown_platform(monkeypatch):
    """An unsupported desktop reads as light rather than guessing dark."""
    import sys

    from ui import theme

    monkeypatch.setattr(sys, "platform", "freebsd13")
    assert theme.detect_os_theme() == "light"


# --- Gallery persistence (dv-4jm.6) -------------------------------------


def test_gallery_mode_defaults_to_both(tmp_path):
    """A fresh config gives the side-by-side view, the useful default."""
    from curation.config import Config

    cfg = Config.load(tmp_path / "config.json")
    assert cfg.app.gallery_theme_mode == "both"


def test_gallery_mode_round_trips_through_the_config(tmp_path):
    """The chosen view survives a save/load, so the next open keeps it."""
    from curation.config import Config

    path = tmp_path / "config.json"
    cfg = Config.load(path)
    cfg.app.gallery_theme_mode = "dark"
    cfg.save(path)

    assert Config.load(path).app.gallery_theme_mode == "dark"


def test_gallery_window_opens_on_the_saved_mode(gallery_without_app_theme, qapp, tmp_path):
    """The selector shows the remembered view, not always 'Both'."""
    from curation.config import Config
    from ui.gallery import GalleryWindow

    path = tmp_path / "config.json"
    cfg = Config.load(path)
    cfg.app.gallery_theme_mode = "dark"

    window = GalleryWindow(config=cfg)
    try:
        assert window._theme_selector.currentData() == "dark"
    finally:
        window.close()
        window.deleteLater()


def test_gallery_window_persists_a_new_choice(gallery_without_app_theme, qapp, tmp_path):
    """Picking a view writes it, so reopening starts there."""
    from curation.config import Config
    from ui.gallery import GalleryWindow

    path = tmp_path / "config.json"
    cfg = Config.load(path)
    cfg.app.gallery_theme_mode = "both"
    cfg.save(path)

    window = GalleryWindow(config=cfg)
    try:
        index = window._theme_selector.findData("light")
        window._theme_selector.setCurrentIndex(index)
        assert cfg.app.gallery_theme_mode == "light"
        assert Config.load(path).app.gallery_theme_mode == "light"
    finally:
        window.close()
        window.deleteLater()


def test_gallery_window_without_config_still_opens(gallery_without_app_theme, qapp):
    """The gallery is reachable from `--gallery` with no config to write."""
    from ui.gallery import GalleryWindow

    window = GalleryWindow()
    try:
        assert window._theme_selector.currentData() == "both"
    finally:
        window.close()
        window.deleteLater()


# --- Smooth transitions (dv-4jm.3) ---------------------------------------


def test_animate_theme_change_repaints_at_once_when_it_cannot_fade(qapp):
    """A window that already has an effect must not be faded.

    The fade installs a ``QGraphicsOpacityEffect``, and a widget can only
    carry one - fading a window that already has an effect would silently
    replace it. That case must swap the sheet immediately instead.
    """
    from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget

    from ui import theme

    window = QWidget()
    window.resize(120, 60)
    window.setGraphicsEffect(QGraphicsOpacityEffect(window))
    window.show()
    qapp.processEvents()
    try:
        calls: list[str] = []
        theme.animate_theme_change(window, lambda: calls.append("repainted"))
        assert calls == ["repainted"], "an unusable target: repaint must happen immediately"
    finally:
        window.close()
        window.deleteLater()


def test_animate_theme_change_fades_the_window_it_is_given(qapp):
    """The fade runs on the named window, on the test platform too.

    Two things are pinned here. The target is the window passed in, not
    "the first visible top-level" - a process can hold several, and picking
    wrong fades a window nobody is looking at. And it fades a
    ``QGraphicsOpacityEffect`` rather than ``windowOpacity``: window opacity
    is a window-manager property, and the offscreen plugin has no manager -
    it answers with a Qt warning and no fade, which this suite treats as a
    failure. An effect is a paint-time operation, so the same code path runs
    everywhere.
    """
    import time

    from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget

    from ui import theme

    window = QWidget()
    window.resize(120, 60)
    window.show()
    qapp.processEvents()

    swapped: list[str] = []
    theme.animate_theme_change(window, lambda: swapped.append("swapped"))
    qapp.processEvents()

    effect = window.graphicsEffect()
    assert isinstance(effect, QGraphicsOpacityEffect), "the fade must install an effect"
    assert swapped == [], "the sheet must not swap until the fade is part-way"

    # Let the fade-out finish (140 ms) plus a beat.
    deadline = time.perf_counter() + 0.25
    while time.perf_counter() < deadline and not swapped:
        qapp.processEvents()
        time.sleep(0.005)
    assert swapped == ["swapped"], "the repaint must land at the dimmest point"

    # And the effect is removed again once the fade-in completes.
    deadline = time.perf_counter() + 0.3
    while time.perf_counter() < deadline and window.graphicsEffect() is not None:
        qapp.processEvents()
        time.sleep(0.005)
    assert window.graphicsEffect() is None, "the effect must not be left installed"

    window.close()
    window.deleteLater()


# --- Scoped sheets follow a live switch (dv-4jm.7) -----------------------


def test_scoped_sheets_follow_a_live_switch(qapp):
    """A switch repaints widgets that carry their own sheet.

    ``apply_theme`` replaces the application sheet, but a widget that called
    ``setStyleSheet`` keeps that sheet - Qt does not re-derive it. Kit
    factories register a rebuild, and ``apply_theme`` runs them, so a card or
    button built before the switch paints the new palette without being
    rebuilt.
    """
    from PySide6.QtWidgets import QWidget

    from ui import theme
    from ui.widgets import make_action_button, make_card, make_progress_bar

    theme.set_active_theme("light")
    theme.apply_theme(qapp, "light", retheme=True)
    host = QWidget()
    host.resize(240, 240)
    host.show()
    qapp.processEvents()
    try:
        card, _body, _title, _header = make_card("Probe")
        button = make_action_button("Probe")
        bar = make_progress_bar()
        # The rebuild covers what is on screen, so the widgets are shown -
        # which is also how a curator meets them.
        for widget in (card, button, bar):
            widget.setParent(host)
            widget.show()
        qapp.processEvents()
        card_light = card.styleSheet()
        button_light = button.styleSheet()

        assert theme.role("SURFACE_CARD", "light") in card_light
        assert theme.role("SURFACE_CARD", "light") in button_light

        theme.set_active_theme("dark")
        theme.apply_theme(qapp, "dark", retheme=True)

        # The application sheet is palette-based and installed once; the
        # switch changed the palette instead of replacing the whole sheet.
        from PySide6.QtGui import QPalette

        assert "palette(base)" in qapp.styleSheet()
        assert qapp.palette().color(QPalette.ColorRole.Base).name() == theme.role(
            "SURFACE_CARD", "dark"
        )
        # ...and so did every scoped sheet the widgets already carried.
        assert card.styleSheet() != card_light
        assert theme.role("SURFACE_CARD", "dark") in card.styleSheet()
        assert button.styleSheet() != button_light
        assert theme.role("ACCENT_PRIMARY", "dark") in bar.styleSheet()

        # And back again: the rebuild is not a one-way latch.
        theme.set_active_theme("light")
        theme.apply_theme(qapp, "light", retheme=True)
        assert theme.role("SURFACE_CARD", "light") in card.styleSheet()
    finally:
        host.close()
        host.deleteLater()
        theme.set_active_theme("light")
        theme.apply_theme(qapp, "light", retheme=True)


def test_retheme_skips_widgets_that_are_gone(qapp):
    """A destroyed widget must not break the switch.

    The rebuild is stored on the widget, so it dies with it - but a widget
    deleted in C++ while its Python wrapper lives on must be skipped rather
    than raising.
    """
    from PySide6.QtWidgets import QWidget

    from ui import theme

    theme.set_active_theme("light")
    theme.apply_theme(qapp, "light", retheme=True)
    try:
        orphan = QWidget()
        orphan.setStyleSheet("QWidget { color: red; }")
        orphan.deleteLater()
        qapp.processEvents()

        theme.set_active_theme("dark")
        ran = theme.retheme_widgets(qapp)  # must not raise
        assert ran >= 0
    finally:
        theme.set_active_theme("light")
        theme.apply_theme(qapp, "light", retheme=True)


def test_retheme_registry_drops_destroyed_widgets(qapp):
    """A destroyed C++ widget must not remain in the tracked set (dv-tqi4).

    topLevelWidgets() used to hand back wrappers whose C++ object was gone;
    the registry is pruned by the destroyed signal instead.
    """
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QWidget

    from ui import theme
    from ui.widgets import set_sheet

    host = QWidget()
    host.setObjectName("RegistryHost")
    set_sheet(host, "page_background", ("RegistryHost",))
    assert host in theme.RETHEME_WIDGETS
    assert host in theme.retheme_top_levels()
    host.show()
    assert host in theme.visible_retheme_roots()
    host.hide()
    assert host not in theme.visible_retheme_roots()
    host.deleteLater()
    qapp.sendPostedEvents(host, QEvent.Type.DeferredDelete)
    qapp.processEvents()
    assert host not in theme.RETHEME_WIDGETS
    assert host not in theme.retheme_top_levels()


def test_hidden_widget_defers_its_retint_until_shown(qapp):
    """A hidden page is skipped on switch, then repainted on Show.

    Re-polishing a hidden stacked page's container costs ~0.5s on a full
    window, so a switch only touches visible widgets. The contract is that
    the page is correct when the curator next opens it.
    """
    from PySide6.QtWidgets import QStackedWidget, QVBoxLayout, QWidget

    from ui import theme
    from ui.widgets import make_card

    theme.set_active_theme("light")
    theme.apply_theme(qapp, "light", retheme=True)
    outer = QWidget()
    outer.resize(240, 200)
    outer_layout = QVBoxLayout(outer)
    stack = QStackedWidget()
    outer_layout.addWidget(stack)
    shown = QWidget()
    hidden = QWidget()
    hidden.setObjectName("HiddenRetintHost")
    stack.addWidget(shown)
    stack.addWidget(hidden)
    layout = QVBoxLayout(hidden)
    outer.show()
    qapp.processEvents()
    card, _body, _title, _header = make_card("probe")
    layout.addWidget(card)
    stack.setCurrentIndex(1)
    qapp.processEvents()
    light_sheet = card.styleSheet()

    stack.setCurrentIndex(0)  # the card's page is now hidden inside a visible window
    qapp.processEvents()
    theme.set_active_theme("dark")
    theme.apply_theme(qapp, "dark", retheme=True)
    qapp.processEvents()
    assert card.styleSheet() == light_sheet, "hidden page must not be re-polished during the switch"

    stack.setCurrentIndex(1)
    qapp.processEvents()
    assert card.styleSheet() != light_sheet
    assert theme.role("SURFACE_CARD", "dark") in card.styleSheet()
    outer.close()
    theme.set_active_theme("light")
    theme.apply_theme(qapp, "light", retheme=True)


def test_retheme_can_be_switched_off_for_a_temporary_build(qapp):
    """The gallery builds a second theme in one process.

    With retheme on, switching to dark to build that column would repaint
    the light column that is already built. ``retheme=False`` keeps the
    temporary switch from touching existing widgets.
    """
    from PySide6.QtWidgets import QWidget

    from ui import theme
    from ui.widgets import make_card

    theme.set_active_theme("light")
    theme.apply_theme(qapp, "light", retheme=True)
    host = QWidget()
    host.resize(200, 200)
    host.show()
    qapp.processEvents()
    try:
        card, _b, _t, _h = make_card("Probe")
        card.setParent(host)
        card.show()
        qapp.processEvents()
        light_sheet = card.styleSheet()

        theme.set_active_theme("dark")
        theme.apply_theme(qapp, "dark", retheme=False)
        assert card.styleSheet() == light_sheet, "a temporary switch must not repaint"

        # A real switch, with retheme on, does.
        theme.apply_theme(qapp, "dark", retheme=True)
        assert card.styleSheet() != light_sheet
    finally:
        host.close()
        host.deleteLater()
        theme.set_active_theme("light")
        theme.apply_theme(qapp, "light", retheme=True)


def test_every_surface_retints_on_a_live_switch(qapp):
    """Every scoped surface follows one live light→dark→light cycle.

    A small harness holds one of each sheet kind - page, card, band, rule,
    button, search field, line edit, checkbox, progress bar, list, table,
    badge and chip - plus the three non-widget surfaces: a widget glyph, a
    model-item glyph and the painted ring. One cycle, three app-stylesheet
    swaps, ~30 widgets instead of the whole main window (dv-314).

    The real-window walk lives in ``probe_theme_switch.py``, which runs in
    the same gate. Keep this harness in step when a view gains a new kind
    of scoped sheet.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import (
        QFrame,
        QListWidget,
        QListWidgetItem,
        QVBoxLayout,
        QWidget,
    )

    from ui import theme
    from ui import widgets as _widgets  # installs the retheme hook
    from ui.icons import set_item_icon
    from ui.ring import RingProgress
    from ui.widgets import (
        AppTable,
        make_action_button,
        make_badge,
        make_card,
        make_checkbox,
        make_icon_button,
        make_line_edit,
        make_list,
        make_progress_bar,
        make_search_field,
        make_split_chip,
        set_flush_table_style,
        set_sheet,
    )

    assert _widgets is not None
    light_only = set(theme.LIGHT_ROLE_TABLE.values()) - set(theme.DARK_ROLE_TABLE.values())
    dark_only = set(theme.DARK_ROLE_TABLE.values()) - set(theme.LIGHT_ROLE_TABLE.values())

    theme.set_active_theme("light")
    theme.apply_theme(qapp, "light", retheme=True)

    host = QWidget()
    host.setObjectName("ThemeHarness")
    set_sheet(host, "page_background", ("ThemeHarness",))
    host.resize(360, 320)
    host.show()
    column = QVBoxLayout(host)
    card, _body, _title, _header = make_card("probe")
    column.addWidget(card)
    column.addWidget(make_action_button("probe"))
    column.addWidget(make_search_field("probe"))
    column.addWidget(make_line_edit("probe"))
    column.addWidget(make_checkbox("probe"))
    column.addWidget(make_progress_bar())
    column.addWidget(make_list(flush=True))
    table = AppTable(["a", "b"])
    set_flush_table_style(table)
    column.addWidget(table)
    column.addWidget(make_badge("Draft"))
    column.addWidget(make_split_chip("probe"))
    band = QFrame()
    band.setObjectName("HarnessBand")
    set_sheet(band, "band", "SURFACE_TINT", "BORDER_SUBTLE", selector="QFrame#HarnessBand")
    column.addWidget(band)
    divider = QFrame()
    set_sheet(divider, "rule", "QFrame", "BORDER_SUBTLE")
    column.addWidget(divider)
    button = make_icon_button("info")
    column.addWidget(button)
    listing = QListWidget()
    item = QListWidgetItem("probe")
    set_item_icon(item, "info")
    listing.addItem(item)
    column.addWidget(listing)
    ring = RingProgress()
    ring.resize(40, 40)
    column.addWidget(ring)
    for _ in range(6):
        qapp.processEvents()

    def stale(colours: set[str]) -> list[tuple[str, list[str]]]:
        found = []
        for widget in [host, *host.findChildren(QWidget)]:
            try:
                sheet = widget.styleSheet()
            except Exception:
                continue
            if not sheet:
                continue
            hits = sorted({c for c in colours if c in sheet})
            if hits:
                found.append((widget.objectName() or type(widget).__name__, hits))
        return found

    def render_ring() -> object:
        pixmap = QPixmap(40, 40)
        pixmap.fill(Qt.GlobalColor.transparent)
        ring.render(pixmap)
        return pixmap.toImage()

    try:
        light_icon = button.icon().cacheKey()
        light_item = item.icon().cacheKey()
        light_ring = render_ring()

        theme.set_active_theme("dark")
        theme.apply_theme(qapp, "dark", retheme=True)

        assert not stale(light_only), stale(light_only)
        assert button.icon().cacheKey() != light_icon, "the widget glyph kept its light tint"
        assert item.icon().cacheKey() != light_item, "the item glyph kept its light tint"
        assert render_ring() != light_ring, "the ring kept the light arc"

        theme.set_active_theme("light")
        theme.apply_theme(qapp, "light", retheme=True)
        assert not stale(dark_only), stale(dark_only)
    finally:
        theme.set_active_theme("light")
        theme.apply_theme(qapp, "light", retheme=True)
        host.close()
        host.deleteLater()
        qapp.processEvents()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
