"""Probe: a live theme switch repaints every scoped sheet.

dv-4jm.7 made the kit factories repaint on a switch; this probe walks the
real window (dashboard, settings, review configuration) and fails if any
widget still wears a colour only the previous theme uses. It is the guard
for view-level sheets - page backgrounds, cards, bands, pills, search
fields, chips, badges, check rows and window chrome (dv-314).

Run: python tools/probes/probe_theme_switch.py
"""

from __future__ import annotations

import sys

from _common import Report, boot


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
    light_only = light - dark
    dark_only = dark - light

    def walk(colours):
        found = []
        for w in [win, *win.findChildren(QWidget)]:
            try:
                sheet = w.styleSheet()
            except Exception:
                continue
            if not sheet:
                continue
            hits = sorted({c for c in colours if c in sheet})
            if hits:
                found.append((w.objectName() or type(w).__name__, hits))
        return found

    theme.set_active_theme("dark")
    theme.apply_theme(app, "dark", retheme=True)
    for _ in range(6):
        app.processEvents()
    stale_dark = walk(light_only)
    report.check(
        not stale_dark,
        "light -> dark leaves no light-only sheet",
        f"stale={stale_dark[:8]}",
    )

    theme.set_active_theme("light")
    theme.apply_theme(app, "light", retheme=True)
    for _ in range(6):
        app.processEvents()
    stale_light = walk(dark_only)
    report.check(
        not stale_light,
        "dark -> light leaves no dark-only sheet",
        f"stale={stale_light[:8]}",
    )

    win.close()
    return report.finish()


if __name__ == "__main__":
    sys.exit(main())
