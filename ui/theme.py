"""Design tokens for the app (originally extracted from a Tailwind mock).

Palette is Material 3-like: primary #004ccd, tertiary #4142cf, error #ba1a1a,
surface #faf8ff, backgrounds #f2f3ff/#eaedff, outline-variant #c3c6d8.
Typography is bundled: Inter for 12/13px body text, Fraunces for the
16/22px display steps, and JetBrains Mono for identifiers and raw payloads.

The colour layer is split in two: the palette says what a colour IS,
the role layer says what it is FOR, and the role layer is a table per
theme - so switching theme is a table swap, not a re-skin.
"""

import os
import re
import subprocess
import sys
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from PySide6.QtCore import QEvent, QObject
    from PySide6.QtWidgets import (
        QApplication,
        QListWidget,
        QTableWidget,
        QWidget,
    )

# --- Colors ---
PRIMARY = "#004ccd"
PRIMARY_CONTAINER = "#0f62fe"
ON_PRIMARY = "#ffffff"
ON_PRIMARY_FIXED_VARIANT = "#003da9"
PRIMARY_FIXED_DIM = "#b4c5ff"
PRIMARY_FIXED = "#dbe1ff"

TERTIARY = "#4142cf"
TERTIARY_CONTAINER = "#5b5ee9"
ON_TERTIARY_CONTAINER = "#f6f3ff"
TERTIARY_FIXED_DIM = "#c0c1ff"

ERROR = "#ba1a1a"
ERROR_CONTAINER = "#ffdad6"
ON_ERROR_CONTAINER = "#93000a"
ON_ERROR = "#ffffff"

SURFACE = "#faf8ff"
BACKGROUND = "#faf8ff"
SURFACE_BRIGHT = "#faf8ff"
SURFACE_CONTAINER_LOWEST = "#ffffff"
SURFACE_CONTAINER_LOW = "#f2f3ff"
SURFACE_CONTAINER = "#eaedff"
SURFACE_CONTAINER_HIGH = "#e2e7ff"
SURFACE_CONTAINER_HIGHEST = "#dae2fd"
SURFACE_DIM = "#d2d9f4"
SURFACE_VARIANT = "#dae2fd"

OUTLINE_VARIANT = "#c3c6d8"
OUTLINE = "#737687"
# Interactive control edge: heavier than a decorative card edge so an
# input or button boundary clears the 3:1 WCAG 1.4.11 floor on white.
CONTROL_OUTLINE = "#8b90a3"  # 3.2:1 on a card

ON_SURFACE = "#131b2e"
ON_SURFACE_VARIANT = "#424656"
ON_SECONDARY_CONTAINER = "#57657a"
ON_SECONDARY_FIXED = "#0d1c2e"
SECONDARY_CONTAINER = "#d5e3fc"
SECONDARY = "#515f74"

# --- State / accent additions (token pass: every ui colour lives here) ---
SUCCESS = "#16a34a"
SUCCESS_DARK = "#15803d"  # green-700 — "string" tone in the log
WARNING = "#d97706"  # amber-600
WARNING_DARK = "#b45309"  # amber-700 — large-download caution
# Warning state face: amber-tinted row + edge + ink, the counterpart of
# ERROR_SURFACE/ERROR_OUTLINE/ON_ERROR_CONTAINER (dv-gc9: a warning row
# must not wear the error's red face).
WARNING_SURFACE = "#fff4e0"  # fail-warning row face
WARNING_OUTLINE = "#fdba74"  # warning-row edge
ON_WARNING_CONTAINER = "#713f12"  # warning copy on the warning surface
AMBER_700 = "#a16207"  # log java tokens, identifier palette
PRIMARY_DEEP = "#00174c"  # deepest brand blue — live badge text
PRIMARY_PRESSED = "#002a78"
PRIMARY_DISABLED = "#8aa9e8"
ERROR_OUTLINE = "#ffb4ab"  # light-red borders (pill / fail rows)
ERROR_SURFACE = "#fff0ef"  # fail-row face
MUTED_BG = "#f4f5f7"  # disabled cell-button face
MUTED_TEXT = "#7d8598"  # disabled text: 3.7:1 on a card (was 2.5)
MUTED_BORDER = "#dfe3ea"
PILL_BLUE_TEXT = "#1a2e4a"  # in-review pill text
PILL_BLUE_BORDER = "#b9c7df"

# --- Semantic roles: what a colour is FOR -------------------------------
# The palette above says what a colour IS. The roles below say what it is
# FOR, so a component names an intent ("muted text", "card surface")
# instead of a hex value. Two things follow:
#
# * a palette change is an edit in one table, not a hunt through views;
# * the pairing rules below (the contrast contract) become data, so a
#   test can check them instead of a reviewer eyeballing them.
#
# Roles are plain aliases: a role resolves to a palette entry today and
# would resolve to a different one in a second theme.

# --- Text roles ---
TEXT_PRIMARY = ON_SURFACE  # body copy, headings, values
TEXT_MUTED = ON_SURFACE_VARIANT  # captions, hints, timestamps, metadata
TEXT_SUBTLE = ON_SECONDARY_CONTAINER  # de-emphasised hints, field help
# A field's placeholder is the example text ("Search datasets..."). It
# has to read as text (WCAG 1.4.3) without pretending to be the value
# the curator typed: 5.9:1 on a white field, a step below the muted
# body colour.
TEXT_PLACEHOLDER = ON_SECONDARY_CONTAINER
TEXT_ON_ACCENT = ON_PRIMARY  # text on the brand fill
TEXT_ON_TINT = ON_SECONDARY_CONTAINER  # text on a tinted surface
TEXT_ON_SECONDARY = ON_SECONDARY_FIXED  # text on the secondary fill (nav)
TEXT_ON_ERROR = ON_ERROR  # text on the error fill
TEXT_DANGER = ERROR  # error copy
TEXT_SUCCESS = SUCCESS_DARK  # success copy (5.0:1 on a card)
TEXT_WARNING = WARNING_DARK  # warning copy (5.0:1 on a card)
TEXT_AMBER = AMBER_700  # amber copy (log tokens, caution notes)
TEXT_DISABLED = MUTED_TEXT  # disabled control text (3.7:1 on a card)
# A workflow step that cannot run yet is still a step the user reads and
# clicks: it carries body-legible text (8.9:1 on a card), never the
# disabled grey. The lock mark says "blocked"; the text says what.
TEXT_BLOCKED = ON_SURFACE_VARIANT

# --- Surface roles ---
SURFACE_PAGE = BACKGROUND  # the page behind everything
SURFACE_CARD = SURFACE_CONTAINER_LOWEST  # cards, tables, sheets
SURFACE_TINT = SURFACE_CONTAINER  # a tinted panel (header band, hover)
SURFACE_SUBTLE = SURFACE_CONTAINER_LOW  # quiet rows, inset panels
SURFACE_HEADER = SURFACE_CONTAINER  # table and tree header bands
SURFACE_RAISED = SURFACE_CONTAINER_HIGH  # a raised panel (hover, metric card)
SURFACE_ALT = SURFACE_VARIANT  # an alternate surface (divider band)
SURFACE_DISABLED = MUTED_BG  # a disabled control's face

# --- Border roles ---
BORDER_SUBTLE = OUTLINE_VARIANT  # card and section edges
BORDER_CONTROL = CONTROL_OUTLINE  # input / button edges (>= 3:1)
BORDER_DISABLED = MUTED_BORDER  # a disabled control's edge

# --- Accent roles ---
ACCENT_PRIMARY = PRIMARY
ACCENT_PRIMARY_HOVER = ON_PRIMARY_FIXED_VARIANT
ACCENT_PRIMARY_PRESSED = PRIMARY_PRESSED
ACCENT_PRIMARY_DISABLED = PRIMARY_DISABLED
# Keyboard-focus face on a filled (primary) button: a lighter brand blue
# than the resting fill, so the tint reads against the fill itself.
ACCENT_PRIMARY_FOCUS = PRIMARY_CONTAINER
ACCENT_TINT = PRIMARY_FIXED  # selected row / pressed fill
ACCENT_FOCUS_TINT = PRIMARY_FIXED_DIM  # the focus tint's fill
ACCENT_FOCUS_RING = PRIMARY  # the focus ring's stroke (7.2:1 on a card)
ACCENT_PRIMARY_DEEP = PRIMARY_DEEP  # the deepest brand blue (a live badge)
ACCENT_SECONDARY = SECONDARY_CONTAINER  # the secondary fill (nav, selection)
ACCENT_TERTIARY = TERTIARY  # the tertiary accent

# --- State roles ---
STATE_ERROR_BG = ERROR_CONTAINER
STATE_ERROR_SURFACE = ERROR_SURFACE
STATE_ERROR_BORDER = ERROR_OUTLINE
STATE_ERROR_TEXT = ON_ERROR_CONTAINER
STATE_ERROR_GRAPHIC = ERROR  # an error icon or mark (6.5:1 on a card)
STATE_SUCCESS_GRAPHIC = SUCCESS  # a success icon or mark (3.3:1 on a card)
STATE_WARNING_GRAPHIC = WARNING_DARK  # a warning icon or mark (4.5:1 on a card)
STATE_WARNING_SURFACE = WARNING_SURFACE  # a warning row's face
STATE_WARNING_BORDER = WARNING_OUTLINE  # a warning row's edge
STATE_WARNING_INK = ON_WARNING_CONTAINER  # warning copy on that face

# --- Badge roles (a status label's fill, text and border) ---
BADGE_NEUTRAL_BG = "#e4e7f2"
BADGE_NEUTRAL_TEXT = "#424656"
BADGE_NEUTRAL_BORDER = "#c3c6d8"
BADGE_BLUE_BG = "#d5e3fc"
BADGE_BLUE_TEXT = "#1a2e4a"
BADGE_BLUE_BORDER = "#b9c7df"
BADGE_GREEN_BG = "#15803d"  # SUCCESS_DARK: white on it clears 5:1
BADGE_GREEN_TEXT = "#ffffff"
BADGE_GREEN_BORDER = "#15803d"
BADGE_RED_BG = "#ba1a1a"
BADGE_RED_TEXT = "#ffffff"
BADGE_RED_BORDER = "#ba1a1a"
BADGE_RED_SOFT_BG = "#ffdad6"
BADGE_RED_SOFT_TEXT = "#93000a"
BADGE_RED_SOFT_BORDER = "#ffb4ab"
BADGE_GREY_BG = "#515f74"
BADGE_GREY_TEXT = "#ffffff"
BADGE_GREY_BORDER = "#515f74"
BADGE_GREEN_SOFT_BG = "#dff5e1"
BADGE_GREEN_SOFT_TEXT = "#14532d"
BADGE_GREEN_SOFT_BORDER = "#a7e3b5"
BADGE_INDIGO_BG = "#e2e8ff"
BADGE_INDIGO_TEXT = "#3730a3"
BADGE_INDIGO_BORDER = "#c7d2fe"
BADGE_ORANGE_BG = "#ffedd5"
BADGE_ORANGE_TEXT = "#9a3412"
BADGE_ORANGE_BORDER = "#fdba74"
BADGE_VIOLET_BG = "#e7e4ff"
BADGE_VIOLET_TEXT = "#4142cf"
BADGE_VIOLET_BORDER = "#c0c1ff"
BADGE_AMBER_BG = "#fef3c7"
BADGE_AMBER_TEXT = "#92400e"
BADGE_AMBER_BORDER = "#fcd34d"
BADGE_TEAL_BG = "#d7f3f0"
BADGE_TEAL_TEXT = "#0f766e"
BADGE_TEAL_BORDER = "#99e4dc"
BADGE_PINK_BG = "#fce7f3"
BADGE_PINK_TEXT = "#9d174d"
BADGE_PINK_BORDER = "#f9a8d4"
BADGE_LIME_BG = "#ecfccb"
BADGE_LIME_TEXT = "#3f6212"
BADGE_LIME_BORDER = "#bef264"
BADGE_SKY_BG = "#e0f2fe"
BADGE_SKY_TEXT = "#0c4a6e"
BADGE_SKY_BORDER = "#bae6fd"
BADGE_SAND_BG = "#f5efe6"
BADGE_SAND_TEXT = "#713f12"
BADGE_SAND_BORDER = "#e7d5b7"

# --- Role tables: one mapping per theme ---------------------------------
# The role layer is data. A role name maps to the colour that role
# wears *in a theme*, so switching theme is a table swap: the palette
# stays, the components stay, the views stay - only the mapping moves.
#
# `light` is the table the app paints today (the aliases above).
# `dark` is the second table. Dark mode is planned in five steps and
# this is step one: the mapping exists first, so the per-theme
# stylesheet, the per-theme contrast contract, the painted assets and
# the both-themes gallery have something to select.
#
# The role *names* never change between themes - only what a name
# resolves to.

# Every role the app paints. The light table is derived from these
# names (the aliases above stay the one source of truth for what
# light looks like); the dark table declares the same names, so a
# table swap can never miss a role.
_ROLE_NAMES: tuple[str, ...] = (
    "TEXT_PRIMARY",
    "TEXT_MUTED",
    "TEXT_SUBTLE",
    "TEXT_PLACEHOLDER",
    "TEXT_ON_ACCENT",
    "TEXT_ON_TINT",
    "TEXT_ON_SECONDARY",
    "TEXT_ON_ERROR",
    "TEXT_DANGER",
    "TEXT_SUCCESS",
    "TEXT_WARNING",
    "TEXT_AMBER",
    "TEXT_DISABLED",
    "TEXT_BLOCKED",
    "SURFACE_PAGE",
    "SURFACE_CARD",
    "SURFACE_TINT",
    "SURFACE_SUBTLE",
    "SURFACE_HEADER",
    "SURFACE_RAISED",
    "SURFACE_ALT",
    "SURFACE_DISABLED",
    "BORDER_SUBTLE",
    "BORDER_CONTROL",
    "BORDER_DISABLED",
    "ACCENT_PRIMARY",
    "ACCENT_PRIMARY_HOVER",
    "ACCENT_PRIMARY_PRESSED",
    "ACCENT_PRIMARY_DISABLED",
    # Keyboard-focus face on a filled (primary) button: a lighter brand
    # blue than the resting fill, so the tint reads on the fill itself.
    "ACCENT_PRIMARY_FOCUS",
    "ACCENT_TINT",
    "ACCENT_FOCUS_TINT",
    "ACCENT_FOCUS_RING",
    "ACCENT_PRIMARY_DEEP",
    "ACCENT_SECONDARY",
    "ACCENT_TERTIARY",
    "STATE_ERROR_BG",
    "STATE_ERROR_SURFACE",
    "STATE_ERROR_BORDER",
    "STATE_ERROR_TEXT",
    "STATE_ERROR_GRAPHIC",
    "STATE_SUCCESS_GRAPHIC",
    "STATE_WARNING_GRAPHIC",
    "STATE_WARNING_SURFACE",
    "STATE_WARNING_BORDER",
    "STATE_WARNING_INK",
    "BADGE_NEUTRAL_BG",
    "BADGE_NEUTRAL_TEXT",
    "BADGE_NEUTRAL_BORDER",
    "BADGE_BLUE_BG",
    "BADGE_BLUE_TEXT",
    "BADGE_BLUE_BORDER",
    "BADGE_GREEN_BG",
    "BADGE_GREEN_TEXT",
    "BADGE_GREEN_BORDER",
    "BADGE_RED_BG",
    "BADGE_RED_TEXT",
    "BADGE_RED_BORDER",
    "BADGE_RED_SOFT_BG",
    "BADGE_RED_SOFT_TEXT",
    "BADGE_RED_SOFT_BORDER",
    "BADGE_GREY_BG",
    "BADGE_GREY_TEXT",
    "BADGE_GREY_BORDER",
    "BADGE_GREEN_SOFT_BG",
    "BADGE_GREEN_SOFT_TEXT",
    "BADGE_GREEN_SOFT_BORDER",
    "BADGE_INDIGO_BG",
    "BADGE_INDIGO_TEXT",
    "BADGE_INDIGO_BORDER",
    "BADGE_ORANGE_BG",
    "BADGE_ORANGE_TEXT",
    "BADGE_ORANGE_BORDER",
    "BADGE_VIOLET_BG",
    "BADGE_VIOLET_TEXT",
    "BADGE_VIOLET_BORDER",
    "BADGE_AMBER_BG",
    "BADGE_AMBER_TEXT",
    "BADGE_AMBER_BORDER",
    "BADGE_TEAL_BG",
    "BADGE_TEAL_TEXT",
    "BADGE_TEAL_BORDER",
    "BADGE_PINK_BG",
    "BADGE_PINK_TEXT",
    "BADGE_PINK_BORDER",
    "BADGE_LIME_BG",
    "BADGE_LIME_TEXT",
    "BADGE_LIME_BORDER",
    "BADGE_SKY_BG",
    "BADGE_SKY_TEXT",
    "BADGE_SKY_BORDER",
    "BADGE_SAND_BG",
    "BADGE_SAND_TEXT",
    "BADGE_SAND_BORDER",
)

