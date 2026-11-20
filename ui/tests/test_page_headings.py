"""Contract: one heading contract for every full-page view.

Settings, Review configuration, Log and About each used to style their
own title, so the four pages drifted apart. They now share
``make_page_heading`` and the theme's ``HeadlineLG`` token. These tests
pin that on the live pages and guard the repo against a new inline
page-heading style.
"""

import re
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QLabel

_UI_DIR = Path(__file__).resolve().parents[1]

# A page title is 22px: that size may only be written in the theme.
_INLINE_HEADING_PX = re.compile(r"font-size:\s*22px")


def _pages(win: Any):
    settings = win._ensure_settings()
    about = win._ensure_about()
    log = win._ensure_log()
    win._show_review_config()
    return [
        ("Settings", settings),
        ("About", about),
        ("Log", log),
        ("Review configuration", win._review_config),
    ]


def test_every_page_has_one_heading(win, qapp):
    for name, page in _pages(win):
        qapp.processEvents()
        headings = [lbl for lbl in page.findChildren(QLabel) if lbl.objectName() == "HeadlineLG"]
        assert len(headings) == 1, f"{name}: {len(headings)} HeadlineLG labels"


def test_headings_carry_no_inline_style(win, qapp):
    for name, page in _pages(win):
        qapp.processEvents()
        for lbl in page.findChildren(QLabel):
            if lbl.objectName() == "HeadlineLG":
                assert lbl.styleSheet() == "", f"{name}: inline heading style"


def test_headings_use_the_same_metrics(win, qapp):
    seen = set()
    for _name, page in _pages(win):
        qapp.processEvents()
        for lbl in page.findChildren(QLabel):
            if lbl.objectName() == "HeadlineLG":
                font = lbl.font()
                seen.add((font.pixelSize(), font.weight()))
    assert seen == {(22, 600)}, f"headings differ: {seen}"


def test_the_theme_owns_the_heading_rule(qapp):
    assert "QLabel#HeadlineLG" in qapp.styleSheet()


def test_no_inline_page_heading_size_outside_the_theme():
    """A 22px label outside the theme is a page heading that drifted."""
    hits = []
    for path in sorted(_UI_DIR.glob("*.py")):
        if path.name == "theme.py":
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if _INLINE_HEADING_PX.search(line):
                hits.append(f"{path.name}:{number}")
    assert hits == [], f"inline 22px styles outside the theme: {hits}"
