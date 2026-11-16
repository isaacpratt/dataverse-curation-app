"""Probe: every full-page heading wears the same theme token.

The Settings, Review configuration, Log and About pages each used to
style their own title, so they drifted apart. They now share
``make_page_heading`` and the theme's ``HeadlineLG`` token; this probe
checks that contract on the live pages.

Run: python tools/probes/probe_headings.py
"""

from __future__ import annotations

import sys

from _common import Report, boot


def main() -> int:
    app, cfg = boot()
    from PySide6.QtWidgets import QLabel

    from ui.main_window import MainWindow

    report = Report("page headings")
    win = MainWindow(cfg)
    win.resize(1280, 860)
    win.show()
    for _ in range(10):
        app.processEvents()

    pages = []
    settings = win._ensure_settings()
    for _ in range(5):
        app.processEvents()
    pages.append(("Settings", settings))

    about = win._ensure_about()
    for _ in range(5):
        app.processEvents()
    pages.append(("About", about))

    log = win._ensure_log()
    for _ in range(5):
        app.processEvents()
    pages.append(("Log", log))

    win._show_review_config()
    for _ in range(10):
        app.processEvents()
    pages.append(("Review configuration", win._review_config))

    for name, page in pages:
        labels = [lbl for lbl in page.findChildren(QLabel) if lbl.objectName() == "HeadlineLG"]
        report.check(
            len(labels) == 1,
            f"{name}: exactly one HeadlineLG heading",
            f"found={len(labels)}",
        )
        if not labels:
            continue
        lbl = labels[0]
        report.check(
            lbl.styleSheet() == "",
            f"{name}: the heading carries no inline stylesheet",
            f"style={lbl.styleSheet()[:40]!r}",
        )
        font = lbl.font()
        report.check(
            font.pixelSize() == 22 and font.weight() == 600,
            f"{name}: 22px semibold",
            f"size={font.pixelSize()} weight={font.weight()}",
        )

    report.check(
        "QLabel#HeadlineLG" in app.styleSheet(),
        "the theme owns the HeadlineLG rule",
    )

    win.close()
    return report.finish()


if __name__ == "__main__":
    sys.exit(main())
