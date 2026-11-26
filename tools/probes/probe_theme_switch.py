"""Probe: a live theme switch repaints every scoped sheet.

dv-4jm.7 made the kit factories repaint on a switch; this probe walks the
real window (dashboard, settings, review configuration) and fails if any
widget still wears a colour only the previous theme uses. It is the guard
for view-level sheets - page backgrounds, cards, bands, pills, search
fields, chips, badges, check rows and window chrome (dv-314).

Hidden pages defer their repaint until they are shown; the probe checks
both halves of that contract: visible sheets are correct immediately, and
every page is correct after it has been visited.

Run: python tools/probes/probe_theme_switch.py
"""

from __future__ import annotations

import sys
from collections.abc import Iterable

from _common import Report, boot


def stale_sheets(
    win: object, colours: set[str], widgets: Iterable[object]
) -> list[tuple[str, list[str]]]:
    """Name widgets whose visible sheet still uses a colour from `colours`."""
    found = []
    for w in widgets:
        try:
            if not w.isVisible():
                continue
            sheet = w.styleSheet()
        except Exception:
            continue
        if not sheet:
            continue
        hits = sorted({c for c in colours if c in sheet})
        if hits:
            found.append((w.objectName() or type(w).__name__, hits))
    return found


def visit_all_pages(win: object, app: object) -> None:
    """Show every stack page so deferred sheets are repainted."""
    stack = win._stack
    for index in range(stack.count()):
        stack.setCurrentIndex(index)
        for _ in range(6):
            app.processEvents()


def main() -> int:
    app, cfg = boot()
    from PySide6.QtWidgets import QWidget

    from ui import theme
    from ui.main_window import MainWindow

    report = Report("theme switch repaints scoped sheets")
    win = MainWindow(cfg)
    win.resize(1280, 860)
    win.show()
    for _ in range(12):
        app.processEvents()

    # Build the other full pages too: each has its own scoped sheets.
    win._ensure_settings()
    win._ensure_about()
    win._show_review_config()
    for _ in range(10):
        app.processEvents()

    light = set(theme.LIGHT_ROLE_TABLE.values())
    dark = set(theme.DARK_ROLE_TABLE.values())
    light_only, dark_only = light - dark, dark - light
    widgets = [win, *win.findChildren(QWidget)]

    from ui.widgets import make_icon_button

    icon_host = QWidget()
    icon_host.resize(200, 200)
    icon_host.show()
    icon_btn = make_icon_button("info")
    icon_btn.setParent(icon_host)
    icon_btn.show()
    for _ in range(4):
        app.processEvents()
    light_icon = icon_btn.icon().cacheKey()

    theme.set_active_theme("dark")
    theme.apply_theme(app, "dark", retheme=True)
    for _ in range(6):
        app.processEvents()
    stale_dark = stale_sheets(win, light_only, widgets)
    report.check(
        not stale_dark,
        "light -> dark leaves no visible light-only sheet",
        f"stale={stale_dark[:8]}",
    )
    report.check(
        icon_btn.icon().cacheKey() != light_icon,
        "light -> dark re-tints a Lucide glyph",
    )

    # Hidden pages must be correct by the time the curator sees them.
    visit_all_pages(win, app)
    stale_deferred = stale_sheets(win, light_only, widgets)
    report.check(
        not stale_deferred,
        "hidden pages repaint when shown after the switch",
        f"stale={stale_deferred[:8]}",
    )

    theme.set_active_theme("light")
    theme.apply_theme(app, "light", retheme=True)
    visit_all_pages(win, app)
    for _ in range(6):
        app.processEvents()
    stale_light = stale_sheets(win, dark_only, widgets)
    report.check(
        not stale_light,
        "dark -> light leaves no dark-only sheet",
        f"stale={stale_light[:8]}",
    )

    win.close()
    icon_host.close()
    return report.finish()


if __name__ == "__main__":
    sys.exit(main())