# The light table: today's colours, read from the aliases above so
# there is exactly one source of truth for what light looks like.
LIGHT_ROLE_TABLE: dict[str, str] = {name: globals()[name] for name in _ROLE_NAMES}

# The dark table: the same roles, painted on a dark surface. The brand
# stays blue (the palette does not move), but the ink flips: on a dark
# surface the body ink is light, and text on the brand fill turns dark
# so it still clears 4.5:1.
DARK_ROLE_TABLE: dict[str, str] = {
    "TEXT_PRIMARY": "#e8eaf2",
    "TEXT_MUTED": "#b7bccb",
    "TEXT_SUBTLE": "#9aa0b3",
    "TEXT_PLACEHOLDER": "#9aa0b3",
    "TEXT_ON_ACCENT": "#0b1220",
    "TEXT_ON_TINT": "#c8cddb",
    "TEXT_ON_SECONDARY": "#e8eaf2",
    "TEXT_ON_ERROR": "#ffffff",
    "TEXT_DANGER": "#ffb4ab",
    "TEXT_SUCCESS": "#7ee2a8",
    "TEXT_WARNING": "#ffcf7a",
    "TEXT_AMBER": "#f0c36a",
    "TEXT_DISABLED": "#8b91a3",
    "TEXT_BLOCKED": "#b7bccb",
    "SURFACE_PAGE": "#11131a",
    "SURFACE_CARD": "#191c25",
    "SURFACE_TINT": "#232735",
    "SURFACE_SUBTLE": "#1f2330",
    "SURFACE_HEADER": "#242938",
    "SURFACE_RAISED": "#2a3040",
    "SURFACE_ALT": "#20242f",
    "SURFACE_DISABLED": "#252936",
    "BORDER_SUBTLE": "#343a4b",
    "BORDER_CONTROL": "#6b7488",
    "BORDER_DISABLED": "#333849",
    "ACCENT_PRIMARY": "#6ea8ff",
    "ACCENT_PRIMARY_HOVER": "#8bbaff",
    "ACCENT_PRIMARY_PRESSED": "#4d8bff",
    "ACCENT_PRIMARY_DISABLED": "#3d5a8f",
    "ACCENT_PRIMARY_FOCUS": "#8bbaff",
    "ACCENT_TINT": "#1c3357",
    "ACCENT_FOCUS_TINT": "#24406b",
    "ACCENT_FOCUS_RING": "#8bbaff",
    "ACCENT_PRIMARY_DEEP": "#b4c5ff",
    "ACCENT_SECONDARY": "#2b3348",
    "ACCENT_TERTIARY": "#a9a7ff",
    "STATE_ERROR_BG": "#4a1c1c",
    "STATE_ERROR_SURFACE": "#33191c",
    "STATE_ERROR_BORDER": "#ffb4ab",
    "STATE_ERROR_TEXT": "#ffdad6",
    "STATE_ERROR_GRAPHIC": "#d92d20",
    "STATE_SUCCESS_GRAPHIC": "#4ade80",
    "STATE_WARNING_GRAPHIC": "#fbbf24",
    "STATE_WARNING_SURFACE": "#3d2c12",
    "STATE_WARNING_BORDER": "#a16207",
    "STATE_WARNING_INK": "#fde68a",
    "BADGE_NEUTRAL_BG": "#2b3040",
    "BADGE_NEUTRAL_TEXT": "#d6dae6",
    "BADGE_NEUTRAL_BORDER": "#454c60",
    "BADGE_BLUE_BG": "#16345e",
    "BADGE_BLUE_TEXT": "#cfe1ff",
    "BADGE_BLUE_BORDER": "#2f5b96",
    "BADGE_GREEN_BG": "#123c2a",
    "BADGE_GREEN_TEXT": "#bbf7d0",
    "BADGE_GREEN_BORDER": "#166534",
    "BADGE_RED_BG": "#4d1717",
    "BADGE_RED_TEXT": "#fecaca",
    "BADGE_RED_BORDER": "#7f1d1d",
    "BADGE_RED_SOFT_BG": "#3a1a1a",
    "BADGE_RED_SOFT_TEXT": "#fecaca",
    "BADGE_RED_SOFT_BORDER": "#7f1d1d",
    "BADGE_GREY_BG": "#3b4252",
    "BADGE_GREY_TEXT": "#e2e8f0",
    "BADGE_GREY_BORDER": "#4b5563",
    "BADGE_GREEN_SOFT_BG": "#123524",
    "BADGE_GREEN_SOFT_TEXT": "#bbf7d0",
    "BADGE_GREEN_SOFT_BORDER": "#166534",
    "BADGE_INDIGO_BG": "#232a5e",
    "BADGE_INDIGO_TEXT": "#c7d2fe",
    "BADGE_INDIGO_BORDER": "#3730a3",
    "BADGE_ORANGE_BG": "#4a2c10",
    "BADGE_ORANGE_TEXT": "#fed7aa",
    "BADGE_ORANGE_BORDER": "#9a3412",
    "BADGE_VIOLET_BG": "#2e2359",
    "BADGE_VIOLET_TEXT": "#ddd6fe",
    "BADGE_VIOLET_BORDER": "#4c1d95",
    "BADGE_AMBER_BG": "#453012",
    "BADGE_AMBER_TEXT": "#fde68a",
    "BADGE_AMBER_BORDER": "#92400e",
    "BADGE_TEAL_BG": "#103b38",
    "BADGE_TEAL_TEXT": "#99f6e4",
    "BADGE_TEAL_BORDER": "#0f766e",
    "BADGE_PINK_BG": "#4a1636",
    "BADGE_PINK_TEXT": "#fbcfe8",
    "BADGE_PINK_BORDER": "#9d174d",
    "BADGE_LIME_BG": "#2b3d12",
    "BADGE_LIME_TEXT": "#d9f99d",
    "BADGE_LIME_BORDER": "#3f6212",
    "BADGE_SKY_BG": "#0c3040",
    "BADGE_SKY_TEXT": "#bae6fd",
    "BADGE_SKY_BORDER": "#075985",
    "BADGE_SAND_BG": "#3d2f1c",
    "BADGE_SAND_TEXT": "#e7d5b7",
    "BADGE_SAND_BORDER": "#713f12",
}

# Every theme the app can select.
ROLE_TABLES: dict[str, dict[str, str]] = {
    "light": LIGHT_ROLE_TABLE,
    "dark": DARK_ROLE_TABLE,
}

# The theme the app paints.
ACTIVE_THEME = "light"


def role_table(theme: str | None = None) -> Mapping[str, str]:
    """Return the role mapping for a theme (the active one by default)."""
    name = theme or ACTIVE_THEME
    table = ROLE_TABLES.get(name)
    if table is None:
        raise KeyError(f"unknown theme {name!r}; known themes: {sorted(ROLE_TABLES)}")
    return table


def role(name: str, theme: str | None = None) -> str:
    """Resolve one role name to the colour it wears in a theme."""
    table = role_table(theme)
    try:
        return table[name]
    except KeyError:
        raise KeyError(f"unknown role {name!r} in theme {theme or ACTIVE_THEME!r}") from None


#: Which of our semantic roles back a standard ``QPalette`` role. Only
#: generic colours can live in the palette: Qt exposes 21 roles, while the
#: app stylesheet uses 29 distinct ones. Role-specific faces (badges, state
#: colours, focus tints) stay in scoped sheets and are re-tinted by the
#: retheme hook.
PALETTE_ROLE_MAP: dict[str, str] = {
    "SURFACE_PAGE": "Window",
    "SURFACE_CARD": "Base",
    "SURFACE_SUBTLE": "AlternateBase",
    "SURFACE_TINT": "Midlight",
    "SURFACE_RAISED": "Light",
    "SURFACE_ALT": "Shadow",
    "BORDER_SUBTLE": "Dark",
    "BORDER_CONTROL": "Mid",
    "ACCENT_PRIMARY": "Highlight",
    "ACCENT_SECONDARY": "Accent",
    "ACCENT_TINT": "ToolTipBase",
    "TEXT_PRIMARY": "WindowText",
    "TEXT_MUTED": "Text",
    "TEXT_ON_ACCENT": "HighlightedText",
    "TEXT_ON_SECONDARY": "BrightText",
    "TEXT_ON_TINT": "ToolTipText",
    "TEXT_PLACEHOLDER": "PlaceholderText",
    "TEXT_SUCCESS": "Link",
    "TEXT_WARNING": "LinkVisited",
}


#: App-sheet-only fallbacks for roles with no distinct QPalette slot.
#: Duplicates are fine here: scoped sheets keep the exact role colour on
#: the widgets that own those faces, so the app sheet only needs a
#: theme-correct approximation.
PALETTE_QSS_FALLBACK: dict[str, str] = {
    "ACCENT_FOCUS_TINT": "ToolTipBase",
    "ACCENT_FOCUS_RING": "Shadow",
    "ACCENT_TERTIARY": "LinkVisited",
    "BADGE_BLUE_BORDER": "Dark",
    "BADGE_BLUE_TEXT": "Text",
    "STATE_ERROR_BG": "AlternateBase",
    "STATE_ERROR_BORDER": "Dark",
    "STATE_ERROR_GRAPHIC": "LinkVisited",
    "STATE_ERROR_SURFACE": "Base",
    "STATE_ERROR_TEXT": "BrightText",
}


def _qt_qss_token(qt_role: str) -> str:
    """Return Qt's hyphenated stylesheet name for a QPalette role."""
    special = {"ToolTipBase": "tooltip-base", "ToolTipText": "tooltip-text"}
    return special.get(qt_role, re.sub(r"(?<!^)(?=[A-Z])", "-", qt_role).lower())


def palette_qss() -> str:
    """Return one theme-independent application stylesheet.

    Colours come from ``palette(<role>)``, so switching the app palette
    re-colours the app without calling ``setStyleSheet`` again. That call
    costs ~1ms per live widget on a populated window; a palette swap is
    effectively free. Exact, role-specific faces stay in scoped sheets
    and are re-tinted by the retheme hook.
    """
    original: Callable[[str, str | None], str] = cast(
        Callable[[str, str | None], str], globals()["role"]
    )
    mapping = {**PALETTE_QSS_FALLBACK, **PALETTE_ROLE_MAP}

    def mapped(name: str, theme: str | None = None) -> str:
        qt_role = mapping.get(name)
        if qt_role is None:
            return original(name, theme)
        return f"palette({_qt_qss_token(qt_role)})"

    globals()["role"] = mapped
    try:
        sheet = global_qss("light")
    finally:
        globals()["role"] = original
    # Qt accepts palette() in colour values, not in the `background`
    # shorthand.
    return re.sub(r"background: palette\(([^)]+)\)", r"background-color: palette(\1)", sheet)


def palette_for(theme: str | None = None) -> Any:
    """Return a ``QPalette`` carrying the active theme's generic roles.

    A palette swap is effectively free (~0.0s on a 1,200-widget window)
    against ~1.05s for a stylesheet swap, so generic colours should come
    from the palette and only structural/role-specific QSS should be
    re-applied on a switch.
    """
    from PySide6.QtGui import QColor, QPalette

    table_name = theme or ACTIVE_THEME
    palette = QPalette()
    for role_name, qt_name in PALETTE_ROLE_MAP.items():
        qt_role = getattr(QPalette.ColorRole, qt_name)
        palette.setColor(qt_role, QColor(role(role_name, table_name)))
    return palette


def colour(value: str, theme: str | None = None) -> str:
    """Return ``value`` as a colour, resolving a role name when it is one.

    Generators that take a fill or an edge accept either a role name
    (``"SURFACE_CARD"``) or a literal (``"#ffffff"``). The name form is
    what lets a scoped sheet be rebuilt on a live theme switch: the
    stored argument is the role, so re-running the generator in the new
    theme resolves it again. A literal is returned untouched.
    """
    if not isinstance(value, str):
        return value
    table = role_table(theme)
    return table.get(value, value)


def set_active_theme(name: str) -> None:
    """Select the active role table.

    The role names stay the same; only the table they resolve through
    changes. The theme's own rules read the module's role values when
    they build a rule, so a repaint after the swap follows the new
    table.

    The kit and the views import role values by name, so they keep the
    table they imported until the per-theme stylesheet step repaints
    them - until then the app runs on light. The contrast contract is
    still the light one, for the same reason.
    """
    global ACTIVE_THEME
    table = role_table(name)
    ACTIVE_THEME = name
    globals().update(table)


def _qt_color_scheme() -> str | None:
    """Ask Qt for the OS colour scheme, or return None when it cannot say.

    Qt 6.5+ exposes the desktop's light/dark preference through
    ``QStyleHints.colorScheme()``. It is the platform-native source and
    needs no registry reads or subprocesses. Headless/offscreen runs (and
    older Qt) report ``Unknown``, which is why the platform fallbacks in
    :func:`detect_os_theme` still matter.
    """
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication

        app = cast(Any, QApplication.instance())
        if app is None:
            return None
        scheme = app.styleHints().colorScheme()
        if scheme == Qt.ColorScheme.Dark:
            return "dark"
        if scheme == Qt.ColorScheme.Light:
            return "light"
    except Exception:
        return None
    return None


