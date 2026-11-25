"""Contract: one type scale, owned by the theme.

Every text size in the app comes from the theme's four-step scale
(``FONT_HEADLINE`` / ``FONT_TITLE`` / ``FONT_BODY`` / ``FONT_SMALL``).
Two ways to honour that:

* a label wears a **token** (its object name is the token: ``HeadlineLG``,
  ``CardTitle``, ``BodyMD``, ``CaptionSM``, ...), and the theme's QSS
  gives it the size;
* a widget that needs a custom stylesheet takes the size from the
  theme's constants (``FONT_SMALL``), not from a literal.

What this file pins down:

* the theme's label tokens resolve to the documented sizes;
* the kit's builders produce the right tokens;
* no module anywhere under ``ui/`` writes a raw ``font-size: Npx`` -- a new
  screen, in any subpackage, cannot quietly introduce a fifth size;
* the only computed font size is the progress ring's geometry-driven label,
  and its floor is pinned so the exception stays legible.
"""

import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QLabel

from ui.theme import (
    FONT_BODY,
    FONT_HEADLINE,
    FONT_SMALL,
    FONT_TITLE,
    global_qss,
)

_UI_DIR = Path(__file__).resolve().parents[1]


def _app_sources() -> Iterator[tuple[Path, str]]:
    """Every application module, including subpackages but not the tests."""
    for path in sorted(_UI_DIR.rglob("*.py")):
        if "tests" in path.parts:
            continue
        yield path, path.read_text(encoding="utf-8")


# A raw size in a stylesheet: "font-size: 13px". Nobody may write one:
# the theme owns the scale, and a literal there is just as much drift as
# a literal in a view (18 of them hid in the theme before dv-i00).
_RAW_SIZE = re.compile(r"font-size:\s*\d+px")

# The size each label token must resolve to.
TOKEN_SIZES = {
    "DisplayLG": FONT_HEADLINE,
    "HeadlineLG": FONT_HEADLINE,
    "HeadlineMD": FONT_TITLE,
    "CardTitle": FONT_TITLE,
    "BodyMD": FONT_BODY,
    "BodySM": FONT_BODY,
    "CaptionSM": FONT_BODY,
    "HintSM": FONT_BODY,
    "StateMD": FONT_SMALL,
    "LabelMD": FONT_SMALL,
    "LabelStrongSM": FONT_SMALL,
    "ValueSM": FONT_SMALL,
}


def test_the_scale_is_a_scale():
    """Four distinct ordered sizes, with a 12px floor for the smallest text."""
    sizes = [
        FONT_SMALL,
        FONT_BODY,
        FONT_TITLE,
        FONT_HEADLINE,
    ]
    assert sizes == sorted(sizes), sizes
    assert len(set(sizes)) == len(sizes), f"two steps share a size: {sizes}"
    assert sizes[0] >= 12, f"the smallest text is below the floor: {sizes}"


def test_every_label_token_is_defined():
    qss = global_qss()
    for token in TOKEN_SIZES:
        assert f"QLabel#{token} {{" in qss, f"the theme has no rule for {token}"


def test_the_kit_builders_use_the_tokens(qapp):
    from ui import widgets

    builders: dict[Callable[..., Any], tuple[str, ...]] = {
        widgets.make_page_heading: ("HeadlineLG",),
        widgets.make_section_heading: ("HeadlineMD",),
        widgets.make_card_title: ("CardTitle",),
        widgets.make_body_label: ("BodyMD",),
        widgets.make_small_body_label: ("BodySM",),
        widgets.make_caption_label: ("CaptionSM",),
        widgets.make_field_label: ("LabelStrongSM",),
        widgets.make_metric_value: ("DisplayLG",),
    }
    for builder, (token,) in builders.items():
        made = builder("x")
        label = made[0] if isinstance(made, tuple) else made
        assert isinstance(label, QLabel)
        assert label.objectName() == token, builder.__name__
        assert label.styleSheet() == "", f"{builder.__name__} writes an inline style"


def test_token_sizes_resolve_to_the_scale(qapp):
    """A label wearing a token really gets that token's size."""
    for token, size in TOKEN_SIZES.items():
        label = QLabel("x")
        label.setObjectName(token)
        label.show()
        qapp.processEvents()
        assert label.font().pixelSize() == size, (
            f"{token}: {label.font().pixelSize()}px, expected {size}px"
        )
        label.hide()


def test_no_raw_font_sizes_anywhere():
    """A new screen in any subpackage cannot introduce a size of its own."""
    hits = []
    for path, source in _app_sources():
        for number, line in enumerate(source.splitlines(), start=1):
            if _RAW_SIZE.search(line):
                hits.append(f"{path.relative_to(_UI_DIR).as_posix()}:{number}")
    assert hits == [], f"raw font sizes outside the scale: {hits}"


def test_computed_font_sizes_are_the_ring_only():
    """SetPixelSize belongs to the theme; the ring is the one exception.

    The ring's percentage has to fit a circle whose size is decided at
    runtime, so it computes a size instead of taking a token. Pinning the
    two call sites stops a view from setting an arbitrary font behind the
    scale's back.
    """
    expected = {
        "theme.py": "font.setPixelSize(FONT_BODY)",
        "ring.py": "font.setPixelSize(self._label_pixel_size(text))",
    }
    found: dict[str, list[tuple[int, str]]] = {}
    for path, source in _app_sources():
        for number, line in enumerate(source.splitlines(), start=1):
            if "setPixelSize(" in line:
                rel = path.relative_to(_UI_DIR).as_posix()
                found.setdefault(rel, []).append((number, line.strip()))
    assert {name: len(calls) for name, calls in found.items()} == dict.fromkeys(expected, 1), found
    for name, call in expected.items():
        assert found[name][0][1] == call, (name, found[name])


def test_the_ring_label_keeps_its_floor(qapp):
    """The off-scale size never falls below the legibility floor."""
    from ui.ring import RingProgress

    for diameter in (12, 24, 40, 80):
        ring = RingProgress(diameter=diameter)
        for text in ("9", "100", "100%"):
            assert ring._label_pixel_size(text) >= 6, (diameter, text)
        ring.deleteLater()
