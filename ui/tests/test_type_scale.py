"""Contract: one type scale, owned by the theme.

Every text size in the app comes from the theme's scale
(``FONT_HEADLINE`` / ``FONT_TITLE`` / ``FONT_SECTION`` / ``FONT_BODY`` /
``FONT_SMALL`` / ``FONT_CAPTION``). Two ways to honour that:

* a label wears a **token** (its object name is the token: ``HeadlineLG``,
  ``CardTitle``, ``BodyMD``, ``CaptionSM``, ...), and the theme's QSS
  gives it the size;
* a widget that needs a custom stylesheet takes the size from the
  theme's constants (``FONT_SMALL``), not from a literal.

What this file pins down:

* the theme's label tokens resolve to the documented sizes;
* the kit's builders produce the right tokens;
* no module outside the theme writes a raw ``font-size: Npx`` -- a new
  screen cannot quietly introduce a thirteenth size.
"""

import re
from pathlib import Path

from PySide6.QtWidgets import QLabel

from ui.theme import (
    FONT_BODY,
    FONT_CAPTION,
    FONT_HEADLINE,
    FONT_SECTION,
    FONT_SMALL,
    FONT_TITLE,
    global_qss,
)

_UI_DIR = Path(__file__).resolve().parents[1]

# A raw size in a stylesheet: "font-size: 13px". The theme may use it
# (it is the scale's home); every other module may not.
_RAW_SIZE = re.compile(r"font-size:\s*\d+px")

# The size each label token must resolve to.
TOKEN_SIZES = {
    "DisplayLG": FONT_HEADLINE,
    "HeadlineLG": FONT_HEADLINE,
    "HeadlineMD": FONT_TITLE,
    "CardTitle": FONT_SECTION,
    "BodyMD": FONT_BODY,
    "BodySM": FONT_SMALL,
    "StateMD": FONT_SMALL,
    "LabelMD": FONT_CAPTION,
    "CaptionSM": FONT_CAPTION,
    "MonoSM": FONT_SMALL,
}


def test_the_scale_is_a_scale():
    """The sizes are distinct and ordered (bigger number = bigger text)."""
    sizes = [
        FONT_CAPTION,
        FONT_SMALL,
        FONT_BODY,
        FONT_SECTION,
        FONT_TITLE,
        FONT_HEADLINE,
    ]
    assert sizes == sorted(sizes), sizes
    assert len(set(sizes)) == len(sizes), f"two steps share a size: {sizes}"


def test_every_label_token_is_defined():
    qss = global_qss()
    for token in TOKEN_SIZES:
        assert f"QLabel#{token} {{" in qss, f"the theme has no rule for {token}"


def test_the_kit_builders_use_the_tokens(qapp):
    from ui import widgets

    builders = {
        widgets.make_page_heading: ("HeadlineLG",),
        widgets.make_section_heading: ("HeadlineMD",),
        widgets.make_card_title: ("CardTitle",),
        widgets.make_body_label: ("BodyMD",),
        widgets.make_small_body_label: ("BodySM",),
        widgets.make_caption_label: ("CaptionSM",),
        widgets.make_field_label: ("LabelMD",),
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


def test_no_raw_font_sizes_outside_the_theme():
    """A new screen cannot quietly introduce a size of its own."""
    hits = []
    for path in sorted(_UI_DIR.glob("*.py")):
        if path.name == "theme.py":
            continue
        for number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if _RAW_SIZE.search(line):
                hits.append(f"{path.name}:{number}")
    assert hits == [], f"raw font sizes outside the theme: {hits}"
