"""Every stylesheet builder emits one syntactically balanced string (dv-bjj).

Qt does not raise on a stylesheet it cannot parse: it logs one warning and
drops the sheet, so the widget renders without its face and the page looks
almost right. The badge bug behind this bead was exactly that - one closing
brace too many, because a fragment was left as a plain string in an f-string
expression.

These tests are the cheap, permanent check: build every sheet the theme and
the kit expose, and assert the braces balance and no f-string placeholder
survived. A new builder belongs in ``BUILDERS``.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from functools import partial

import pytest

# A placeholder that never got substituted, e.g. "{SURFACE_CARD}".
_LEFTOVER_TOKEN = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}")


def _builders() -> list[tuple[str, Callable[[], str]]]:
    """One representative sheet per builder, with every branching argument."""
    from ui import theme, widgets

    cases: list[tuple[str, Callable[[], str]]] = [
        ("global_qss", theme.global_qss),
        ("header_section_qss", theme.header_section_qss),
        ("header_section_qss flush", lambda: theme.header_section_qss(flush=True)),
        ("selection_qss", theme.selection_qss),
        ("selection_qss scoped", lambda: theme.selection_qss("QTableWidget")),
        ("scrollbar_lane_qss", theme.scrollbar_lane_qss),
        ("scrollbar_lane_qss scoped", lambda: theme.scrollbar_lane_qss("QTableWidget")),
        ("transparent_qss", theme.transparent_qss),
        (
            "transparent_surface_qss",
            lambda: theme.transparent_surface_qss("Card", "Inset"),
        ),
        (
            "surface_frame_qss",
            lambda: theme.surface_frame_qss(theme.SURFACE_CARD, theme.BORDER_SUBTLE),
        ),
        (
            "surface_frame_qss dashed",
            lambda: theme.surface_frame_qss(
                theme.SURFACE_CARD,
                theme.BORDER_SUBTLE,
                radius=theme.RADIUS_SM,
                selector="QFrame#Empty",
                border_style="dashed",
            ),
        ),
        (
            "band_qss bottom",
            lambda: theme.band_qss(theme.SURFACE_SUBTLE, theme.BORDER_SUBTLE),
        ),
        (
            "band_qss top",
            lambda: theme.band_qss(theme.SURFACE_SUBTLE, theme.BORDER_SUBTLE, edge="top"),
        ),
        (
            "status_strip_qss",
            lambda: theme.status_strip_qss(
                theme.SURFACE_SUBTLE, theme.BORDER_SUBTLE, theme.TEXT_PRIMARY
            ),
        ),
        (
            "status_strip_qss weighted",
            lambda: theme.status_strip_qss(
                theme.SURFACE_SUBTLE,
                theme.BORDER_SUBTLE,
                theme.TEXT_PRIMARY,
                font_size=theme.FONT_SMALL,
                padding="2px 4px",
                selector="QLabel#Strip",
                weight=600,
            ),
        ),
        ("input_qss", lambda: theme.input_qss("QLineEdit")),
        (
            "input_qss mono",
            lambda: theme.input_qss(
                "QPlainTextEdit", font_size=theme.FONT_CAPTION, family="Consolas"
            ),
        ),
        (
            "badge_qss",
            lambda: theme.badge_qss(theme.SURFACE_SUBTLE, theme.TEXT_PRIMARY, theme.BORDER_SUBTLE),
        ),
        (
            "badge_qss sized",
            lambda: theme.badge_qss(
                theme.SURFACE_SUBTLE,
                theme.TEXT_PRIMARY,
                theme.BORDER_SUBTLE,
                font_size=theme.FONT_CAPTION,
                padding="2px 8px",
            ),
        ),
        ("label_badge_style draft", lambda: theme.label_badge_style("draft")),
        ("label_badge_style review", lambda: theme.label_badge_style("In Review")),
        ("label_badge_style unknown", lambda: theme.label_badge_style("Zzz")),
        ("action_button_style", theme.action_button_style),
        (
            "action_button_style primary",
            lambda: theme.action_button_style(primary=True),
        ),
        ("flush_table_style", widgets.flush_table_style),
        (
            "flush_table_style last=False",
            lambda: widgets.flush_table_style(
                last=False,
                header_background=theme.SURFACE_SUBTLE,
                item_padding="2px 6px",
            ),
        ),
        ("flush_list_style", widgets.flush_list_style),
        ("flush_list_style last=False", lambda: widgets.flush_list_style(last=False)),
        ("framed_list_style", widgets.framed_list_style),
        ("tree_style", widgets.tree_style),
        (
            "tree_style framed",
            lambda: widgets.tree_style(flush=False, row_height=None),
        ),
    ]
    for kind in theme.BUTTON_OBJECTS:
        cases.append((f"button_qss {kind}", partial(theme.button_qss, kind)))
        cases.append(
            (
                f"button_qss {kind} scoped",
                partial(theme.button_qss, kind, selector="QPushButton", scope="#TopNav"),
            )
        )
    for state in ("todo", "done", "current", "blocked"):
        cases.append((f"workflow_step_qss {state}", partial(theme.workflow_step_qss, state)))
    return cases


BUILDERS = _builders()


@pytest.mark.parametrize(("name", "builder"), BUILDERS, ids=[name for name, _ in BUILDERS])
def test_sheet_braces_balance(name, builder):
    """As many closing braces as opening ones - Qt drops the sheet otherwise."""
    sheet = builder()
    assert isinstance(sheet, str)
    assert sheet.strip(), f"{name} built nothing"
    opened = sheet.count("{")
    closed = sheet.count("}")
    assert opened == closed, (
        f"{name} has {opened} '{{' and {closed} '}}': Qt drops an unbalanced "
        f"stylesheet with only a warning, so the widget silently loses its face"
    )


@pytest.mark.parametrize(("name", "builder"), BUILDERS, ids=[name for name, _ in BUILDERS])
def test_sheet_has_no_unsubstituted_placeholder(name, builder):
    """An f-string that lost its prefix leaves ``{TOKEN}`` in the output."""
    sheet = builder()
    leftovers = sorted(set(_LEFTOVER_TOKEN.findall(sheet)))
    assert not leftovers, f"{name} still contains {leftovers}"


def test_label_badge_style_is_the_regression_that_started_this(qapp):
    """The badge sheet ends with one brace, not two (the dv-bjj defect)."""
    from ui.theme import label_badge_style

    for label in ("draft", "In Review", "Approved", "Needs Review", "Zzz"):
        sheet = label_badge_style(label)
        assert sheet.startswith("QLabel {"), label
        assert sheet.endswith("}"), label
        assert not sheet.endswith("}}"), label
        assert sheet.count("{") == 1, label
        assert sheet.count("}") == 1, label


def test_every_button_kind_has_a_face(qapp):
    """One rule per named button object, so no kind falls back to a bare button."""
    from ui.theme import BUTTON_OBJECTS, button_qss

    seen = set()
    for kind, object_name in BUTTON_OBJECTS.items():
        sheet = button_qss(kind)
        assert f"#{object_name}" in sheet, f"{kind} does not paint #{object_name}"
        seen.add(object_name)
    assert len(seen) == len(BUTTON_OBJECTS), "two kinds share one object name"