def detect_os_theme() -> str:
    """Return "light" or "dark" for the desktop's current appearance.

    Qt's colour scheme is consulted first. Where Qt cannot answer (or no
    application exists yet), the platform fallbacks are:

    * **Windows** - ``AppsUseLightTheme`` under the per-user Personalize
      key (0 = dark).
    * **macOS** - ``defaults read -g AppleInterfaceStyle`` prints
      ``Dark`` in dark mode and exits non-zero in light mode (the key is
      absent), so the exit status carries the answer.
    * **Linux/GNOME** - ``gsettings get org.gnome.desktop.interface
      color-scheme`` returns ``prefer-dark`` or ``prefer-light`` (older
      GNOME only has ``gtk-theme``; a dark theme name is the fallback).

    Anything else, or any failure, reads as light: a wrong guess must
    never leave the curator on an unreadable palette.
    """
    qt_scheme = _qt_color_scheme()
    if qt_scheme is not None:
        return qt_scheme
    platform = sys.platform
    try:
        if platform.startswith("win"):
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            ) as key:
                value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return "light" if value else "dark"

        if platform == "darwin":
            result = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            # Non-zero exit = the key is unset = light mode.
            return "dark" if result.returncode == 0 else "light"

        if platform.startswith("linux"):
            result = subprocess.run(
                [
                    "gsettings",
                    "get",
                    "org.gnome.desktop.interface",
                    "color-scheme",
                ],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            if result.returncode == 0:
                scheme = result.stdout.strip().strip("'\"")
                if scheme in ("prefer-dark", "dark"):
                    return "dark"
                if scheme in ("prefer-light", "light", "default"):
                    return "light"
            # Older GNOME: the GTK theme name is the only signal.
            result = subprocess.run(
                ["gsettings", "get", "org.gnome.desktop.interface", "gtk-theme"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            if result.returncode == 0:
                name = result.stdout.strip().strip("'\"").lower()
                if "dark" in name:
                    return "dark"
    except Exception:
        pass
    return "light"


def resolve_theme_mode(mode: str) -> str:
    """Map a config theme mode to the palette to paint.

    ``"light"``/``"dark"`` pass through; ``"auto"`` (and anything
    unrecognised) asks the OS, falling back to light.
    """
    if mode in ("light", "dark"):
        return mode
    return detect_os_theme()


# --- Typography (Qt QSS uses px) ---
# All three faces are bundled in ui/assets/fonts and registered by
# register_fonts(); the trailing names are system fallbacks if a file cannot
# be loaded. Fraunces is the display face for the 16px and 22px steps.
FONT_FAMILY = "Inter, 'Segoe UI', sans-serif"
HEADING_FAMILY = "Fraunces, Georgia, serif"
MONO_FAMILY = "'JetBrains Mono', Consolas, monospace"

# (family, file) pairs; the files are shipped by PyInstaller with ui/assets.
BUNDLED_FONTS: tuple[tuple[str, str], ...] = (
    ("Inter", "Inter.ttf"),
    ("Fraunces", "Fraunces.ttf"),
    ("JetBrains Mono", "JetBrainsMono.ttf"),
)

# --- Radii / Sizes ---
# Unified app-wide corner radius: everything (cards, inputs, tables, panes,
# buttons, badges, menus) uses RADIUS_LG, matching the dropdown menus. The
# smaller tokens stay defined for reference; only structural square junctions
# (combo-popup seam, tab-pane seam, caption buttons) keep 0px corners.
RADIUS_XL = "12px"
RADIUS_LG = "8px"
RADIUS_MD = "6px"
RADIUS_SM = "4px"

# --- Spacing scale (px) — layouts should use these, not magic numbers ---
SP_XS = 4
SP_SM = 8
SP_MD = 12
SP_LG = 16
SP_XL = 20
SP_XXL = 24

# --- Standard margins ---
MARGIN_PAGE = 24  # outer view padding
MARGIN_CARD_H = 16  # card header/body horizontal padding
MARGIN_CARD_V = 12  # card header/body vertical padding

# --- Type scale (px) ---
FONT_HEADLINE = 22
FONT_TITLE = 16
FONT_BODY = 13
FONT_SMALL = 12

# --- Shadows (simulated via border) ---
CARD_BORDER = f"1px solid {OUTLINE_VARIANT}"

# --- Elevation (a real, subtle drop shadow behind cards and chips) ---
# QSS has no box-shadow, so elevation is a QGraphicsDropShadowEffect. The
# numbers are deliberately small: the page already separates surfaces with
# a border, and the shadow only says "this sits above the page".
SHADOW_BLUR = 18
SHADOW_DY = 2
SHADOW_ALPHA = 22  # ~9% black at the darkest point
SHADOW_COLOR = (16, 24, 40)  # a cool near-black, not pure #000

# A chip is small and sits ON the card, so it gets a tighter shadow than a
# card does: less blur, no offset, a touch lighter.
CHIP_SHADOW_BLUR = 10
CHIP_SHADOW_DY = 1
CHIP_SHADOW_ALPHA = 16


def apply_elevation(
    widget: "QWidget",
    *,
    blur: int = SHADOW_BLUR,
    dy: int = SHADOW_DY,
    alpha: int = SHADOW_ALPHA,
) -> None:
    """Give a card or chip one subtle shadow (the app's elevation contract).

    Reuses the widget's existing drop-shadow effect if it already has one,
    so calling this twice never stacks two effects. Never raises: a widget
    without a native graphics effect simply keeps its border.
    """
    try:
        from PySide6.QtGui import QColor
        from PySide6.QtWidgets import QGraphicsDropShadowEffect

        effect = widget.graphicsEffect()
        if not isinstance(effect, QGraphicsDropShadowEffect):
            effect = QGraphicsDropShadowEffect(widget)
        effect.setBlurRadius(blur)
        effect.setOffset(0, dy)
        r, g, b = SHADOW_COLOR
        effect.setColor(QColor(r, g, b, alpha))
        widget.setGraphicsEffect(effect)
    except Exception:
        pass


# --- Contrast contract ---------------------------------------------------
# Every colour pairing the app actually paints, with the ratio it must
# clear. `ui/tests/test_contrast.py` reads this table, so a palette
# change that breaks legibility fails the build instead of shipping.
#
# kind:
#   "text"    normal-size text (WCAG AA: 4.5:1)
#   "graphic" icons and other non-text marks (3:1)
#   "disabled" disabled controls are exempt from WCAG 1.4.3; the app
#             still holds them to 3:1 so they stay readable.
CONTRAST_PAIRS: tuple[tuple[str, str, str, str, float], ...] = (
    # label, foreground, background, kind, minimum ratio
    ("body text on a card", TEXT_PRIMARY, SURFACE_CARD, "text", 4.5),
    ("body text on the page", TEXT_PRIMARY, SURFACE_PAGE, "text", 4.5),
    ("muted text on a card", TEXT_MUTED, SURFACE_CARD, "text", 4.5),
    ("muted text on the page", TEXT_MUTED, SURFACE_PAGE, "text", 4.5),
    ("muted text on a tinted panel", TEXT_MUTED, SURFACE_TINT, "text", 4.5),
    ("body text on a tinted panel", TEXT_PRIMARY, SURFACE_TINT, "text", 4.5),
    ("body text on a subtle panel", TEXT_PRIMARY, SURFACE_SUBTLE, "text", 4.5),
    ("body text on the error surface", TEXT_PRIMARY, STATE_ERROR_BG, "text", 4.5),
    ("success mark on a tinted panel", TEXT_SUCCESS, SURFACE_TINT, "graphic", 3.0),
    ("caution mark on a tinted panel", TEXT_AMBER, SURFACE_TINT, "graphic", 3.0),
    ("error mark on the error surface", TEXT_DANGER, STATE_ERROR_BG, "graphic", 3.0),
    ("subtle hint text on a card", TEXT_SUBTLE, SURFACE_CARD, "text", 4.5),
    ("text on the brand fill", TEXT_ON_ACCENT, ACCENT_PRIMARY, "text", 4.5),
    ("text on a tint", TEXT_ON_TINT, SURFACE_TINT, "text", 4.5),
    ("error text on a card", TEXT_DANGER, SURFACE_CARD, "text", 4.5),
    ("warning ink on warning fill", STATE_WARNING_INK, STATE_WARNING_SURFACE, "text", 4.5),
    ("warning mark on warning fill", STATE_WARNING_GRAPHIC, STATE_WARNING_SURFACE, "graphic", 3.0),
    ("error text on the error surface", STATE_ERROR_TEXT, STATE_ERROR_SURFACE, "text", 4.5),
    ("success text on a card", TEXT_SUCCESS, SURFACE_CARD, "text", 4.5),
    ("warning text on a card", TEXT_WARNING, SURFACE_CARD, "text", 4.5),
    ("brand text on a card", ACCENT_PRIMARY, SURFACE_CARD, "text", 4.5),
    ("brand text on the page", ACCENT_PRIMARY, SURFACE_PAGE, "text", 4.5),
    ("muted text on a raised panel", TEXT_MUTED, SURFACE_RAISED, "text", 4.5),
    ("subtle hint text on the page", TEXT_SUBTLE, SURFACE_PAGE, "text", 4.5),
    ("subtle hint text on a card", TEXT_SUBTLE, SURFACE_CARD, "text", 4.5),
    ("subtle hint text on a raised panel", TEXT_SUBTLE, SURFACE_RAISED, "text", 4.5),
    ("text on the secondary fill", TEXT_ON_SECONDARY, ACCENT_SECONDARY, "text", 4.5),
    ("text on the error fill", TEXT_ON_ERROR, STATE_ERROR_GRAPHIC, "text", 4.5),
    ("amber text on a card", TEXT_AMBER, SURFACE_CARD, "text", 4.5),
    ("blocked step text on a card", TEXT_BLOCKED, SURFACE_CARD, "text", 4.5),
    ("blocked step text on the page", TEXT_BLOCKED, SURFACE_PAGE, "text", 4.5),
    ("disabled text on a card", TEXT_DISABLED, SURFACE_CARD, "disabled", 3.0),
    ("disabled text on the page", TEXT_DISABLED, SURFACE_PAGE, "disabled", 3.0),
    ("disabled primary label", TEXT_PRIMARY, ACCENT_PRIMARY_DISABLED, "disabled", 3.0),
    ("success icon on a card", STATE_SUCCESS_GRAPHIC, SURFACE_CARD, "graphic", 3.0),
    ("warning icon on a card", STATE_WARNING_GRAPHIC, SURFACE_CARD, "graphic", 3.0),
    ("error icon on a card", STATE_ERROR_GRAPHIC, SURFACE_CARD, "graphic", 3.0),
    ("brand icon on a card", ACCENT_PRIMARY, SURFACE_CARD, "graphic", 3.0),
    ("tertiary icon on a card", ACCENT_TERTIARY, SURFACE_CARD, "graphic", 3.0),
    ("control edge on a card", BORDER_CONTROL, SURFACE_CARD, "graphic", 3.0),
    ("control edge on the page", BORDER_CONTROL, SURFACE_PAGE, "graphic", 3.0),
    ("placeholder text on a field", TEXT_PLACEHOLDER, SURFACE_CONTAINER_LOWEST, "text", 4.5),
    ("focus ring on a card", ACCENT_FOCUS_RING, SURFACE_CARD, "graphic", 3.0),
)

# Dark theme contrast pairs: same semantic pairings, dark role table.
# The pairings are identical in structure; the dark role table provides
# the dark colours. The test checks both tables so a dark palette that
# fails legibility fails the build exactly like a light one.
CONTRAST_PAIRS_DARK: tuple[tuple[str, str, str, str, float], ...] = (
    # label, foreground, background, kind, minimum ratio
    ("body text on a card", "TEXT_PRIMARY", "SURFACE_CARD", "text", 4.5),
    ("body text on the page", "TEXT_PRIMARY", "SURFACE_PAGE", "text", 4.5),
    ("muted text on a card", "TEXT_MUTED", "SURFACE_CARD", "text", 4.5),
    ("muted text on the page", "TEXT_MUTED", "SURFACE_PAGE", "text", 4.5),
    ("muted text on a tinted panel", "TEXT_MUTED", "SURFACE_TINT", "text", 4.5),
    ("body text on a tinted panel", "TEXT_PRIMARY", "SURFACE_TINT", "text", 4.5),
    ("body text on a subtle panel", "TEXT_PRIMARY", "SURFACE_SUBTLE", "text", 4.5),
    ("body text on the error surface", "TEXT_PRIMARY", "STATE_ERROR_BG", "text", 4.5),
    ("success mark on a tinted panel", "TEXT_SUCCESS", "SURFACE_TINT", "graphic", 3.0),
    ("caution mark on a tinted panel", "TEXT_AMBER", "SURFACE_TINT", "graphic", 3.0),
    ("error mark on the error surface", "TEXT_DANGER", "STATE_ERROR_BG", "graphic", 3.0),
    ("subtle hint text on a card", "TEXT_SUBTLE", "SURFACE_CARD", "text", 4.5),
    ("text on the brand fill", "TEXT_ON_ACCENT", "ACCENT_PRIMARY", "text", 4.5),
    ("text on a tint", "TEXT_ON_TINT", "SURFACE_TINT", "text", 4.5),
    ("error text on a card", "TEXT_DANGER", "SURFACE_CARD", "text", 4.5),
    ("error text on the error surface", "STATE_ERROR_TEXT", "STATE_ERROR_SURFACE", "text", 4.5),
    ("warning ink on warning fill", "STATE_WARNING_INK", "STATE_WARNING_SURFACE", "text", 4.5),
    (
        "warning mark on warning fill",
        "STATE_WARNING_GRAPHIC",
        "STATE_WARNING_SURFACE",
        "graphic",
        3.0,
    ),
    ("success text on a card", "TEXT_SUCCESS", "SURFACE_CARD", "text", 4.5),
    ("warning text on a card", "TEXT_WARNING", "SURFACE_CARD", "text", 4.5),
    ("brand text on a card", "ACCENT_PRIMARY", "SURFACE_CARD", "text", 4.5),
    ("brand text on the page", "ACCENT_PRIMARY", "SURFACE_PAGE", "text", 4.5),
    ("muted text on a raised panel", "TEXT_MUTED", "SURFACE_RAISED", "text", 4.5),
    ("subtle hint text on the page", "TEXT_SUBTLE", "SURFACE_PAGE", "text", 4.5),
    ("subtle hint text on a card", "TEXT_SUBTLE", "SURFACE_CARD", "text", 4.5),
    ("subtle hint text on a raised panel", "TEXT_SUBTLE", "SURFACE_RAISED", "text", 4.5),
    ("text on the secondary fill", "TEXT_ON_SECONDARY", "ACCENT_SECONDARY", "text", 4.5),
    ("text on the error fill", "TEXT_ON_ERROR", "STATE_ERROR_GRAPHIC", "text", 4.5),
    ("amber text on a card", "TEXT_AMBER", "SURFACE_CARD", "text", 4.5),
    ("blocked step text on a card", "TEXT_BLOCKED", "SURFACE_CARD", "text", 4.5),
    ("blocked step text on the page", "TEXT_BLOCKED", "SURFACE_PAGE", "text", 4.5),
    ("disabled text on a card", "TEXT_DISABLED", "SURFACE_CARD", "disabled", 3.0),
    ("disabled text on the page", "TEXT_DISABLED", "SURFACE_PAGE", "disabled", 3.0),
    ("disabled primary label", "TEXT_PRIMARY", "ACCENT_PRIMARY_DISABLED", "disabled", 3.0),
    ("success icon on a card", "STATE_SUCCESS_GRAPHIC", "SURFACE_CARD", "graphic", 3.0),
    ("warning icon on a card", "STATE_WARNING_GRAPHIC", "SURFACE_CARD", "graphic", 3.0),
    ("error icon on a card", "STATE_ERROR_GRAPHIC", "SURFACE_CARD", "graphic", 3.0),
    ("brand icon on a card", "ACCENT_PRIMARY", "SURFACE_CARD", "graphic", 3.0),
    ("tertiary icon on a card", "ACCENT_TERTIARY", "SURFACE_CARD", "graphic", 3.0),
    ("control edge on a card", "BORDER_CONTROL", "SURFACE_CARD", "graphic", 3.0),
    ("control edge on the page", "BORDER_CONTROL", "SURFACE_PAGE", "graphic", 3.0),
    ("placeholder text on a field", "TEXT_PLACEHOLDER", "SURFACE_CARD", "text", 4.5),
    ("focus ring on a card", "ACCENT_FOCUS_RING", "SURFACE_CARD", "graphic", 3.0),
)

BADGE_CONTRAST_PAIRS_DARK: tuple[tuple[str, str, str], ...] = (
    ("neutral badge", "BADGE_NEUTRAL_TEXT", "BADGE_NEUTRAL_BG"),
    ("blue badge", "BADGE_BLUE_TEXT", "BADGE_BLUE_BG"),
    ("green badge", "BADGE_GREEN_TEXT", "BADGE_GREEN_BG"),
    ("red badge", "BADGE_RED_TEXT", "BADGE_RED_BG"),
    ("soft red badge", "BADGE_RED_SOFT_TEXT", "BADGE_RED_SOFT_BG"),
    ("grey badge", "BADGE_GREY_TEXT", "BADGE_GREY_BG"),
    ("soft green badge", "BADGE_GREEN_SOFT_TEXT", "BADGE_GREEN_SOFT_BG"),
    ("indigo badge", "BADGE_INDIGO_TEXT", "BADGE_INDIGO_BG"),
    ("orange badge", "BADGE_ORANGE_TEXT", "BADGE_ORANGE_BG"),
    ("violet badge", "BADGE_VIOLET_TEXT", "BADGE_VIOLET_BG"),
    ("amber badge", "BADGE_AMBER_TEXT", "BADGE_AMBER_BG"),
    ("teal badge", "BADGE_TEAL_TEXT", "BADGE_TEAL_BG"),
    ("pink badge", "BADGE_PINK_TEXT", "BADGE_PINK_BG"),
    ("lime badge", "BADGE_LIME_TEXT", "BADGE_LIME_BG"),
    ("sky badge", "BADGE_SKY_TEXT", "BADGE_SKY_BG"),
    ("sand badge", "BADGE_SAND_TEXT", "BADGE_SAND_BG"),
)


def _relative_luminance(hex_color: str) -> float:
    """WCAG 2.1 relative luminance of a #rrggbb colour."""
    h = hex_color.lstrip("#")
    channels = []
    for i in (0, 2, 4):
        c = int(h[i : i + 2], 16) / 255
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(foreground: str, background: str) -> float:
    """WCAG 2.1 contrast ratio between two #rrggbb colours (1.0 - 21.0)."""
    la = _relative_luminance(foreground)
    lb = _relative_luminance(background)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


# The badge roles are part of the contract too: a status label is text on
# a fill, and it has to be readable.
BADGE_CONTRAST_PAIRS: tuple[tuple[str, str, str], ...] = (
    ("neutral badge", BADGE_NEUTRAL_TEXT, BADGE_NEUTRAL_BG),
    ("blue badge", BADGE_BLUE_TEXT, BADGE_BLUE_BG),
    ("green badge", BADGE_GREEN_TEXT, BADGE_GREEN_BG),
    ("red badge", BADGE_RED_TEXT, BADGE_RED_BG),
    ("soft red badge", BADGE_RED_SOFT_TEXT, BADGE_RED_SOFT_BG),
    ("grey badge", BADGE_GREY_TEXT, BADGE_GREY_BG),
    ("soft green badge", BADGE_GREEN_SOFT_TEXT, BADGE_GREEN_SOFT_BG),
    ("indigo badge", BADGE_INDIGO_TEXT, BADGE_INDIGO_BG),
    ("orange badge", BADGE_ORANGE_TEXT, BADGE_ORANGE_BG),
    ("violet badge", BADGE_VIOLET_TEXT, BADGE_VIOLET_BG),
    ("amber badge", BADGE_AMBER_TEXT, BADGE_AMBER_BG),
    ("teal badge", BADGE_TEAL_TEXT, BADGE_TEAL_BG),
    ("pink badge", BADGE_PINK_TEXT, BADGE_PINK_BG),
    ("lime badge", BADGE_LIME_TEXT, BADGE_LIME_BG),
    ("sky badge", BADGE_SKY_TEXT, BADGE_SKY_BG),
    ("sand badge", BADGE_SAND_TEXT, BADGE_SAND_BG),
)


def asset_path(name: str, theme: str | None = None) -> str:
    """Absolute path to a bundled ui/asset (works frozen via sys._MEIPASS).

    If theme is provided and a dark variant exists (name with -dark suffix),
    it will be preferred when theme="dark".
    """
    # If dark theme requested, try dark variant first
    if theme == "dark":
        base, ext = os.path.splitext(name)
        dark_name = f"{base}-dark{ext}"
        # Try dark variant first
        result = _find_asset(dark_name)
        if result:
            return result

    return _find_asset(name)


def _find_asset(name: str) -> str:
    """Find an asset by name."""
    import sys
    from pathlib import Path

    candidates = []
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        candidates.append(Path(meipass) / "ui" / "assets" / name)
        candidates.append(Path(meipass) / "assets" / name)
    candidates.append(Path(__file__).resolve().parent / "assets" / name)
    for path in candidates:
        try:
            if path.exists():
                return path.as_posix()
        except Exception:
            continue
    return ""


def app_icon_path(theme: str | None = None) -> str:
    """Absolute path to the app icon (ui/assets/docent.png).

    The About page keeps this mark. asset_path resolves the bundled
    copy both in dev and frozen (the exe ships --add-data "ui/assets;ui/assets").
    If theme is provided, a dark variant will be used when available.
    """
    return asset_path("docent.png", theme)


def mark_icon_path(theme: str | None = None) -> str:
    """Absolute path to the 16x16.png mark (ui/assets/16x16.png).

    The dashboard status pill's mark and the window icon the Windows
    taskbar draws use this; the About page keeps docent.png
    (app_icon_path). Resolved by asset_path (dev + frozen).
    If theme is provided, a dark variant will be used when available.
    """
    return asset_path("16x16.png", theme)


def _chevron_qss(theme: str | None = None) -> str:
    """Down-arrow rule: Lucide chevron when bundled, CSS triangle fallback."""
    theme = theme or ACTIVE_THEME
    arrow = asset_path("lucide/chevron-down-grey.svg")
    if not arrow:
        arrow = asset_path("chevron-down.png")
    if arrow:
        return f"""QComboBox::down-arrow {{
    image: url({arrow});
    width: 14px;
    height: 14px;
    margin-right: 10px;
}}"""
    return f"""QComboBox::down-arrow {{
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {role("TEXT_MUTED", theme)};
    margin-right: 8px;
}}"""


def header_section_qss(*, flush: bool = False, theme: str | None = None) -> str:
    """Table/tree header section rules — one source of truth.

    A widget-level stylesheet replaces the app-level rules for that
    subtree (Qt does not merge them), so every table that sets its own
    stylesheet has to repeat the header rules. They are repeated from
    here instead of by hand, so the app-level sheet and the local sheets
    cannot drift apart.

    flush=True squares the end caps: the header sits flush inside a card,
    where a rounded cap would notch the unfilled corner.
    """
    theme = theme or ACTIVE_THEME
    radius = "0px" if flush else RADIUS_LG
    return (
        # The header is one continuous band: the area right of the last
        # section (the vertical scrollbar's lane) carries the header's
        # own background, not the page colour.
        f"QHeaderView {{ background: {role('SURFACE_TINT', theme)}; }} "
        f"QHeaderView::section {{ background: {role('SURFACE_TINT', theme)}; "
        f"color: {role('TEXT_MUTED', theme)}; padding: 8px 14px 8px 12px; "
        # One continuous band: a bottom rule only. A right border drew a
        # vertical bar between sections, which reads as a column divider
        # and crept back into the review-config and dataset tables.
        f"border: none; border-bottom: 1px solid {role('BORDER_SUBTLE', theme)}; "
        f"font-size: {FONT_SMALL}px; "
        # No text-transform here: Qt applies it when it *paints* a label
        # but not when it *measures* one, so the painted header was wider
        # than the text Qt elided against and a narrow section lost its
        # first letter ("SUBMITTING AUTHOR" read as "UBMITTING AUTHOR").
        # The kit stores the header labels in the case they are painted
        # in (see AppTable.setHorizontalHeaderLabels), so the metrics and
        # the paint agree - and a translation can choose its own casing.
        "font-weight: 600; } "
        f"QHeaderView::section:hover {{ background: {role('SURFACE_RAISED', theme)}; }} "
        f"QHeaderView::section:pressed {{ background: {role('ACCENT_TINT', theme)}; }} "
        f"QHeaderView::section:first {{ border-top-left-radius: {radius}; }} "
        f"QHeaderView::section:last {{ border-top-right-radius: {radius}; }} "
    )


def selection_qss(scope: str = "", *, hover: bool = True, theme: str | None = None) -> str:
    """Row selection and hover for an item view — one source of truth.

    Every table and tree wears the same face: a quiet full-row tint on
    selection (never a per-cell box) and an even quieter hover. Views
    that set a local stylesheet have to repeat the rules, so they take
    them from here instead of writing their own — the dashboard queue,
    the metadata tree and the extensions table had drifted apart.

    scope is the view selector ("QTableWidget", "QTreeView"). Leave it
    empty when embedding in a rule that already carries the selector.

    hover=False is for a view whose rows are a *form* rather than a list
    of documents (the Review configuration field tree): a pointer passing
    over a row must not paint a band that reads as "this is the one" while
    the Response pane still targets a different rule (dv-ud0).
    """
    theme = theme or ACTIVE_THEME
    # No space between the scope and ``::item``: a descendant selector
    # (``QTreeView ::item``) matches a *child widget*, so the rules were
    # silently dead and views fell back to the native highlight colour.
    prefix = f"{scope}::item" if scope else "::item"
    # ACCENT_SECONDARY is the palette's selection fill (it already backs
    # menus and combo popups); SURFACE_TINT is the header band, so using it
    # here made a selected row indistinguishable from its own header.
    # The selected rules repeat instead of sharing a `tint` variable: the
    # catalogue guard reads every prose-shaped literal in this module, and
    # a bare ":selected { " fragment reads as prose.
    return (
        (f"{prefix}:hover {{ background: {role('SURFACE_SUBTLE', theme)}; }} " if hover else "")
        # Keep the selected face when the view loses focus: the inactive
        # palette would otherwise drop the row back to an unstyled white.
        + f"{prefix}:selected {{ background: {role('ACCENT_SECONDARY', theme)}; "
        f"color: {role('TEXT_PRIMARY', theme)}; }} "
        f"{prefix}:selected:!active {{ background: {role('ACCENT_SECONDARY', theme)}; "
        f"color: {role('TEXT_PRIMARY', theme)}; }} "
    )


def scrollbar_lane_qss(scope: str = "", theme: str | None = None) -> str:
    """Transparent scrollbar lanes for a widget scope.

    A filled lane paints the page colour over the card's rounded
    bottom-right corner, so the card border ends in a white notch. The
    lanes stay transparent and the card's own surface shows through;
    thumbs and grooves keep coming from the global theme.

    ``theme`` is accepted for signature parity with the other generators;
    a transparent rule carries no colour to resolve.
    """
    prefix = f"{scope} " if scope else ""
    return (
        f"{prefix}QScrollBar:vertical {{ background: transparent; }} "
        f"{prefix}QScrollBar:horizontal {{ background: transparent; }} "
    )


# The button kinds and the object name each one paints under. The kit
# (ui/widgets.py) reads the same map, so a button's identity and its
# rules come from one place.
BUTTON_OBJECTS = {
    "primary": "PrimaryButton",
    "secondary": "SecondaryButton",
    "ghost": "GhostButton",
    "chip": "FilterChip",
    "cell": "CellButton",
    "link": "LinkButton",
    "nav-active": "NavActive",
    "nav": "NavItem",
    "nav-dataset": "NavDataset",
}


def button_qss(
    kind: str = "secondary",
    *,
    selector: str | None = None,
    scope: str = "",
    theme: str | None = None,
) -> str:
    """Build the QSS for one button kind.

    The app sheet and the local sheets come from here, so the two cannot
    drift.

    ``selector=None`` (the default) gives the app-level object-name rule
    (``QPushButton#PrimaryButton``). Pass ``selector="QPushButton"`` for a
    widget-level sheet: Qt replaces the application sheet for a subtree,
    so a button inside a styled panel needs its own copy - and that copy
    must be the same rules, not a second hand-written version.

    ``scope`` prefixes the selector (``scope="#TopNav"`` gives
    ``#TopNav QPushButton#NavItem``).

    ``theme`` picks the role table the colours resolve through, so a
    widget sheet built for the dark theme paints dark faces.
    """
    theme = theme or ACTIVE_THEME
    prefix = f"{scope} " if scope else ""
    if selector:
        sel = f"{prefix}{selector}"
    else:
        sel = f"{prefix}QPushButton#{BUTTON_OBJECTS.get(kind, 'SecondaryButton')}"

    if kind == "primary":
        return (
            f"{sel} {{ background: {role('ACCENT_PRIMARY', theme)}; color: {role('TEXT_ON_ACCENT', theme)}; border: none; "
            f"border-radius: {RADIUS_LG}; padding: 8px 16px; font-weight: 600; "
            f"font-size: {FONT_SMALL}px; }} "
            f'{sel}[focusVisible="true"] {{ background: {role("ACCENT_PRIMARY_FOCUS", theme)}; }} '
            f"{sel}:hover {{ background: {role('ACCENT_PRIMARY_HOVER', theme)}; }} "
            f"{sel}:pressed {{ background: {role('ACCENT_PRIMARY_PRESSED', theme)}; }} "
            # Disabled: a muted blue face with the dark text colour. White
            # on the old face was 2.35:1 - the label was unreadable.
            f"{sel}:disabled {{ background: {role('ACCENT_PRIMARY_DISABLED', theme)}; color: {role('TEXT_PRIMARY', theme)}; }}"
        )
    if kind == "secondary":
        return (
            f"{sel} {{ background: {role('SURFACE_CARD', theme)}; color: {role('TEXT_PRIMARY', theme)}; "
            f"border: 1px solid {role('BORDER_CONTROL', theme)}; border-radius: {RADIUS_LG}; "
            f"padding: 7px 14px; font-weight: 600; font-size: {FONT_SMALL}px; }} "
            f'{sel}[focusVisible="true"] {{ background: {role("ACCENT_FOCUS_TINT", theme)}; }} '
            f"{sel}:hover {{ background: {role('SURFACE_RAISED', theme)}; "
            f"border: 1px solid {role('ACCENT_PRIMARY', theme)}; }} "
            f"{sel}:pressed {{ background: {role('ACCENT_SECONDARY', theme)}; }} "
            f"{sel}:disabled {{ background: {role('SURFACE_SUBTLE', theme)}; "
            f"color: {role('TEXT_DISABLED', theme)}; }}"
        )
    if kind == "ghost":
        return (
            f"{sel} {{ background: transparent; color: {role('TEXT_PRIMARY', theme)}; "
            f"border: none; border-radius: {RADIUS_LG}; padding: 6px 10px; "
            f"font-size: {FONT_SMALL}px; font-weight: 500; }} "
            f'{sel}[focusVisible="true"] {{ background: {role("ACCENT_FOCUS_TINT", theme)}; '
            f"color: {role('TEXT_PRIMARY', theme)}; }} "
            f"{sel}:hover {{ background: {role('SURFACE_TINT', theme)}; color: {role('TEXT_PRIMARY', theme)}; }} "
            f"{sel}:disabled {{ color: {role('TEXT_DISABLED', theme)}; }}"
        )
    if kind == "chip":
        return (
            f"{sel} {{ background: {role('SURFACE_CARD', theme)}; "
            f"border: 1px solid {role('BORDER_CONTROL', theme)}; border-radius: {RADIUS_LG}; "
            f"padding: 6px 10px; font-size: {FONT_SMALL}px; font-weight: 600; "
            f"color: {role('TEXT_MUTED', theme)}; }} "
            f'{sel}[focusVisible="true"] {{ background: {role("ACCENT_FOCUS_TINT", theme)}; '
            f"color: {role('TEXT_PRIMARY', theme)}; }} "
            f"{sel}:hover {{ background: {role('SURFACE_RAISED', theme)}; "
            f"border: 1px solid {role('ACCENT_PRIMARY', theme)}; }}"
        )
    if kind == "cell":
        # The compact face for a table action cell: the standard action
        # padding (7px 14px) made "Reinstall"+"Uninstall" need 294px
        # against a 240px column, clipping both buttons. Same button
        # system, cell-sized padding.
        return (
            f"{sel} {{ background: {role('SURFACE_CARD', theme)}; color: {role('TEXT_PRIMARY', theme)}; "
            f"border: 1px solid {role('BORDER_CONTROL', theme)}; border-radius: 6px; "
            f"padding: 0 8px; font-weight: 600; font-size: {FONT_SMALL}px; }} "
            f'{sel}[focusVisible="true"] {{ background: {role("ACCENT_FOCUS_TINT", theme)}; }} '
            f"{sel}:hover {{ background: {role('SURFACE_RAISED', theme)}; "
            f"border: 1px solid {role('ACCENT_PRIMARY', theme)}; }} "
            f"{sel}:pressed {{ background: {role('ACCENT_SECONDARY', theme)}; }} "
            f"{sel}:disabled {{ background: {role('SURFACE_DISABLED', theme)}; color: {role('TEXT_DISABLED', theme)}; "
            f"border: 1px solid {role('BORDER_DISABLED', theme)}; }}"
        )
    if kind == "link":
        # A left-aligned brand row that navigates to a section. The
        # kit's button kinds could not express it: it is a text link
        # that happens to be a button.
        return (
            f"{sel} {{ text-align: left; padding: 7px 8px; "
            f"font-size: {FONT_SMALL}px; color: {role('ACCENT_PRIMARY', theme)}; "
            f"background: transparent; border: none; border-radius: {RADIUS_LG}; }} "
            f'{sel}[focusVisible="true"] {{ background: {role("ACCENT_FOCUS_TINT", theme)}; '
            f"color: {role('TEXT_PRIMARY', theme)}; }} "
            f"{sel}:hover {{ background: {role('SURFACE_TINT', theme)}; }} "
            f"{sel}:disabled {{ color: {role('TEXT_DISABLED', theme)}; }}"
        )
    if kind == "nav-active":
        return (
            f"{sel} {{ background: {role('ACCENT_SECONDARY', theme)}; color: {role('TEXT_ON_SECONDARY', theme)}; "
            f"border: none; border-radius: {RADIUS_LG}; padding: 6px 12px; "
            f"font-weight: 600; font-size: {FONT_SMALL}px; }} "
            f'{sel}[focusVisible="true"] {{ background: {role("ACCENT_FOCUS_TINT", theme)}; '
            f"color: {role('TEXT_PRIMARY', theme)}; }}"
        )
    if kind == "nav-dataset":
        # A dataset chip in the nav: the nav surface, so the rail band can
        # match it (2026-11-24).
        return (
            f"{sel} {{ background: {role('SURFACE_CARD', theme)}; color: {role('TEXT_PRIMARY', theme)}; "
            f"border: none; border-radius: {RADIUS_LG}; padding: 6px 12px; "
            f"font-weight: 600; font-size: {FONT_SMALL}px; }} "
            f'{sel}[focusVisible="true"] {{ background: {role("ACCENT_FOCUS_TINT", theme)}; }} '
            f"{sel}:hover {{ background: {role('SURFACE_RAISED', theme)}; }}"
        )
    # nav
    return (
        f"{sel} {{ background: transparent; color: {role('TEXT_MUTED', theme)}; "
        f"border: none; border-radius: {RADIUS_LG}; padding: 6px 12px; "
        f"font-weight: 600; font-size: {FONT_SMALL}px; }} "
        f'{sel}[focusVisible="true"] {{ background: {role("ACCENT_FOCUS_TINT", theme)}; '
        f"color: {role('TEXT_PRIMARY', theme)}; }} "
        f"{sel}:hover {{ background: {role('SURFACE_RAISED', theme)}; color: {role('TEXT_PRIMARY', theme)}; }}"
    )


def page_background_qss(*names: str, theme: str | None = None) -> str:
    """Build the page background rule for a view root.

    Every view sits on the page colour. A view sets it on its own root
    object name, so a widget-level sheet cannot leak the page colour
    into a nested card. The scroll areas come with it: a scroll area
    paints its own viewport, and without the rule the area shows the
    parent's colour around a white canvas.
    """
    theme = theme or ACTIVE_THEME
    page = role("SURFACE_PAGE", theme)
    parts = []
    if names:
        selectors = ", ".join(f"QWidget#{name}" for name in names)
        parts.append(f"{selectors} {{ background: {page}; border: none; }}")
    parts.append(f"QScrollArea {{ background: {page}; border: none; }}")
    return " ".join(parts)


def transparent_qss(selector: str = "QWidget", theme: str | None = None) -> str:
    """Build the transparent rule for one selector.

    A bare label that carries a pixmap (an icon) must not paint a face
    of its own, or it shows as a chip inside the row it sits in.

    ``theme`` is accepted for signature parity with the other generators;
    a transparent rule carries no colour to resolve.
    """
    return f"{selector} {{ background: transparent; border: none; }}"


def transparent_surface_qss(*names: str, theme: str | None = None) -> str:
    """Build the transparent rule for a wrapper that must not paint.

    A wrapper inside a card inherits the card's background when it does
    not paint one of its own, which shows as a seam.

    ``theme`` is accepted for signature parity with the other generators;
    a transparent rule carries no colour to resolve.
    """
    if not names:
        return ""
    selectors = ", ".join(f"QWidget#{name}" for name in names)
    return f"{selectors} {{ background: transparent; border: none; }}"


def surface_frame_qss(
    background: str,
    border: str,
    *,
    radius: str = RADIUS_LG,
    selector: str = "QFrame",
    border_style: str = "solid",
    theme: str | None = None,
) -> str:
    """Build a plain surface frame (a card face, a check row).

    The radius is the app-wide RADIUS_LG unless a caller has a reason
    to pass another one. ``border_style`` is "solid" everywhere except
    the empty-state card, whose dashed edge is the cue that there is
    nothing here yet.

    The fill and edge arrive as arguments, so the caller decides which
    role they came from; ``theme`` is accepted so a call site can name
    the theme it resolved them against and keep one call shape app-wide.
    A fill or edge may be a role name, which is resolved here - that is
    what lets a live switch rebuild the sheet (dv-314).
    """
    background = colour(background, theme)
    border = colour(border, theme)
    return (
        f"{selector} {{ background: {background}; "
        f"border: 1px {border_style} {border}; border-radius: {radius}; }}"
    )


def band_qss(
    background: str,
    border: str,
    *,
    radius: str = RADIUS_LG,
    selector: str = "QFrame",
    edge: str = "bottom",
    theme: str | None = None,
) -> str:
    """Build a tinted band with one edge (a card's header bar or footer).

    ``edge="bottom"`` is a header bar: it sits flush on the card's top
    edge, so it keeps the top corners and carries its border along the
    bottom. ``edge="top"`` is a flush footer: it keeps the bottom
    corners and carries its border along the top.

    The fill and edge arrive as arguments; ``theme`` is accepted so every
    generator shares one call shape. Either may be a role name, resolved
    here so a live switch can rebuild the band (dv-314).
    """
    background = colour(background, theme)
    border = colour(border, theme)
    if edge == "top":
        return (
            f"{selector} {{ background: {background}; "
            f"border-top: 1px solid {border}; "
            f"border-bottom-left-radius: {radius}; "
            f"border-bottom-right-radius: {radius}; }}"
        )
    return (
        f"{selector} {{ background: {background}; "
        f"border-bottom: 1px solid {border}; "
        f"border-top-left-radius: {radius}; border-top-right-radius: {radius}; }}"
    )


def rule_qss(selector: str, background: str, *, theme: str | None = None) -> str:
    """Build a one-colour rule with no border (a divider or a separator).

    A hairline is a background and nothing else, but it still has to
    follow a theme switch, so it takes a role name like the other
    generators (dv-314).
    """
    return f"{selector} {{ background: {colour(background, theme)}; border: none; }}"


def caption_button_qss(kind: str, *, theme: str | None = None) -> str:
    """Build a frameless window-caption button's face (window chrome).

    A caption control keeps the square Windows caption face and the red
    close hover, which the kit's button kinds cannot express. Built from
    the role table so a live theme switch repaints it (dv-314).
    """
    theme = theme or ACTIVE_THEME
    base = (
        f"QPushButton {{ background: transparent; color: {role('TEXT_PRIMARY', theme)}; "
        "border: none; border-radius: 0px; }"
        f'QPushButton[focusVisible="true"] {{ background: {role("ACCENT_FOCUS_TINT", theme)}; }}'
    )
    if kind == "close":
        return base + (
            f'QPushButton:hover, QPushButton[hovered="true"] {{ '
            f"background: {role('STATE_ERROR_GRAPHIC', theme)}; "
            f"color: {role('TEXT_ON_ACCENT', theme)}; }}"
            f"QPushButton:pressed {{ background: {role('STATE_ERROR_BG', theme)}; "
            f"color: {role('TEXT_ON_ACCENT', theme)}; }}"
        )
    return base + (
        f'QPushButton:hover, QPushButton[hovered="true"] {{ '
        f"background: {role('SURFACE_RAISED', theme)}; }}"
        f"QPushButton:pressed {{ background: {role('ACCENT_SECONDARY', theme)}; }}"
    )


def status_strip_qss(
    background: str,
    border: str,
    text_color: str,
    *,
    font_size: int = FONT_SMALL,
    padding: str = "6px 10px",
    selector: str = "QLabel",
    weight: int | None = None,
    theme: str | None = None,
) -> str:
    """Build a one-line status strip: a message on a card face.

    The strip carries its own face (background, edge, padding) and its
    own text colour, because a widget-level sheet replaces the app
    sheet for that widget - the label's type token would not reach it.
    The three colours arrive as arguments; ``theme`` is accepted so every
    generator shares one call shape.
    """
    weight_rule = f" font-weight: {int(weight)};" if weight else ""
    return (
        f"{selector} {{ background: {background}; color: {text_color}; "
        f"border: 1px solid {border}; border-radius: {RADIUS_LG}; "
        f"padding: {padding}; font-size: {font_size}px;{weight_rule} }}"
    )


def workflow_step_qss(
    state: str = "todo", *, active: bool = False, theme: str | None = None
) -> str:
    """Build the face of one step in the dataset step rail.

    The rail is guidance, not a gate: every step is clickable in every
    state, so the state shows in the colour and the weight, never in
    whether the step can be pressed.

    ``active=True`` is the section rail's "current view" face (dv-gfx.4):
    the step on screen carries a shaded block, not only coloured text.

    ``state="nav"`` is the dataset page's section tab face (dv-3d0.2):
    fixed 36px height, left-aligned, no expanding, hairline separators.
    """
    theme = theme or ACTIVE_THEME
    hover = f"QPushButton#WorkflowStep:hover {{ background: {role('SURFACE_TINT', theme)}; border-radius: 8px; }}"
    if state == "nav":
        # Tab face: 36px fixed height, padding for text, no border by default.
        # The active face keeps the SAME box metrics AND the same font
        # weight as the resting face, so clicking a link never changes its
        # size or position (2026-11-24). The current view is carried by the
        # tint and the accent colour alone.
        if active:
            return (
                f"QPushButton#WorkflowStep {{ color: {role('ACCENT_PRIMARY', theme)}; font-size: {FONT_SMALL}px; "
                f"font-weight: 500; background: {role('ACCENT_TINT', theme)}; "
                f"border: none; border-radius: {RADIUS_MD}; "
                f"padding: 0 12px; min-width: 0; height: 32px; }} "
                f"QPushButton#WorkflowStep:hover {{ background: {role('ACCENT_TINT', theme)}; }}"
            )
        return (
            f"QPushButton#WorkflowStep {{ color: {role('TEXT_MUTED', theme)}; font-size: {FONT_SMALL}px; "
            f"font-weight: 500; background: transparent; border: none; "
            f"padding: 0 12px; min-width: 0; height: 32px; }} {hover}"
        )
    if active:
        return (
            f"QPushButton#WorkflowStep {{ color: {role('ACCENT_PRIMARY', theme)}; font-size: {FONT_SMALL}px; "
            f"font-weight: 700; background: {role('ACCENT_TINT', theme)}; "
            f"border: 1px solid {role('ACCENT_FOCUS_TINT', theme)}; border-radius: {RADIUS_MD}; "
            f"padding: 2px 8px; height: 30px; }} "
            f"QPushButton#WorkflowStep:hover {{ background: {role('ACCENT_TINT', theme)}; "
            f"border: 1px solid {role('ACCENT_PRIMARY', theme)}; }}"
        )
    if state == "done":
        return (
            f"QPushButton#WorkflowStep {{ color: {role('TEXT_SUCCESS', theme)}; font-size: {FONT_SMALL}px; "
            f"font-weight: 600; background: transparent; border: none; "
            f"padding: 3px 6px; }} {hover}"
        )
    if state == "current":
        return (
            f"QPushButton#WorkflowStep {{ color: {role('ACCENT_PRIMARY', theme)}; font-size: {FONT_SMALL}px; "
            f"font-weight: 700; background: {role('ACCENT_TINT', theme)}; "
            f"border: 1px solid {role('ACCENT_FOCUS_TINT', theme)}; border-radius: 8px; "
            f"padding: 2px 8px; height: 30px; }} "
            f"QPushButton#WorkflowStep:hover {{ background: {role('SURFACE_RAISED', theme)}; "
            f"border: 1px solid {role('ACCENT_PRIMARY', theme)}; }}"
        )
    if state == "blocked":
        # A blocked step is guidance, not a disabled control: it stays
        # clickable and stays legible (the lock mark carries the state).
        return (
            f"QPushButton#WorkflowStep {{ color: {role('TEXT_BLOCKED', theme)}; font-size: {FONT_SMALL}px; "
            f"background: transparent; border: none; padding: 3px 6px; }} {hover}"
        )
    return (
        f"QPushButton#WorkflowStep {{ color: {role('TEXT_MUTED', theme)}; font-size: {FONT_SMALL}px; "
        f"background: transparent; border: none; padding: 2px 6px; height: 30px; }} {hover}"
    )


def workflow_rail_qss(theme: str | None = None) -> str:
    """Build the section rail's band: nav-bar surface, one bottom rule.

    The rail sits directly under the app nav bar and reads as part of that
    stack: the same surface, a single 1px bottom hairline, and no other
    border (2026-11-24).
    """
    theme = theme or ACTIVE_THEME
    return (
        f"QWidget#WorkflowRail {{ background: {role('SURFACE_CARD', theme)}; "
        f"border: none; border-bottom: 1px solid {role('BORDER_SUBTLE', theme)}; }}"
    )


def input_qss(
    selector: str,
    *,
    font_size: int = FONT_SMALL,
    family: str | None = None,
    theme: str | None = None,
) -> str:
    """Build the standard text input sheet for one selector.

    A widget that carries its own stylesheet loses the application-level
    input rules, so the sheet repeats them - from here, so the app-level
    sheet and the local sheet cannot drift.

    ``family`` overrides the font stack (a raw payload view uses the
    mono stack).
    """
    theme = theme or ACTIVE_THEME
    stack = f"font-family: {family}; " if family else ""
    return (
        f"{selector} {{ background: {role('SURFACE_CARD', theme)}; "
        f"border: 1px solid {role('BORDER_CONTROL', theme)}; border-radius: {RADIUS_LG}; "
        f"padding: 7px 10px; font-size: {font_size}px; {stack}"
        f"selection-background-color: {role('ACCENT_TINT', theme)}; }} "
        f"{selector}:focus {{ border: 1px solid {role('ACCENT_FOCUS_RING', theme)}; }} "
        # The placeholder is text: it carries its own colour instead of
        # inheriting the platform's (a pale grey that fails 4.5:1).
        f"{selector}::placeholder-text {{ color: {role('TEXT_PLACEHOLDER', theme)}; }}"
    )


def badge_qss(
    background: str,
    foreground: str,
    border: str,
    *,
    font_size: int = FONT_SMALL,
    padding: str = "0 6px",
    theme: str | None = None,
) -> str:
    """Build a badge face from role colours.

    A badge is text on a fill: the fill, the text and the edge are three
    roles, and the badge's contract (a rounded, bordered, bold label)
    is the same everywhere. The three colours arrive as arguments;
    ``theme`` is accepted so every generator shares one call shape. Each
    may be a role name, resolved here so a live switch can rebuild the
    badge (dv-314).
    """
    return (
        f"QLabel {{ background: {colour(background, theme)}; color: {colour(foreground, theme)}; "
        f"border: 1px solid {colour(border, theme)}; border-radius: {RADIUS_LG}; "
        f"font-size: {font_size}px; font-weight: 700; padding: {padding}; }}"
    )


def global_qss(theme: str | None = None) -> str:
    """Return the app's global Qt style sheet, derived from the active palette."""
    theme = theme or ACTIVE_THEME
    return f"""
/* ===== Base ===== */
QWidget {{
    font-family: {FONT_FAMILY};
    color: {role("TEXT_PRIMARY", theme)};
}}
QMainWindow, QStackedWidget, QScrollArea {{
    background: {role("SURFACE_PAGE", theme)};
}}

/* ===== Top nav / header bar ===== */
#TopNav {{
    background: {role("SURFACE_CARD", theme)};
    border-bottom: 1px solid {role("BORDER_SUBTLE", theme)};
}}
{button_qss("nav-active", scope="#TopNav", theme=theme)}
{button_qss("nav", scope="#TopNav", theme=theme)}
/* Keyboard focus tint (focus-visible) — a colour change, never an outline.
   Sits before :hover/:checked so hover feedback wins when both apply. */
#TopNav QPushButton#NavActive[focusVisible="true"],
#TopNav QPushButton#NavItem[focusVisible="true"] {{
    background: {role("ACCENT_FOCUS_TINT", theme)};
    color: {role("TEXT_PRIMARY", theme)};
}}
#TopNav QPushButton#NavItem:hover {{
    background: {role("SURFACE_RAISED", theme)};
    color: {role("TEXT_PRIMARY", theme)};
}}
/* Toggle nav buttons (Settings/Log/About) are checkable: a checked button
   reads exactly like the active location tab so "pane open" is unmistakable
   and identical for Log and Settings. */
#TopNav QPushButton#NavItem:checked {{
    background: {role("ACCENT_SECONDARY", theme)};
    color: {role("TEXT_ON_SECONDARY", theme)};
    font-weight: 600;
}}
#TopNav QLabel#Brand {{
    font-family: {HEADING_FAMILY};
    font-size: {FONT_TITLE}px;
    font-weight: 700;
    color: {role("ACCENT_PRIMARY", theme)};
}}

/* ===== Cards ===== */
#Card {{
    background: {role("SURFACE_CARD", theme)};
    border: 1px solid {role("BORDER_SUBTLE", theme)};
    border-radius: {RADIUS_LG};
}}
#MetricCard {{
    background: {role("SURFACE_CARD", theme)};
    border: 1px solid {role("BORDER_SUBTLE", theme)};
    border-radius: {RADIUS_LG};
}}
/* The metric cards filter the queue: hover signals the affordance
   (dv-1k4). Keyboard focus already tints via [focusVisible="true"]. */
#MetricCard:hover {{
    background: {role("SURFACE_SUBTLE", theme)};
    border: 1px solid {role("ACCENT_PRIMARY", theme)};
}}

#SectionHeader {{
    background: {role("SURFACE_CARD", theme)};
    border-bottom: 1px solid {role("SURFACE_SUBTLE", theme)};
}}

/* ===== Buttons: one system (QPushButton), generated by theme.button_qss() ===== */
{button_qss("primary")}
{button_qss("secondary")}
{button_qss("ghost")}
{button_qss("chip")}
{button_qss("cell")}
{button_qss("link")}

/* ===== Dialog buttons (QDialogButtonBox) ===== */
/* QDialogButtonBox builds its own buttons, so they never carry a kit
   object name and used to fall back to the platform face: no border, no
   focus ring, a different type size. The rule below gives every dialog
   button the app's secondary face; an affirmative button that opts into
   the #PrimaryButton id (see ui.dialogs) picks up the brand fill. */
QDialogButtonBox QPushButton {{
    background: {role("SURFACE_CARD", theme)};
    color: {role("TEXT_PRIMARY", theme)};
    border: 1px solid {role("BORDER_CONTROL", theme)};
    border-radius: {RADIUS_LG};
    padding: 7px 16px;
    font-weight: 600;
    font-size: {FONT_SMALL}px;
    min-height: 18px;
}}
QDialogButtonBox QPushButton:hover {{
    background: {role("SURFACE_RAISED", theme)};
    border-color: {role("ACCENT_PRIMARY", theme)};
}}
QDialogButtonBox QPushButton:focus {{
    outline: 2px solid {role("ACCENT_FOCUS_RING", theme)};
    outline-offset: 2px;
}}
{button_qss("primary", scope="QDialogButtonBox", theme=theme)}

/* ===== Inputs ===== */
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox {{
    background: {role("SURFACE_CARD", theme)};
    border: 1px solid {role("BORDER_CONTROL", theme)};
    border-radius: {RADIUS_LG};
    padding: 7px 10px;
    selection-background-color: {role("ACCENT_TINT", theme)};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{
    border: 1px solid {role("ACCENT_FOCUS_RING", theme)};
}}
/* The placeholder is text, so it carries its own colour: the platform
   default is a pale grey that does not clear 4.5:1 on a white field. */
QLineEdit::placeholder-text, QTextEdit::placeholder-text,
QPlainTextEdit::placeholder-text {{
    color: {role("TEXT_PLACEHOLDER", theme)};
}}
/* Keyboard focus (Tab/arrow navigation) paints a colour tint — never an
   outline (2026-10-02 — replaces both the outline batch and its removal).
   focusVisible is set only when focus arrives from the keyboard
   (theme._install_interaction_tracking); mouse clicks set no tint. Focused inputs
   still signal focus via the border-colour change above. */
QPushButton[focusVisible="true"] {{
    background: {role("ACCENT_FOCUS_TINT", theme)};
    color: {role("TEXT_PRIMARY", theme)};
}}
QTabBar[focusVisible="true"]::tab:selected {{
    background: {role("ACCENT_FOCUS_TINT", theme)};
    color: {role("TEXT_PRIMARY", theme)};
}}
/* Keyboard focus ring — 2px offset, high-contrast stroke.
   Applied to every focusable control so keyboard users never lose their place. */
QPushButton[focusVisible="true"],
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus,
QHeaderView[focusVisible="true"],
QTreeView[focusVisible="true"],
QTreeWidget[focusVisible="true"],
QTableWidget[focusVisible="true"],
QTabBar[focusVisible="true"]::tab:selected,
QToolButton[focusVisible="true"],
QAbstractScrollArea[focusVisible="true"],
QWidget[focusVisible="true"] {{
    outline: 2px solid {role("ACCENT_FOCUS_RING", theme)};
    outline-offset: 2px;
}}

QLineEdit#SearchField {{
    padding-left: 32px;
    background: {role("SURFACE_CARD", theme)};
    border: 1px solid {role("BORDER_CONTROL", theme)};
    border-radius: {RADIUS_LG};
}}
QLineEdit#SearchField:focus {{
    border: 1px solid {role("ACCENT_FOCUS_RING", theme)};
}}

/* ComboBox drop-down: fully owner-drawn button so no native edge, groove
   or separator line can render — just the chevron glyph. */
QComboBox {{
    padding-right: 32px;
}}
QComboBox::drop-down {{
    border: none;
    border-left: none;
    border-width: 0px;
    background: transparent;
    width: 30px;
    margin: 0px;
    padding: 0px;
    subcontrol-origin: padding;
    subcontrol-position: top right;
}}
{_chevron_qss(theme=theme)}
/* Popup floats just below the button (the kit offsets it ~4px): fully
   rounded on every corner, so opening it never changes the field's shape.
   Item metrics are pinned (not font-implied) so every menu spaces choices
   identically no matter which card hosts the combo. */
QComboBox QAbstractItemView {{
    background: {role("SURFACE_CARD", theme)};
    border: 1px solid {role("BORDER_SUBTLE", theme)};
    border-top-left-radius: {RADIUS_LG};
    border-top-right-radius: {RADIUS_LG};
    border-bottom-left-radius: {RADIUS_LG};
    border-bottom-right-radius: {RADIUS_LG};
    selection-background-color: {role("ACCENT_SECONDARY", theme)};
    selection-color: {role("TEXT_PRIMARY", theme)};
    outline: 0;
}}
QComboBox QAbstractItemView::item {{
    border: none;
    min-height: 22px;
    padding: 6px 10px;
}}
QComboBox QAbstractItemView::item:selected {{
    background: {role("ACCENT_SECONDARY", theme)};
    color: {role("TEXT_PRIMARY", theme)};
    border: none;
}}
/* The field keeps its rounded corners while open: the popup floats below
   it (see the kit's showPopup gap), so there is no junction to square off. */

/* ===== Table ===== */
/* Item views mark the current cell/row with the secondary fill (the
   palette's selection role). A visible focus ring (added above) carries
   focus for keyboard users. */
QTableWidget {{
    background: {role("SURFACE_CARD", theme)};
    border: none;
    gridline-color: {role("BORDER_SUBTLE", theme)};
    selection-background-color: {role("ACCENT_SECONDARY", theme)};
    alternate-background-color: {role("SURFACE_SUBTLE", theme)};
}}
QTableWidget::item {{
    padding: 10px 12px;
    border-bottom: 1px solid {role("SURFACE_SUBTLE", theme)};
}}
{header_section_qss(theme=theme)}
{selection_qss("QTableWidget", theme=theme)}

/* ===== Tooltips ===== */
/* Explicit light face for EVERY tooltip app-wide: without this, the global
   QWidget text color leaks into system-drawn (dark) tooltip backgrounds and
   renders black unreadable boxes (seen on dataset log + metadata table). */
QToolTip {{
    background: {role("SURFACE_CARD", theme)};
    color: {role("TEXT_PRIMARY", theme)};
    border: 1px solid {role("BORDER_SUBTLE", theme)};
    border-radius: {RADIUS_LG};
    padding: 6px 8px;
    font-size: {FONT_SMALL}px;
}}

/* ===== Labels ===== */
/* The type scale (FONT_* above) is the only place a size is written. */
QLabel#DisplayLG {{
    font-family: {HEADING_FAMILY};
    font-size: {FONT_HEADLINE}px;
    font-weight: 700;
    color: {role("TEXT_PRIMARY", theme)};
}}
QLabel#HeadlineLG {{
    font-family: {HEADING_FAMILY};
    font-size: {FONT_HEADLINE}px;
    font-weight: 600;
    color: {role("TEXT_PRIMARY", theme)};
    letter-spacing: -0.2px;
}}
QLabel#HeadlineMD {{
    font-family: {HEADING_FAMILY};
    font-size: {FONT_TITLE}px;
    font-weight: 600;
    color: {role("TEXT_PRIMARY", theme)};
}}
QLabel#BodyMD {{
    font-size: {FONT_BODY}px;
    color: {role("TEXT_MUTED", theme)};
}}
QLabel#LabelMD {{
    font-size: {FONT_SMALL}px;
    font-weight: 600;
    color: {role("TEXT_MUTED", theme)};
    letter-spacing: 0.5px;
}}
QLabel#CardTitle {{
    font-family: {HEADING_FAMILY};
    font-size: {FONT_TITLE}px;
    font-weight: 600;
    color: {role("TEXT_PRIMARY", theme)};
}}
/* The separator between two steps of the dataset step rail. */
QLabel#WorkflowSeparator {{
    font-size: {FONT_BODY}px;
    color: {role("BORDER_SUBTLE", theme)};
}}
QLabel#CaptionSM {{
    font-size: {FONT_BODY}px;
    color: {role("TEXT_MUTED", theme)};
}}
/* A field or section label on the primary text colour (11px, semibold,
   tracked) - "Decision State", "Internal Notes". */
QLabel#LabelStrongSM {{
    font-size: {FONT_SMALL}px;
    font-weight: 600;
    color: {role("TEXT_PRIMARY", theme)};
    letter-spacing: 0.5px;
}}
/* Brand-coloured text: a link-like line of copy. */
QLabel#AccentSM {{
    font-size: {FONT_SMALL}px;
    color: {role("ACCENT_PRIMARY", theme)};
}}
/* Success-coloured text: a result line ("All checks passed"). */
QLabel#SuccessSM {{
    font-size: {FONT_SMALL}px;
    color: {role("TEXT_SUCCESS", theme)};
}}
/* Warning-coloured text: a caution line ("Large dataset"). */
QLabel#WarningSM {{
    font-size: {FONT_SMALL}px;
    color: {role("TEXT_WARNING", theme)};
}}
/* Danger-coloured text: a validation error line. */
QLabel#DangerSM {{
    font-size: {FONT_SMALL}px;
    color: {role("STATE_ERROR_GRAPHIC", theme)};
}}
/* A result line at body size: a confirmation reads as unmissable at a
   glance (success pair already in the contrast contract). */
QLabel#SuccessMD {{
    font-size: {FONT_BODY}px;
    font-weight: 600;
    color: {role("TEXT_SUCCESS", theme)};
}}
/* An error line at body size, distinct from success at the same glance. */
QLabel#DangerMD {{
    font-size: {FONT_BODY}px;
    font-weight: 600;
    color: {role("STATE_ERROR_GRAPHIC", theme)};
}}
/* The dashboard counter: the data it is — body size, primary ink (the
   CaptionSM it wore read as chrome). */
QLabel#ValueMD {{
    font-size: {FONT_BODY}px;
    font-weight: 600;
    color: {role("TEXT_PRIMARY", theme)};
}}
QLabel#BodySM {{
    font-size: {FONT_BODY}px;
    color: {role("TEXT_MUTED", theme)};
}}
/* A loaded value (a signed-in user's checked identity): the same size
   as BodySM but on the primary text colour, so it reads as the data it
   is — an unfetched "Not checked yet" keeps BodySM (muted), a checked
   value wears ValueSM. */
QLabel#ValueSM {{
    font-size: {FONT_SMALL}px;
    color: {role("TEXT_PRIMARY", theme)};
}}
/* A field hint: body size and muted ink. TEXT_ON_TINT was intentionally
   de-emphasised and read as smaller than its size, so the hint now uses
   the same muted ink as body copy while keeping the 12px value tokens
   distinct. */
QLabel#HintSM {{
    font-size: {FONT_BODY}px;
    color: {role("TEXT_MUTED", theme)};
}}
QLabel#StateMD {{
    font-size: {FONT_SMALL}px;
    font-weight: 600;
    color: {role("TEXT_MUTED", theme)};
    letter-spacing: 0.5px;
}}

/* ===== Status pills (QLabel with objectName) ===== */
QLabel#PillInReview {{
    background: {role("ACCENT_SECONDARY", theme)};
    color: {role("BADGE_BLUE_TEXT", theme)};
    border: 1px solid {role("BADGE_BLUE_BORDER", theme)};
    border-radius: {RADIUS_LG};
    padding: 2px 8px;
    font-size: {FONT_SMALL}px;
    font-weight: 700;
}}
QLabel#PillDraft {{
    background: {role("SURFACE_ALT", theme)};
    color: {role("TEXT_MUTED", theme)};
    border: 1px solid {role("BORDER_SUBTLE", theme)};
    border-radius: {RADIUS_LG};
    padding: 2px 8px;
    font-size: {FONT_SMALL}px;
    font-weight: 700;
}}
QLabel#PillAuthorContacted {{
    background: {role("STATE_ERROR_BG", theme)};
    color: {role("STATE_ERROR_TEXT", theme)};
    border: 1px solid {role("STATE_ERROR_BORDER", theme)};
    border-radius: {RADIUS_LG};
    padding: 2px 8px;
    font-size: {FONT_SMALL}px;
    font-weight: 700;
}}
QLabel#PillReady {{
    background: {role("ACCENT_TERTIARY", theme)};
    color: {role("TEXT_ON_ACCENT", theme)};
    border: 1px solid {role("ACCENT_TERTIARY", theme)};
    border-radius: {RADIUS_LG};
    padding: 2px 8px;
    font-size: {FONT_SMALL}px;
    font-weight: 700;
}}
QLabel#PillClean {{
    color: {role("ACCENT_PRIMARY", theme)};
    font-size: {FONT_SMALL}px;
    font-weight: 600;
}}
QLabel#PillFlagged {{
    color: {role("STATE_ERROR_GRAPHIC", theme)};
    font-size: {FONT_SMALL}px;
    font-weight: 600;
}}

/* ===== Auto-check rows ===== */
#CheckRowPass {{
    background: {role("SURFACE_TINT", theme)};
    border: 1px solid {role("BORDER_SUBTLE", theme)};
    border-radius: 8px;
}}
#CheckRowFail {{
    background: {role("STATE_ERROR_SURFACE", theme)};
    border: 1px solid {role("STATE_ERROR_BORDER", theme)};
    border-radius: 8px;
}}

/* ===== ScrollBar (subtle) ===== */
/* Opaque table-surface gutters: transparent tracks failed to composite and
   left the scrollbar lanes + the bottom-right meeting corner page-colored
   ("unfilled"). White matches every table/list surface in the app. */
QScrollBar:vertical {{
    background: {role("SURFACE_CARD", theme)};
    width: 8px;
    margin: 0;
    border-radius: {RADIUS_SM};
}}
QScrollBar::handle:vertical {{
    background: {role("BORDER_SUBTLE", theme)};
    border-radius: {RADIUS_SM};
    min-height: 24px;
}}
QScrollBar::groove:vertical {{
    background: transparent;
    border: none;
    border-radius: {RADIUS_SM};
    margin: 0px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: {role("SURFACE_CARD", theme)};
    height: 8px;
    margin: 0;
    border-radius: {RADIUS_SM};
}}
QScrollBar::groove:horizontal {{
    background: transparent;
    border: none;
    border-radius: {RADIUS_SM};
    margin: 0px;
}}
QScrollBar::handle:horizontal {{
    background: {role("BORDER_SUBTLE", theme)};
    border-radius: {RADIUS_SM};
    min-width: 24px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ===== TabWidget ===== */
/* The pane itself draws NO outline: QTabWidget::pane is painted by Qt's
   special tab-frame primitive, which ignores border-radius (it shortens
   straight edges for the radius but never paints the corner arcs, leaving
   open corners — verified by pixel-probe against a QFrame control).
   The outline + rounded corners come from a plain QFrame#Card wrapper
   around the tab widget (see settings_dialog.py), which uses the generic
   frame renderer where arcs work. Pane stays transparent so the card's
   white face shows through; tab-bar rules below are unaffected. */
QTabWidget::pane {{
    border: none;
    border-radius: 0px;
    background: transparent;
}}
QTabBar::tab {{
    background: transparent;
    color: {role("TEXT_MUTED", theme)};
    padding: 8px 14px;
    border: 1px solid transparent;
    border-bottom: 2px solid transparent;
    font-size: {FONT_SMALL}px;
    font-weight: 600;
}}
QTabBar::tab:selected {{
    color: {role("ACCENT_PRIMARY", theme)};
    border-bottom: 2px solid {role("ACCENT_PRIMARY", theme)};
    background: {role("SURFACE_CARD", theme)};
}}
QTabBar::tab:hover {{ color: {role("TEXT_PRIMARY", theme)}; }}

/* ===== Progress ===== */
QProgressBar {{
    border: 1px solid {role("BORDER_SUBTLE", theme)};
    border-radius: {RADIUS_LG};
    background: {role("SURFACE_SUBTLE", theme)};
    height: 6px;
}}
QProgressBar::chunk {{
    background: {role("ACCENT_PRIMARY", theme)};
    border-radius: {RADIUS_LG};
}}

/* ===== Menu bar ===== */
QMenuBar {{
    background: {role("SURFACE_CARD", theme)};
    border-bottom: 1px solid {role("BORDER_SUBTLE", theme)};
}}
QMenuBar::item:selected {{ background: {role("SURFACE_TINT", theme)}; }}
QMenu {{
    background: {role("SURFACE_CARD", theme)};
    border: 1px solid {role("BORDER_SUBTLE", theme)};
    /* Fully rounded: a menu never changes shape when it opens (2026-11-24). */
    border-top-left-radius: {RADIUS_LG};
    border-top-right-radius: {RADIUS_LG};
    border-bottom-left-radius: {RADIUS_LG};
    border-bottom-right-radius: {RADIUS_LG};
    padding: 4px;
}}
QMenu::item:selected {{ background: {role("ACCENT_SECONDARY", theme)}; border-radius: {RADIUS_LG}; }}

/* ===== Status bar ===== */
QStatusBar {{
    background: {role("SURFACE_CARD", theme)};
    border-top: 1px solid {role("BORDER_SUBTLE", theme)};
    color: {role("TEXT_MUTED", theme)};
    font-size: {FONT_SMALL}px;
}}
QStatusBar::item {{ border: none; }}

/* ===== Dock widgets (log panel renders its own card, no native title bar) ===== */
QDockWidget {{
    background: {role("SURFACE_PAGE", theme)};
    border: none;
    color: {role("TEXT_PRIMARY", theme)};
    titlebar-close-icon: none;
    titlebar-normal-icon: none;
}}

/* ===== Splitter ===== */
QSplitter::handle {{
    background: {role("BORDER_SUBTLE", theme)};
}}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}
"""


# addApplicationFont returns a NEW id on every call even for the same file,
# so repeated registration leaks font entries. Register once per process.
_REGISTERED_FONTS: dict[str, int] = {}


def register_fonts() -> dict[str, bool]:
    """Load the three bundled variable faces into Qt's font database.

    Called from :func:`apply_theme` (before the app font and stylesheet are
    set), and safe to call again: a file already registered is skipped.
    Returns ``{family: loaded}`` so a probe/test can assert the bundle.
    """
    from PySide6.QtGui import QFontDatabase

    loaded: dict[str, bool] = {}
    for family, filename in BUNDLED_FONTS:
        path = asset_path(f"fonts/{filename}")
        if not path:
            loaded[family] = False
            continue
        if path not in _REGISTERED_FONTS:
            _REGISTERED_FONTS[path] = QFontDatabase.addApplicationFont(path)
        font_id = _REGISTERED_FONTS[path]
        loaded[family] = font_id >= 0 and family in QFontDatabase.applicationFontFamilies(font_id)
    return loaded


#: Attribute a kit factory sets on a widget to carry its own repaint.
#: The value is a list of ``(rebuilder_name, args, kwargs)`` tuples of plain
#: data - never a closure. A closure would capture the widget, and the widget
#: holding the closure makes a reference cycle; a cycle keeps the Python
#: wrapper alive after Qt has deleted the C++ object, and the next method call
#: on that wrapper aborts the process. Plain data cannot do that, and it dies
#: with the widget. A list, so one widget can carry both a sheet and an icon.
RETHEME_ATTR = "_retheme_spec"

#: Installed by ``ui.widgets`` at import. ``ui.theme`` must not import the
#: kit (the kit imports the theme), so the extension point lives here and
#: the implementation registers itself.
_retheme_hook: Callable[["QApplication"], int] | None = None


def set_retheme_hook(hook: Callable[["QApplication"], int] | None) -> None:
    """Install the callable that repaints scoped sheets (used by ``ui.widgets``)."""
    global _retheme_hook
    _retheme_hook = hook


def retheme_widgets(app: "QApplication") -> int:
    """Repaint every widget that carries a scoped sheet. Returns how many ran.

    Called from :func:`apply_theme` after the application sheet is replaced.
    Without a hook (the kit not imported) this is a no-op.
    """
    if _retheme_hook is None:
        return 0
    try:
        return _retheme_hook(app)
    except Exception:
        return 0


#: The palette-based application sheet is installed once; a switch only
#: swaps the palette, which Qt applies without re-polishing every widget.
_APP_QSS_INSTALLED = False
#: Avoid repeated setPalette calls: Qt re-policies on every one, and the
#: suite applies the same theme many times per worker.
_APPLIED_PALETTE_THEME: str | None = None


def apply_theme(app: "QApplication", theme: str | None = None, *, retheme: bool = False) -> None:
    """Register the bundled faces, then apply global QSS and default font.

    ``theme`` is the role table to paint; it defaults to the active one,
    so a plain ``apply_theme(app)`` after ``set_active_theme(name)``
    repaints in that theme.

    ``retheme`` also repaints widgets that carry their own scoped sheet
    (cards, buttons, tables). Pass ``False`` when building a second theme's
    widgets in one process - the gallery does - so a temporary switch does
    not repaint the column that is already built.
    """
    from PySide6.QtGui import QFont, QFontDatabase

    register_fonts()
    # A QFont keeps its requested name even when the family is absent, so
    # `QFont("Inter").family()` cannot detect a fallback. Ask the database
    # instead; with the bundle loaded this branch always takes Inter.
    base = "Inter" if "Inter" in QFontDatabase.families() else "Segoe UI"
    font = QFont(base)
    # Pixel size (not point size) so Qt measures what the QSS paints:
    # tokens are px (FONT_BODY=13) while a 9pt app font is ~12px.
    font.setPixelSize(FONT_BODY)
    app.setFont(font)

    # One static, palette-based application sheet for the process lifetime.
    # Switching themes replaces the palette (~0s) instead of the stylesheet
    # (~1ms per live widget). Role-specific faces keep their exact colours
    # in scoped sheets, re-tinted below.
    global _APP_QSS_INSTALLED, _APPLIED_PALETTE_THEME
    if not _APP_QSS_INSTALLED:
        app.setStyleSheet(palette_qss())
        _APP_QSS_INSTALLED = True
    name = theme or ACTIVE_THEME
    if name != _APPLIED_PALETTE_THEME:
        app.setPalette(palette_for(name))
        _APPLIED_PALETTE_THEME = name
    _install_interaction_tracking(app)
    if retheme:
        retheme_widgets(app)
    _log_active_role_table()


def animate_theme_change(window: "QWidget", repaint: Callable[[], None]) -> None:
    """Fade ``window`` out, ``repaint``, fade it back in.

    A stylesheet swap is one atomic repaint, so without a transition the
    window cuts from one palette to the other in a single frame (dv-4jm.3).
    Qt cannot interpolate a whole stylesheet, so the fade runs on a
    ``QGraphicsOpacityEffect``: the window dims toward the desktop, the new
    sheet goes on at the dimmest point, and it fades back up. 140 ms each
    way reads as a fade without feeling like a wait.

    An effect rather than ``windowOpacity``: window opacity is a
    window-manager property, and the offscreen/minimal platform plugins have
    no manager to blend against - they answer it with a Qt warning and no
    fade. An effect is a paint-time operation, so the same code path runs
    (and is testable) on every platform.

    The window is named by the caller rather than looked up. "The first
    visible top-level window" is ambiguous in a process that may hold
    several - the app's main window, a dialog, a test's own window - and
    picking wrong fades a window the curator is not looking at.

    Falls back to an immediate ``repaint()`` when there is nothing to fade:
    a window that already carries a graphics effect, which this must not
    clobber.
    """
    try:
        from PySide6.QtCore import QEasingCurve, QPropertyAnimation
        from PySide6.QtWidgets import QGraphicsEffect, QGraphicsOpacityEffect
    except Exception:
        repaint()
        return

    if window is None or window.graphicsEffect() is not None:
        repaint()
        return

    effect = QGraphicsOpacityEffect(window)
    effect.setOpacity(1.0)
    window.setGraphicsEffect(effect)

    fade_ms = 140
    curve = QEasingCurve.Type.InOutQuad
    # One slot, replaced per switch: a running animation must not be
    # collected mid-flight, and keeping only the newest keeps this bounded
    # no matter how often the curator toggles the theme.
    holder: dict[str, QPropertyAnimation] = {}

    def _fade(start: float, end: float, done: Callable[[], None] | None = None) -> None:
        animation = QPropertyAnimation(effect, b"opacity", effect)
        animation.setDuration(fade_ms)
        animation.setStartValue(start)
        animation.setEndValue(end)
        animation.setEasingCurve(curve)
        if done is not None:
            animation.finished.connect(done)
        # Parented to the effect, so Qt owns the lifetime; deleteLater on
        # completion keeps repeated switches from accumulating finished
        # QObjects.
        animation.finished.connect(animation.deleteLater)
        holder["fade"] = animation
        animation.start()

    def _swap() -> None:
        repaint()
        _fade(0.0, 1.0, _restore)

    def _restore() -> None:
        # Drop the effect so the window paints normally again; leaving it on
        # would keep an offscreen render surface alive for no reason.
        # The cast is for the type checker: Qt documents None as "remove the
        # effect" but types the parameter as non-optional.
        window.setGraphicsEffect(cast("QGraphicsEffect", None))

    _fade(1.0, 0.0, _swap)


def _log_active_role_table() -> None:
    """Record the role table the app is painting (the Log page shows it).

    A theme is a table of role values; naming the live table in the log
    says which one the pixels came from, without opening a debugger.
    """
    try:
        from curation.applog import log as _log

        table = role_table()
        _log(f"theme-role-table-{ACTIVE_THEME}-roles-{len(table)}")
    except Exception:
        pass


def action_button_style(primary: bool = False, theme: str | None = None) -> str:
    """Build the scoped (widget-level) button sheet for a critical action.

    A widget-level stylesheet replaces the application sheet for that
    subtree, and a button face inside a styled panel does not paint
    otherwise - so critical actions carry their own copy. That copy comes
    from ``button_qss()``, the same generator the app-level rules use,
    so the two cannot drift.

    ``theme`` defaults to the active role table, so a sheet built after
    a theme switch paints the new theme.

    Views do not call this: they build the button with the kit's
    ``make_action_button()``.
    """
    return button_qss(
        "primary" if primary else "secondary",
        selector="QPushButton",
        theme=theme or ACTIVE_THEME,
    )


# The badge roles: (background, text, border) per role. Every distinct
# status / curation label gets its own role so dataset-page badges scan
# at a glance, and every role is in the contrast contract (the test
# checks each role's text against its fill).
_BADGE_ROLES: dict[str, tuple[str, str, str]] = {
    "neutral": ("BADGE_NEUTRAL_BG", "BADGE_NEUTRAL_TEXT", "BADGE_NEUTRAL_BORDER"),
    "grey": ("BADGE_GREY_BG", "BADGE_GREY_TEXT", "BADGE_GREY_BORDER"),
    "blue": ("BADGE_BLUE_BG", "BADGE_BLUE_TEXT", "BADGE_BLUE_BORDER"),
    "indigo": ("BADGE_INDIGO_BG", "BADGE_INDIGO_TEXT", "BADGE_INDIGO_BORDER"),
    "green": ("BADGE_GREEN_BG", "BADGE_GREEN_TEXT", "BADGE_GREEN_BORDER"),
    "green-soft": ("BADGE_GREEN_SOFT_BG", "BADGE_GREEN_SOFT_TEXT", "BADGE_GREEN_SOFT_BORDER"),
    "red": ("BADGE_RED_BG", "BADGE_RED_TEXT", "BADGE_RED_BORDER"),
    "red-soft": ("BADGE_RED_SOFT_BG", "BADGE_RED_SOFT_TEXT", "BADGE_RED_SOFT_BORDER"),
    "orange": ("BADGE_ORANGE_BG", "BADGE_ORANGE_TEXT", "BADGE_ORANGE_BORDER"),
    "violet": ("BADGE_VIOLET_BG", "BADGE_VIOLET_TEXT", "BADGE_VIOLET_BORDER"),
    "amber": ("BADGE_AMBER_BG", "BADGE_AMBER_TEXT", "BADGE_AMBER_BORDER"),
    "teal": ("BADGE_TEAL_BG", "BADGE_TEAL_TEXT", "BADGE_TEAL_BORDER"),
    "pink": ("BADGE_PINK_BG", "BADGE_PINK_TEXT", "BADGE_PINK_BORDER"),
    "lime": ("BADGE_LIME_BG", "BADGE_LIME_TEXT", "BADGE_LIME_BORDER"),
    "sky": ("BADGE_SKY_BG", "BADGE_SKY_TEXT", "BADGE_SKY_BORDER"),
    "sand": ("BADGE_SAND_BG", "BADGE_SAND_TEXT", "BADGE_SAND_BORDER"),
}

# Which role a curation label wears. Order matters: substring match on
# the lowered label, specific phrases first ("hold for internal review"
# must beat bare "review").
_LABEL_BADGE_ROLES: list[tuple[str, str]] = [
    ("deaccessioned", "grey"),
    ("reject", "red"),
    ("revisions", "red-soft"),
    ("needs review", "orange"),
    ("hold", "violet"),
    ("author contacted", "amber"),
    ("contact author", "amber"),
    ("approve", "green"),
    ("ready", "teal"),
    ("publish", "green-soft"),
    ("released", "green-soft"),
    ("review", "blue"),
    ("draft", "neutral"),
]

# Fallback roles for custom instance labels: deterministic (md5, not
# hash() which is salted per process), so the same label always wears
# the same role.
_LABEL_BADGE_FALLBACK_ROLES: tuple[str, ...] = (
    "teal",
    "indigo",
    "pink",
    "lime",
    "sky",
    "sand",
)


def _resolve_badge(colours: tuple[str, str, str]) -> tuple[str, str, str]:
    """Resolve a badge's three role names in the active theme (dv-314)."""
    background, foreground, border = colours
    return colour(background), colour(foreground), colour(border)


def label_badge_colors(label: str) -> tuple[str, str, str]:
    """(background, text, border) for a status/curation label. Never raises."""
    try:
        lowered = (label or "").strip().lower()
    except Exception:
        lowered = ""
    for phrase, role in _LABEL_BADGE_ROLES:
        if phrase and phrase in lowered:
            return _resolve_badge(_BADGE_ROLES[role])
    try:
        import hashlib

        digest = hashlib.md5(lowered.encode("utf-8")).digest()
        role = _LABEL_BADGE_FALLBACK_ROLES[digest[0] % len(_LABEL_BADGE_FALLBACK_ROLES)]
        return _resolve_badge(_BADGE_ROLES[role])
    except Exception:
        return _resolve_badge(_BADGE_ROLES["teal"])


def label_badge_style(label: str) -> str:
    """Build an inline badge face with DOI-badge chrome (bordered 8px box).

    Uses the label's own role colours. Inline so it always paints (see
    action_button_style). Views do not call this: the kit's
    ``make_badge()`` does.
    """
    bg, fg, border = label_badge_colors(label)
    return (
        f"QLabel {{ background: {bg}; color: {fg}; border: 1px solid {border}; "
        f"border-radius: {RADIUS_LG}; padding: 3px 8px; font-size: {FONT_SMALL}px; "
        f"font-weight: 700; }}"
    )


def _install_interaction_tracking(app: "QApplication") -> None:  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
    """Pointing-hand cursors + keyboard-only focus tint, in one app filter.

    Two behaviours share one QApplication event filter: QSS cannot set
    cursors, and it has no "focus arrived from the keyboard" selector.
    Keeping them together halves the Python callbacks during startup, when
    Qt delivers tens of thousands of show/polish events (the filters used to
    be separate, so every event crossed into Python twice).

    Keyboard focus: Tab/arrow presses arm the flag; any mouse press disarms
    it and drops the tint from the focused widget (clicking the
    already-focused widget fires no focusChanged, so it is cleared here).
    On focus change the new widget gets ``focusVisible="true"`` and the old
    one loses it, painted as a colour tint — tabbing shows focus, clicking
    never does, and no outline is ever drawn (2026-10-02).
    """
    try:
        from PySide6.QtCore import QEvent, QObject, Qt
        from PySide6.QtWidgets import QAbstractButton

        state = {"kbd": False}
        nav_keys = {
            Qt.Key.Key_Tab,
            Qt.Key.Key_Backtab,
            Qt.Key.Key_Left,
            Qt.Key.Key_Right,
            Qt.Key.Key_Up,
            Qt.Key.Key_Down,
            Qt.Key.Key_Home,
            Qt.Key.Key_End,
            Qt.Key.Key_PageUp,
            Qt.Key.Key_PageDown,
        }

        def _paint(w: "QWidget | None", on: bool) -> None:
            try:
                if w is None:
                    return
                cur = w.property("focusVisible")
                if (cur == "true") == on:
                    return
                w.setProperty("focusVisible", "true" if on else "false")
                w.style().unpolish(w)
                w.style().polish(w)
                w.update()
            except Exception:
                pass

        class _Interaction(QObject):
            def eventFilter(self, obj: "QObject", event: "QEvent") -> bool:
                try:
                    t = event.type()
                    if t == QEvent.Type.Enter:
                        if isinstance(obj, QAbstractButton):
                            if obj.isEnabled():
                                obj.setCursor(Qt.CursorShape.PointingHandCursor)
                            else:
                                obj.unsetCursor()
                    elif t == QEvent.Type.KeyPress:
                        if cast(Any, event).key() in nav_keys:
                            state["kbd"] = True
                    elif t == QEvent.Type.MouseButtonPress:
                        state["kbd"] = False
                        _paint(app.focusWidget(), False)
                except Exception:
                    pass
                return False

        filt = _Interaction(app)
        app.installEventFilter(filt)
        try:
            cast(Any, app)._interaction_ref = filt
        except Exception:
            pass

        def _on_focus_changed(old: "QWidget | None", new: "QWidget | None") -> None:
            try:
                _paint(old, False)
                if state["kbd"]:
                    _paint(new, True)
            except Exception:
                pass

        app.focusChanged.connect(_on_focus_changed)
    except Exception:
        pass


def selectable_labels(root: "QWidget") -> None:
    """Make every QLabel under root selectable with mouse + keyboard.

    The selection is themed: the system highlight colour is not used (it
    renders as a black box behind the text on a dark palette), the app
    paints the same light-blue selection its inputs use. A rich-text
    label also paints its document background with the palette's Base
    role, which is kept transparent so no box shows behind the text.
    """
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QColor, QPalette
        from PySide6.QtWidgets import QLabel

        for lbl in root.findChildren(QLabel):
            try:
                flags = lbl.textInteractionFlags()
                lbl.setTextInteractionFlags(
                    flags
                    | Qt.TextInteractionFlag.TextSelectableByMouse
                    | Qt.TextInteractionFlag.TextSelectableByKeyboard
                )
                pal = lbl.palette()
                pal.setColor(QPalette.ColorRole.Base, Qt.GlobalColor.transparent)
                pal.setColor(QPalette.ColorRole.Window, Qt.GlobalColor.transparent)
                pal.setColor(QPalette.ColorRole.Highlight, QColor(PRIMARY_FIXED))
                pal.setColor(QPalette.ColorRole.HighlightedText, QColor(ON_SURFACE))
                lbl.setPalette(pal)
            except Exception:
                continue
    except Exception:
        pass


def enable_table_copy(table: "QTableWidget") -> None:
    """Ctrl+C support + extended selection for a QTableWidget (best-effort)."""
    try:
        from PySide6.QtCore import QEvent, QObject, Qt
        from PySide6.QtWidgets import QApplication, QTableWidget

        table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)

        class _CopyFilter(QObject):
            def eventFilter(self, _obj: "QObject", event: "QEvent") -> bool:
                try:
                    if event.type() == QEvent.Type.KeyPress and cast(Any, event).matches(
                        Qt.Key.Key_Copy
                    ):
                        ranges = table.selectedRanges()
                        if ranges:
                            rows: set[int] = set()
                            for rng in ranges:
                                rows.update(range(rng.topRow(), rng.bottomRow() + 1))
                            lines = []
                            for r in sorted(rows):
                                cells = []
                                for rng in ranges:
                                    if rng.topRow() <= r <= rng.bottomRow():
                                        for c in range(rng.leftColumn(), rng.rightColumn() + 1):
                                            item = table.item(r, c)
                                            cells.append(item.text() if item else "")
                                lines.append("\t".join(cells))
                            QApplication.clipboard().setText("\n".join(lines))
                            return True
                except Exception:
                    pass
                return False

        table.installEventFilter(_CopyFilter(table))
        try:
            # Keep a reference so the filter is not garbage-collected.
            cast(Any, table)._copy_filter_ref = table.findChildren(_CopyFilter)[-1]
        except Exception:
            pass
    except Exception:
        pass


def enable_list_copy(list_widget: "QListWidget") -> None:
    """Ctrl+C support for a QListWidget (copies selected rows as lines)."""
    try:
        from PySide6.QtCore import QEvent, QObject, Qt
        from PySide6.QtWidgets import QApplication

        list_widget.setSelectionMode(cast(Any, list_widget).ExtendedSelection)

        class _ListCopyFilter(QObject):
            def eventFilter(self, _obj: "QObject", event: "QEvent") -> bool:
                try:
                    if event.type() == QEvent.Type.KeyPress and cast(Any, event).matches(
                        Qt.Key.Key_Copy
                    ):
                        items = list_widget.selectedItems()
                        if items:
                            QApplication.clipboard().setText("\n".join(i.text() for i in items))
                            return True
                except Exception:
                    pass
                return False

        list_widget.installEventFilter(_ListCopyFilter(list_widget))
        try:
            cast(Any, list_widget)._copy_filter_ref = list_widget.findChildren(_ListCopyFilter)[-1]
        except Exception:
            pass
    except Exception:
        pass
