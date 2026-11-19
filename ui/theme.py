"""Design tokens for the app (originally extracted from a Tailwind mock).

Palette is Material 3-like: primary #004ccd, tertiary #4142cf, error #ba1a1a,
surface #faf8ff, backgrounds #f2f3ff/#eaedff, outline-variant #c3c6d8.
Typography is Inter (body) + JetBrains Mono (monospace).

The colour layer is split in two: the palette says what a colour IS,
the role layer says what it is FOR, and the role layer is a table per
theme - so switching theme is a table swap, not a re-skin.
"""

from collections.abc import Mapping

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

# Deterministic identifier-colour palette for the syntax-highlighting log
# (cyan/amber/blue/violet/pink tints; md5-selected, never random per run).
LOG_IDENTIFIER_PALETTE = (
    "#0e7490",  # cyan-700
    AMBER_700,
    "#1d4ed8",  # blue-700
    "#7c3aed",  # violet-600
    "#be185d",  # pink-700
    "#0369a1",  # sky-700
    SUCCESS_DARK,
    WARNING_DARK,
    "#6d28d9",  # violet-700
    "#9d174d",  # pink-800
    "#155e75",  # cyan-800
    "#b91c1c",  # red-700
    "#166534",  # green-800
    "#92400e",  # amber-800
    "#1e40af",  # blue-800
)

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
SURFACE_ROW = SURFACE_CONTAINER_LOW  # alternating / separated rows
SURFACE_HEADER = SURFACE_CONTAINER  # table and tree header bands
SURFACE_RAISED = SURFACE_CONTAINER_HIGH  # a raised panel (hover, metric card)
SURFACE_ALT = SURFACE_VARIANT  # an alternate surface (divider band)
SURFACE_DISABLED = MUTED_BG  # a disabled control's face

# --- Border roles ---
BORDER_SUBTLE = OUTLINE_VARIANT  # card and section edges
BORDER_STRONG = OUTLINE  # dividers that carry meaning
BORDER_CONTROL = CONTROL_OUTLINE  # input / button edges (>= 3:1)
BORDER_DISABLED = MUTED_BORDER  # a disabled control's edge

# --- Accent roles ---
ACCENT_PRIMARY = PRIMARY
ACCENT_PRIMARY_HOVER = ON_PRIMARY_FIXED_VARIANT
ACCENT_PRIMARY_PRESSED = PRIMARY_PRESSED
ACCENT_PRIMARY_DISABLED = PRIMARY_DISABLED
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
STATE_SUCCESS_TEXT = SUCCESS_DARK
STATE_SUCCESS_GRAPHIC = SUCCESS  # a success icon or mark (3.3:1 on a card)
STATE_WARNING_TEXT = WARNING_DARK
STATE_WARNING_GRAPHIC = WARNING  # a warning icon or mark (3.2:1 on a card)

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
    "SURFACE_ROW",
    "SURFACE_HEADER",
    "SURFACE_RAISED",
    "SURFACE_ALT",
    "SURFACE_DISABLED",
    "BORDER_SUBTLE",
    "BORDER_STRONG",
    "BORDER_CONTROL",
    "BORDER_DISABLED",
    "ACCENT_PRIMARY",
    "ACCENT_PRIMARY_HOVER",
    "ACCENT_PRIMARY_PRESSED",
    "ACCENT_PRIMARY_DISABLED",
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
    "STATE_SUCCESS_TEXT",
    "STATE_SUCCESS_GRAPHIC",
    "STATE_WARNING_TEXT",
    "STATE_WARNING_GRAPHIC",
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
    "SURFACE_ROW": "#1f2330",
    "SURFACE_HEADER": "#242938",
    "SURFACE_RAISED": "#2a3040",
    "SURFACE_ALT": "#20242f",
    "SURFACE_DISABLED": "#252936",
    "BORDER_SUBTLE": "#343a4b",
    "BORDER_STRONG": "#4a5165",
    "BORDER_CONTROL": "#6b7488",
    "BORDER_DISABLED": "#333849",
    "ACCENT_PRIMARY": "#6ea8ff",
    "ACCENT_PRIMARY_HOVER": "#8bbaff",
    "ACCENT_PRIMARY_PRESSED": "#4d8bff",
    "ACCENT_PRIMARY_DISABLED": "#3d5a8f",
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
    "STATE_SUCCESS_TEXT": "#7ee2a8",
    "STATE_SUCCESS_GRAPHIC": "#4ade80",
    "STATE_WARNING_TEXT": "#ffcf7a",
    "STATE_WARNING_GRAPHIC": "#fbbf24",
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


# --- Typography (Qt QSS uses px) ---
FONT_FAMILY = "Inter, 'Segoe UI', sans-serif"
MONO_FAMILY = "'JetBrains Mono', Consolas, monospace"

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
FONT_MICRO = 11  # log level badges (the smallest text in the app; dv-vw0)
FONT_HEADLINE = 22
FONT_TITLE = 16
FONT_SECTION = 15
FONT_BODY = 13
FONT_SMALL = 12
FONT_CAPTION = 11

# --- Shadows (simulated via border) ---
CARD_BORDER = f"1px solid {OUTLINE_VARIANT}"

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
    ("subtle hint text on a card", TEXT_SUBTLE, SURFACE_CARD, "text", 4.5),
    ("text on the brand fill", TEXT_ON_ACCENT, ACCENT_PRIMARY, "text", 4.5),
    ("text on a tint", TEXT_ON_TINT, SURFACE_TINT, "text", 4.5),
    ("error text on a card", TEXT_DANGER, SURFACE_CARD, "text", 4.5),
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


def _relative_luminance(hex_color: str) -> float:
    """WCAG 2.1 relative luminance of a #rrggbb colour."""
    h = hex_color.lstrip("#")
    channels = []
    for i in (0, 2, 4):
        c = int(h[i : i + 2], 16) / 255
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def log_identifier_color(seed: int) -> str:
    """Pick a deterministic identifier colour for the log's syntax highlighting.

    The identifier palette is a raw palette: it stays inside the theme,
    and a view asks for a colour by seed rather than naming a hue.
    """
    return LOG_IDENTIFIER_PALETTE[seed % len(LOG_IDENTIFIER_PALETTE)]


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


def asset_path(name: str) -> str:
    """Absolute path to a bundled ui/asset (works frozen via sys._MEIPASS)."""
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


def app_icon_path() -> str:
    """Absolute path to the app icon (ui/assets/docent.png).

    The About page keeps this mark. asset_path resolves the bundled
    copy both in dev and frozen (the exe ships --add-data "ui/assets;ui/assets").
    """
    return asset_path("docent.png")


def mark_icon_path() -> str:
    """Absolute path to the 16x16.png mark (ui/assets/16x16.png).

    The dashboard status pill's mark and the window icon the Windows
    taskbar draws use this; the About page keeps docent.png
    (app_icon_path). Resolved by asset_path (dev + frozen).
    """
    return asset_path("16x16.png")


def _chevron_qss() -> str:
    """Down-arrow rule: Lucide chevron when bundled, CSS triangle fallback."""
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
    border-top: 6px solid {ON_SURFACE_VARIANT};
    margin-right: 8px;
}}"""


def header_section_qss(*, flush: bool = False) -> str:
    """Table/tree header section rules — one source of truth.

    A widget-level stylesheet replaces the app-level rules for that
    subtree (Qt does not merge them), so every table that sets its own
    stylesheet has to repeat the header rules. They are repeated from
    here instead of by hand, so the app-level sheet and the local sheets
    cannot drift apart.

    flush=True squares the end caps: the header sits flush inside a card,
    where a rounded cap would notch the unfilled corner.
    """
    radius = "0px" if flush else RADIUS_LG
    return (
        # The header is one continuous band: the area right of the last
        # section (the vertical scrollbar's lane) carries the header's
        # own background, not the page colour.
        f"QHeaderView {{ background: {SURFACE_CONTAINER}; }} "
        f"QHeaderView::section {{ background: {SURFACE_CONTAINER}; "
        f"color: {ON_SURFACE_VARIANT}; padding: 8px 14px 8px 12px; "
        # One continuous band: a bottom rule only. A right border drew a
        # vertical bar between sections, which reads as a column divider
        # and crept back into the review-config and dataset tables.
        f"border: none; border-bottom: 1px solid {OUTLINE_VARIANT}; "
        f"font-size: {FONT_CAPTION}px; "
        # No text-transform here: Qt applies it when it *paints* a label
        # but not when it *measures* one, so the painted header was wider
        # than the text Qt elided against and a narrow section lost its
        # first letter ("SUBMITTING AUTHOR" read as "UBMITTING AUTHOR").
        # The kit stores the header labels in the case they are painted
        # in (see AppTable.setHorizontalHeaderLabels), so the metrics and
        # the paint agree - and a translation can choose its own casing.
        "font-weight: 600; } "
        f"QHeaderView::section:hover {{ background: {SURFACE_CONTAINER_HIGH}; }} "
        f"QHeaderView::section:pressed {{ background: {PRIMARY_FIXED}; }} "
        f"QHeaderView::section:first {{ border-top-left-radius: {radius}; }} "
        f"QHeaderView::section:last {{ border-top-right-radius: {radius}; }} "
    )


def selection_qss(scope: str = "") -> str:
    """Row selection and hover for an item view — one source of truth.

    Every table and tree wears the same face: a quiet full-row tint on
    selection (never a per-cell box) and an even quieter hover. Views
    that set a local stylesheet have to repeat the rules, so they take
    them from here instead of writing their own — the dashboard queue,
    the metadata tree and the extensions table had drifted apart.

    scope is the view selector ("QTableWidget", "QTreeView"). Leave it
    empty when embedding in a rule that already carries the selector.
    """
    # No space between the scope and ``::item``: a descendant selector
    # (``QTreeView ::item``) matches a *child widget*, so the rules were
    # silently dead and views fell back to the native highlight colour.
    prefix = f"{scope}::item" if scope else "::item"
    # SECONDARY_CONTAINER is the palette's selection fill (it already backs
    # menus and combo popups); SURFACE_TINT is the header band, so using it
    # here made a selected row indistinguishable from its own header.
    # The selected rules repeat instead of sharing a `tint` variable: the
    # catalogue guard reads every prose-shaped literal in this module, and
    # a bare ":selected { " fragment reads as prose.
    return (
        f"{prefix}:hover {{ background: {SURFACE_SUBTLE}; }} "
        # Keep the selected face when the view loses focus: the inactive
        # palette would otherwise drop the row back to an unstyled white.
        f"{prefix}:selected {{ background: {SECONDARY_CONTAINER}; "
        f"color: {TEXT_PRIMARY}; }} "
        f"{prefix}:selected:!active {{ background: {SECONDARY_CONTAINER}; "
        f"color: {TEXT_PRIMARY}; }} "
    )


def scrollbar_lane_qss(scope: str = "") -> str:
    """Transparent scrollbar lanes for a widget scope.

    A filled lane paints the page colour over the card's rounded
    bottom-right corner, so the card border ends in a white notch. The
    lanes stay transparent and the card's own surface shows through;
    thumbs and grooves keep coming from the global theme.
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
}


def button_qss(
    kind: str = "secondary",
    *,
    selector: str | None = None,
    scope: str = "",
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
    """
    prefix = f"{scope} " if scope else ""
    if selector:
        sel = f"{prefix}{selector}"
    else:
        sel = f"{prefix}QPushButton#{BUTTON_OBJECTS.get(kind, 'SecondaryButton')}"

    if kind == "primary":
        return (
            f"{sel} {{ background: {PRIMARY}; color: {ON_PRIMARY}; border: none; "
            f"border-radius: {RADIUS_LG}; padding: 8px 16px; font-weight: 600; "
            f"font-size: {FONT_SMALL}px; }} "
            f'{sel}[focusVisible="true"] {{ background: {PRIMARY_CONTAINER}; }} '
            f"{sel}:hover {{ background: {ON_PRIMARY_FIXED_VARIANT}; }} "
            f"{sel}:pressed {{ background: {PRIMARY_PRESSED}; }} "
            # Disabled: a muted blue face with the dark text colour. White
            # on the old face was 2.35:1 - the label was unreadable.
            f"{sel}:disabled {{ background: {PRIMARY_DISABLED}; color: {TEXT_PRIMARY}; }}"
        )
    if kind == "secondary":
        return (
            f"{sel} {{ background: {SURFACE_CONTAINER_LOWEST}; color: {ON_SURFACE}; "
            f"border: 1px solid {BORDER_CONTROL}; border-radius: {RADIUS_LG}; "
            f"padding: 7px 14px; font-weight: 600; font-size: {FONT_SMALL}px; }} "
            f'{sel}[focusVisible="true"] {{ background: {PRIMARY_FIXED_DIM}; }} '
            f"{sel}:hover {{ background: {SURFACE_CONTAINER_HIGH}; "
            f"border: 1px solid {PRIMARY}; }} "
            f"{sel}:pressed {{ background: {SECONDARY_CONTAINER}; }} "
            f"{sel}:disabled {{ background: {SURFACE_CONTAINER_LOW}; "
            f"color: {MUTED_TEXT}; }}"
        )
    if kind == "ghost":
        return (
            f"{sel} {{ background: transparent; color: {TEXT_PRIMARY}; "
            f"border: none; border-radius: {RADIUS_LG}; padding: 6px 10px; "
            f"font-size: {FONT_SMALL}px; font-weight: 500; }} "
            f'{sel}[focusVisible="true"] {{ background: {PRIMARY_FIXED_DIM}; '
            f"color: {ON_SURFACE}; }} "
            f"{sel}:hover {{ background: {SURFACE_CONTAINER}; color: {ON_SURFACE}; }} "
            f"{sel}:disabled {{ color: {MUTED_TEXT}; }}"
        )
    if kind == "chip":
        return (
            f"{sel} {{ background: {SURFACE_CONTAINER_LOWEST}; "
            f"border: 1px solid {BORDER_CONTROL}; border-radius: {RADIUS_LG}; "
            f"padding: 6px 10px; font-size: {FONT_SMALL}px; font-weight: 600; "
            f"color: {ON_SURFACE_VARIANT}; }} "
            f'{sel}[focusVisible="true"] {{ background: {PRIMARY_FIXED_DIM}; '
            f"color: {ON_SURFACE}; }} "
            f"{sel}:hover {{ background: {SURFACE_CONTAINER_HIGH}; "
            f"border: 1px solid {PRIMARY}; }}"
        )
    if kind == "cell":
        # The compact face for a table action cell: the standard action
        # padding (7px 14px) made "Reinstall"+"Uninstall" need 294px
        # against a 240px column, clipping both buttons. Same button
        # system, cell-sized padding.
        return (
            f"{sel} {{ background: {SURFACE_CONTAINER_LOWEST}; color: {ON_SURFACE}; "
            f"border: 1px solid {BORDER_CONTROL}; border-radius: 6px; "
            f"padding: 0 8px; font-weight: 600; font-size: {FONT_SMALL}px; }} "
            f'{sel}[focusVisible="true"] {{ background: {PRIMARY_FIXED_DIM}; }} '
            f"{sel}:hover {{ background: {SURFACE_CONTAINER_HIGH}; "
            f"border: 1px solid {PRIMARY}; }} "
            f"{sel}:pressed {{ background: {SECONDARY_CONTAINER}; }} "
            f"{sel}:disabled {{ background: {MUTED_BG}; color: {MUTED_TEXT}; "
            f"border: 1px solid {MUTED_BORDER}; }}"
        )
    if kind == "link":
        # A left-aligned brand row that navigates to a section. The
        # kit's button kinds could not express it: it is a text link
        # that happens to be a button.
        return (
            f"{sel} {{ text-align: left; padding: 7px 8px; "
            f"font-size: {FONT_SMALL}px; color: {PRIMARY}; "
            f"background: transparent; border: none; border-radius: {RADIUS_LG}; }} "
            f'{sel}[focusVisible="true"] {{ background: {PRIMARY_FIXED_DIM}; '
            f"color: {ON_SURFACE}; }} "
            f"{sel}:hover {{ background: {SURFACE_CONTAINER}; }} "
            f"{sel}:disabled {{ color: {MUTED_TEXT}; }}"
        )
    if kind == "nav-active":
        return (
            f"{sel} {{ background: {SECONDARY_CONTAINER}; color: {ON_SECONDARY_FIXED}; "
            f"border: none; border-radius: {RADIUS_LG}; padding: 6px 12px; "
            f"font-weight: 600; font-size: {FONT_SMALL}px; }} "
            f'{sel}[focusVisible="true"] {{ background: {PRIMARY_FIXED_DIM}; '
            f"color: {ON_SURFACE}; }}"
        )
    # nav
    return (
        f"{sel} {{ background: transparent; color: {ON_SURFACE_VARIANT}; "
        f"border: none; border-radius: {RADIUS_LG}; padding: 6px 12px; "
        f"font-weight: 500; font-size: {FONT_SMALL}px; }} "
        f'{sel}[focusVisible="true"] {{ background: {PRIMARY_FIXED_DIM}; '
        f"color: {ON_SURFACE}; }} "
        f"{sel}:hover {{ background: {SURFACE_CONTAINER_HIGH}; color: {ON_SURFACE}; }}"
    )


def page_background_qss(*names: str) -> str:
    """Build the page background rule for a view root.

    Every view sits on the page colour. A view sets it on its own root
    object name, so a widget-level sheet cannot leak the page colour
    into a nested card. The scroll areas come with it: a scroll area
    paints its own viewport, and without the rule the area shows the
    parent's colour around a white canvas.
    """
    parts = []
    if names:
        selectors = ", ".join(f"QWidget#{name}" for name in names)
        parts.append(f"{selectors} {{ background: {BACKGROUND}; border: none; }}")
    parts.append(f"QScrollArea {{ background: {BACKGROUND}; border: none; }}")
    return " ".join(parts)


def transparent_qss(selector: str = "QWidget") -> str:
    """Build the transparent rule for one selector.

    A bare label that carries a pixmap (an icon) must not paint a face
    of its own, or it shows as a chip inside the row it sits in.
    """
    return f"{selector} {{ background: transparent; border: none; }}"


def transparent_surface_qss(*names: str) -> str:
    """Build the transparent rule for a wrapper that must not paint.

    A wrapper inside a card inherits the card's background when it does
    not paint one of its own, which shows as a seam.
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
) -> str:
    """Build a plain surface frame (a card face, a check row).

    The radius is the app-wide RADIUS_LG unless a caller has a reason
    to pass another one. ``border_style`` is "solid" everywhere except
    the empty-state card, whose dashed edge is the cue that there is
    nothing here yet.
    """
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
) -> str:
    """Build a tinted band with one edge (a card's header bar or footer).

    ``edge="bottom"`` is a header bar: it sits flush on the card's top
    edge, so it keeps the top corners and carries its border along the
    bottom. ``edge="top"`` is a flush footer: it keeps the bottom
    corners and carries its border along the top.
    """
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


def status_strip_qss(
    background: str,
    border: str,
    text_color: str,
    *,
    font_size: int = FONT_CAPTION,
    padding: str = "6px 10px",
    selector: str = "QLabel",
    weight: int | None = None,
) -> str:
    """Build a one-line status strip: a message on a card face.

    The strip carries its own face (background, edge, padding) and its
    own text colour, because a widget-level sheet replaces the app
    sheet for that widget - the label's type token would not reach it.
    """
    weight_rule = f" font-weight: {int(weight)};" if weight else ""
    return (
        f"{selector} {{ background: {background}; color: {text_color}; "
        f"border: 1px solid {border}; border-radius: {RADIUS_LG}; "
        f"padding: {padding}; font-size: {font_size}px;{weight_rule} }}"
    )


def workflow_step_qss(state: str = "todo") -> str:
    """Build the face of one step in the dataset step rail.

    The rail is guidance, not a gate: every step is clickable in every
    state, so the state shows in the colour and the weight, never in
    whether the step can be pressed.
    """
    hover = f"QPushButton#WorkflowStep:hover {{ background: {SURFACE_TINT}; border-radius: 8px; }}"
    if state == "done":
        return (
            f"QPushButton#WorkflowStep {{ color: {TEXT_SUCCESS}; font-size: 12px; "
            f"font-weight: 600; background: transparent; border: none; "
            f"padding: 3px 6px; }} {hover}"
        )
    if state == "current":
        return (
            f"QPushButton#WorkflowStep {{ color: {ACCENT_PRIMARY}; font-size: 12px; "
            f"font-weight: 700; background: {ACCENT_TINT}; "
            f"border: 1px solid {ACCENT_FOCUS_TINT}; border-radius: 8px; "
            f"padding: 2px 8px; }} "
            f"QPushButton#WorkflowStep:hover {{ background: {SURFACE_RAISED}; "
            f"border: 1px solid {ACCENT_PRIMARY}; }}"
        )
    if state == "blocked":
        # A blocked step is guidance, not a disabled control: it stays
        # clickable and stays legible (the lock mark carries the state).
        return (
            f"QPushButton#WorkflowStep {{ color: {TEXT_BLOCKED}; font-size: 12px; "
            f"background: transparent; border: none; padding: 3px 6px; }} {hover}"
        )
    return (
        f"QPushButton#WorkflowStep {{ color: {TEXT_MUTED}; font-size: 12px; "
        f"background: transparent; border: none; padding: 3px 6px; }} {hover}"
    )


def input_qss(
    selector: str,
    *,
    font_size: int = FONT_SMALL,
    family: str | None = None,
) -> str:
    """Build the standard text input sheet for one selector.

    A widget that carries its own stylesheet loses the application-level
    input rules, so the sheet repeats them - from here, so the app-level
    sheet and the local sheet cannot drift.

    ``family`` overrides the font stack (a raw payload view uses the
    mono stack).
    """
    stack = f"font-family: {family}; " if family else ""
    return (
        f"{selector} {{ background: {SURFACE_CONTAINER_LOWEST}; "
        f"border: 1px solid {BORDER_CONTROL}; border-radius: {RADIUS_LG}; "
        f"padding: 7px 10px; font-size: {font_size}px; {stack}"
        f"selection-background-color: {PRIMARY_FIXED}; }} "
        f"{selector}:focus {{ border: 1px solid {ACCENT_FOCUS_RING}; }} "
        # The placeholder is text: it carries its own colour instead of
        # inheriting the platform's (a pale grey that fails 4.5:1).
        f"{selector}::placeholder-text {{ color: {TEXT_PLACEHOLDER}; }}"
    )


def badge_qss(
    background: str,
    foreground: str,
    border: str,
    *,
    font_size: int = FONT_MICRO,
    padding: str = "0 6px",
) -> str:
    """Build a badge face from role colours.

    A badge is text on a fill: the fill, the text and the edge are three
    roles, and the badge's contract (a rounded, bordered, bold label)
    is the same everywhere.
    """
    return (
        f"QLabel {{ background: {background}; color: {foreground}; "
        f"border: 1px solid {border}; border-radius: {RADIUS_LG}; "
        f"font-size: {font_size}px; font-weight: 700; padding: {padding}; }}"
    )


def global_qss() -> str:
    """Return the app's global Qt style sheet, derived from the active palette."""
    return f"""
/* ===== Base ===== */
QWidget {{
    font-family: {FONT_FAMILY};
    color: {ON_SURFACE};
}}
QMainWindow, QStackedWidget, QScrollArea {{
    background: {BACKGROUND};
}}

/* ===== Top nav / header bar ===== */
#TopNav {{
    background: {SURFACE_CONTAINER_LOWEST};
    border-bottom: 1px solid {OUTLINE_VARIANT};
}}
{button_qss("nav-active", scope="#TopNav")}
{button_qss("nav", scope="#TopNav")}
/* Keyboard focus tint (focus-visible) — a colour change, never an outline.
   Sits before :hover/:checked so hover feedback wins when both apply. */
#TopNav QPushButton#NavActive[focusVisible="true"],
#TopNav QPushButton#NavItem[focusVisible="true"] {{
    background: {PRIMARY_FIXED_DIM};
    color: {ON_SURFACE};
}}
#TopNav QPushButton#NavItem:hover {{
    background: {SURFACE_CONTAINER_HIGH};
    color: {ON_SURFACE};
}}
/* Toggle nav buttons (Settings/Log/About) are checkable: a checked button
   reads exactly like the active location tab so "pane open" is unmistakable
   and identical for Log and Settings. */
#TopNav QPushButton#NavItem:checked {{
    background: {SECONDARY_CONTAINER};
    color: {ON_SECONDARY_FIXED};
    font-weight: 600;
}}
#TopNav QLabel#Brand {{
    font-size: 16px;
    font-weight: 700;
    color: {PRIMARY};
}}

/* ===== Cards ===== */
#Card {{
    background: {SURFACE_CONTAINER_LOWEST};
    border: {CARD_BORDER};
    border-radius: {RADIUS_LG};
}}
#MetricCard {{
    background: {SURFACE_CONTAINER_LOWEST};
    border: {CARD_BORDER};
    border-radius: {RADIUS_LG};
}}
/* The metric cards filter the queue: hover signals the affordance
   (dv-1k4). Keyboard focus already tints via [focusVisible="true"]. */
#MetricCard:hover {{
    background: {SURFACE_CONTAINER_LOW};
    border: 1px solid {PRIMARY};
}}

#SectionHeader {{
    background: {SURFACE_CONTAINER_LOWEST};
    border-bottom: 1px solid {SURFACE_CONTAINER_LOW};
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
    background: {SURFACE_CONTAINER_LOWEST};
    color: {ON_SURFACE};
    border: 1px solid {BORDER_CONTROL};
    border-radius: {RADIUS_LG};
    padding: 7px 16px;
    font-weight: 600;
    font-size: {FONT_SMALL}px;
    min-height: 18px;
}}
QDialogButtonBox QPushButton:hover {{
    background: {SURFACE_CONTAINER_HIGH};
    border-color: {PRIMARY};
}}
QDialogButtonBox QPushButton:focus {{
    outline: 2px solid {ACCENT_FOCUS_RING};
    outline-offset: 2px;
}}
{button_qss("primary", scope="QDialogButtonBox")}

/* ===== Inputs ===== */
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox {{
    background: {SURFACE_CONTAINER_LOWEST};
    border: 1px solid {BORDER_CONTROL};
    border-radius: {RADIUS_LG};
    padding: 7px 10px;
    selection-background-color: {PRIMARY_FIXED};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{
    border: 1px solid {ACCENT_FOCUS_RING};
}}
/* The placeholder is text, so it carries its own colour: the platform
   default is a pale grey that does not clear 4.5:1 on a white field. */
QLineEdit::placeholder-text, QTextEdit::placeholder-text,
QPlainTextEdit::placeholder-text {{
    color: {TEXT_PLACEHOLDER};
}}
/* Keyboard focus (Tab/arrow navigation) paints a colour tint — never an
   outline (2026-10-02 — replaces both the outline batch and its removal).
   focusVisible is set only when focus arrives from the keyboard
   (theme._install_interaction_tracking); mouse clicks set no tint. Focused inputs
   still signal focus via the border-colour change above. */
QPushButton[focusVisible="true"] {{
    background: {PRIMARY_FIXED_DIM};
    color: {ON_SURFACE};
}}
QTabBar[focusVisible="true"]::tab:selected {{
    background: {PRIMARY_FIXED_DIM};
    color: {ON_SURFACE};
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
    outline: 2px solid {ACCENT_FOCUS_RING};
    outline-offset: 2px;
}}

QLineEdit#SearchField {{
    padding-left: 32px;
    background: {SURFACE_CONTAINER_LOWEST};
    border: 1px solid {BORDER_CONTROL};
    border-radius: {RADIUS_LG};
}}
QLineEdit#SearchField:focus {{
    border: 1px solid {ACCENT_FOCUS_RING};
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
{_chevron_qss()}
/* Popup descends straight from the button: square top corners meet the
   (squared when open) button flush, 8px rounds only the bottom. Item
   metrics are pinned (not font-implied) so every menu spaces choices
   identically no matter which card hosts the combo. */
QComboBox QAbstractItemView {{
    background: {SURFACE_CONTAINER_LOWEST};
    border: 1px solid {OUTLINE_VARIANT};
    border-top-left-radius: 0px;
    border-top-right-radius: 0px;
    border-bottom-left-radius: {RADIUS_LG};
    border-bottom-right-radius: {RADIUS_LG};
    selection-background-color: {SECONDARY_CONTAINER};
    selection-color: {ON_SURFACE};
    outline: 0;
}}
QComboBox QAbstractItemView::item {{
    border: none;
    min-height: 22px;
    padding: 6px 10px;
}}
QComboBox QAbstractItemView::item:selected {{
    background: {SECONDARY_CONTAINER};
    color: {ON_SURFACE};
    border: none;
}}
/* While open, the field's bottom corners go square so they meet the
   popup flush — no notch/gap artifacts at the junction. */
QComboBox:on {{
    border-bottom-left-radius: 0px;
    border-bottom-right-radius: 0px;
}}

/* ===== Table ===== */
/* Item views mark the current cell/row with the secondary fill (the
   palette's selection role). A visible focus ring (added above) carries
   focus for keyboard users. */
QTableWidget {{
    background: {SURFACE_CONTAINER_LOWEST};
    border: none;
    gridline-color: {OUTLINE_VARIANT};
    selection-background-color: {SECONDARY_CONTAINER};
    alternate-background-color: {SURFACE_CONTAINER_LOW};
}}
QTableWidget::item {{
    padding: 10px 12px;
    border-bottom: 1px solid {SURFACE_CONTAINER_LOW};
}}
{header_section_qss()}
{selection_qss("QTableWidget")}

/* ===== Tooltips ===== */
/* Explicit light face for EVERY tooltip app-wide: without this, the global
   QWidget text color leaks into system-drawn (dark) tooltip backgrounds and
   renders black unreadable boxes (seen on dataset log + metadata table). */
QToolTip {{
    background: {SURFACE_CONTAINER_LOWEST};
    color: {ON_SURFACE};
    border: 1px solid {OUTLINE_VARIANT};
    border-radius: {RADIUS_LG};
    padding: 6px 8px;
    font-size: 12px;
}}

/* ===== Labels ===== */
/* The type scale (FONT_* above) is the only place a size is written. */
QLabel#DisplayLG {{
    font-size: {FONT_HEADLINE}px;
    font-weight: 700;
    color: {ON_SURFACE};
}}
QLabel#HeadlineLG {{
    font-size: {FONT_HEADLINE}px;
    font-weight: 600;
    color: {ON_SURFACE};
    letter-spacing: -0.2px;
}}
QLabel#HeadlineMD {{
    font-size: {FONT_TITLE}px;
    font-weight: 600;
    color: {ON_SURFACE};
}}
QLabel#BodyMD {{
    font-size: {FONT_BODY}px;
    color: {ON_SURFACE_VARIANT};
}}
QLabel#LabelMD {{
    font-size: {FONT_CAPTION}px;
    font-weight: 600;
    color: {ON_SURFACE_VARIANT};
    letter-spacing: 0.5px;
}}
QLabel#CardTitle {{
    font-size: {FONT_SECTION}px;
    font-weight: 600;
    color: {ON_SURFACE};
}}
/* The separator between two steps of the dataset step rail. */
QLabel#WorkflowSeparator {{
    font-size: 13px;
    color: {BORDER_SUBTLE};
}}
QLabel#CaptionSM {{
    font-size: {FONT_CAPTION}px;
    color: {ON_SURFACE_VARIANT};
}}
/* A field or section label on the primary text colour (11px, semibold,
   tracked) - "Decision State", "Internal Notes". */
QLabel#LabelStrongSM {{
    font-size: {FONT_CAPTION}px;
    font-weight: 600;
    color: {ON_SURFACE};
    letter-spacing: 0.5px;
}}
/* Brand-coloured text: a link-like line of copy. */
QLabel#AccentSM {{
    font-size: {FONT_SMALL}px;
    color: {PRIMARY};
}}
/* Success-coloured text: a result line ("All checks passed"). */
QLabel#SuccessSM {{
    font-size: {FONT_SMALL}px;
    color: {SUCCESS_DARK};
}}
/* Warning-coloured text: a caution line ("Large dataset"). */
QLabel#WarningSM {{
    font-size: {FONT_SMALL}px;
    color: {WARNING_DARK};
}}
/* Danger-coloured text: a validation error line. */
QLabel#DangerSM {{
    font-size: {FONT_SMALL}px;
    color: {ERROR};
}}
/* A result line at body size: a confirmation reads as unmissable at a
   glance (success pair already in the contrast contract). */
QLabel#SuccessMD {{
    font-size: {FONT_BODY}px;
    font-weight: 600;
    color: {SUCCESS_DARK};
}}
/* An error line at body size, distinct from success at the same glance. */
QLabel#DangerMD {{
    font-size: {FONT_BODY}px;
    font-weight: 600;
    color: {ERROR};
}}
/* The dashboard counter: the data it is — body size, primary ink (the
   CaptionSM it wore read as chrome). */
QLabel#ValueMD {{
    font-size: {FONT_BODY}px;
    font-weight: 600;
    color: {ON_SURFACE};
}}
QLabel#BodySM {{
    font-size: {FONT_SMALL}px;
    color: {ON_SURFACE_VARIANT};
}}
/* A loaded value (a signed-in user's checked identity): the same size
   as BodySM but on the primary text colour, so it reads as the data it
   is — an unfetched "Not checked yet" keeps BodySM (muted), a checked
   value wears ValueSM. */
QLabel#ValueSM {{
    font-size: {FONT_SMALL}px;
    color: {ON_SURFACE};
}}
/* A de-emphasised hint: the explanatory sentence under a field. */
QLabel#HintSM {{
    font-size: {FONT_SMALL}px;
    color: {ON_SECONDARY_CONTAINER};
}}
QLabel#StateMD {{
    font-size: {FONT_SMALL}px;
    font-weight: 600;
    color: {ON_SURFACE_VARIANT};
    letter-spacing: 0.5px;
}}
QLabel#MonoSM {{
    font-family: {MONO_FAMILY};
    font-size: {FONT_SMALL}px;
    color: {ON_SURFACE_VARIANT};
}}

/* ===== Status pills (QLabel with objectName) ===== */
QLabel#PillInReview {{
    background: {SECONDARY_CONTAINER};
    color: {PILL_BLUE_TEXT};
    border: 1px solid {PILL_BLUE_BORDER};
    border-radius: {RADIUS_LG};
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 700;
}}
QLabel#PillDraft {{
    background: {SURFACE_VARIANT};
    color: {ON_SURFACE_VARIANT};
    border: 1px solid {OUTLINE_VARIANT};
    border-radius: {RADIUS_LG};
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 700;
}}
QLabel#PillAuthorContacted {{
    background: {ERROR_CONTAINER};
    color: {ON_ERROR_CONTAINER};
    border: 1px solid {ERROR_OUTLINE};
    border-radius: {RADIUS_LG};
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 700;
}}
QLabel#PillReady {{
    background: {TERTIARY};
    color: {ON_PRIMARY};
    border: 1px solid {TERTIARY};
    border-radius: {RADIUS_LG};
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 700;
}}
QLabel#PillClean {{
    color: {PRIMARY};
    font-size: 12px;
    font-weight: 600;
}}
QLabel#PillFlagged {{
    color: {ERROR};
    font-size: 12px;
    font-weight: 600;
}}

/* ===== Auto-check rows ===== */
#CheckRowPass {{
    background: {SURFACE_CONTAINER};
    border: 1px solid {OUTLINE_VARIANT};
    border-radius: 8px;
}}
#CheckRowFail {{
    background: {ERROR_SURFACE};
    border: 1px solid {ERROR_OUTLINE};
    border-radius: 8px;
}}

/* ===== ScrollBar (subtle) ===== */
/* Opaque table-surface gutters: transparent tracks failed to composite and
   left the scrollbar lanes + the bottom-right meeting corner page-colored
   ("unfilled"). White matches every table/list surface in the app. */
QScrollBar:vertical {{
    background: {SURFACE_CONTAINER_LOWEST};
    width: 8px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {OUTLINE_VARIANT};
    border-radius: {RADIUS_LG};
    min-height: 24px;
}}
QScrollBar::groove:vertical {{
    background: {SURFACE_CONTAINER_LOWEST};
    border: none;
    margin: 0px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: {SURFACE_CONTAINER_LOWEST};
    height: 8px;
    margin: 0;
}}
QScrollBar::groove:horizontal {{
    background: {SURFACE_CONTAINER_LOWEST};
    border: none;
    margin: 0px;
}}
QScrollBar::handle:horizontal {{
    background: {OUTLINE_VARIANT};
    border-radius: {RADIUS_LG};
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
    color: {ON_SURFACE_VARIANT};
    padding: 8px 14px;
    border: 1px solid transparent;
    border-bottom: 2px solid transparent;
    font-size: 12px;
    font-weight: 600;
}}
QTabBar::tab:selected {{
    color: {PRIMARY};
    border-bottom: 2px solid {PRIMARY};
    background: {SURFACE_CONTAINER_LOWEST};
}}
QTabBar::tab:hover {{ color: {ON_SURFACE}; }}

/* ===== Progress ===== */
QProgressBar {{
    border: 1px solid {OUTLINE_VARIANT};
    border-radius: {RADIUS_LG};
    background: {SURFACE_CONTAINER_LOW};
    height: 6px;
}}
QProgressBar::chunk {{
    background: {PRIMARY};
    border-radius: {RADIUS_LG};
}}

/* ===== Menu bar ===== */
QMenuBar {{
    background: {SURFACE_CONTAINER_LOWEST};
    border-bottom: 1px solid {OUTLINE_VARIANT};
}}
QMenuBar::item:selected {{ background: {SURFACE_CONTAINER}; }}
QMenu {{
    background: {SURFACE_CONTAINER_LOWEST};
    border: 1px solid {OUTLINE_VARIANT};
    /* Square top corners: a menu opens directly under its button, so the
       popup connects flush into the element that opened it (same junction
       contract as QComboBox popups above). Only the bottom rounds. */
    border-top-left-radius: 0px;
    border-top-right-radius: 0px;
    border-bottom-left-radius: {RADIUS_LG};
    border-bottom-right-radius: {RADIUS_LG};
    padding: 4px;
}}
QMenu::item:selected {{ background: {SECONDARY_CONTAINER}; border-radius: {RADIUS_LG}; }}

/* ===== Status bar ===== */
QStatusBar {{
    background: {SURFACE_CONTAINER_LOWEST};
    border-top: 1px solid {OUTLINE_VARIANT};
    color: {ON_SURFACE_VARIANT};
    font-size: 11px;
}}
QStatusBar::item {{ border: none; }}

/* ===== Dock widgets (log panel renders its own card, no native title bar) ===== */
QDockWidget {{
    background: {BACKGROUND};
    border: none;
    color: {ON_SURFACE};
    titlebar-close-icon: none;
    titlebar-normal-icon: none;
}}

/* ===== Splitter ===== */
QSplitter::handle {{
    background: {OUTLINE_VARIANT};
}}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}
"""


def apply_theme(app) -> None:
    """Apply global QSS and default font."""
    from PySide6.QtGui import QFont

    # Prefer Inter if installed; fall back to Segoe UI
    font = QFont("Inter")
    if font.family() != "Inter":
        font = QFont("Segoe UI")
    # Pixel size (not point size) so Qt measures what the QSS paints:
    # tokens are px (FONT_BODY=13) while a 9pt app font is ~12px.
    font.setPixelSize(FONT_BODY)
    app.setFont(font)
    app.setStyleSheet(global_qss())
    _install_interaction_tracking(app)
    _log_active_role_table()


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


def action_button_style(primary: bool = False) -> str:
    """Build the scoped (widget-level) button sheet for a critical action.

    A widget-level stylesheet replaces the application sheet for that
    subtree, and a button face inside a styled panel does not paint
    otherwise - so critical actions carry their own copy. That copy comes
    from ``button_qss()``, the same generator the app-level rules use,
    so the two cannot drift.

    Views do not call this: they build the button with the kit's
    ``make_action_button()``.
    """
    return button_qss("primary" if primary else "secondary", selector="QPushButton")


# The badge roles: (background, text, border) per role. Every distinct
# status / curation label gets its own role so dataset-page badges scan
# at a glance, and every role is in the contrast contract (the test
# checks each role's text against its fill).
_BADGE_ROLES: dict[str, tuple[str, str, str]] = {
    "neutral": (BADGE_NEUTRAL_BG, BADGE_NEUTRAL_TEXT, BADGE_NEUTRAL_BORDER),
    "grey": (BADGE_GREY_BG, BADGE_GREY_TEXT, BADGE_GREY_BORDER),
    "blue": (BADGE_BLUE_BG, BADGE_BLUE_TEXT, BADGE_BLUE_BORDER),
    "indigo": (BADGE_INDIGO_BG, BADGE_INDIGO_TEXT, BADGE_INDIGO_BORDER),
    "green": (BADGE_GREEN_BG, BADGE_GREEN_TEXT, BADGE_GREEN_BORDER),
    "green-soft": (BADGE_GREEN_SOFT_BG, BADGE_GREEN_SOFT_TEXT, BADGE_GREEN_SOFT_BORDER),
    "red": (BADGE_RED_BG, BADGE_RED_TEXT, BADGE_RED_BORDER),
    "red-soft": (BADGE_RED_SOFT_BG, BADGE_RED_SOFT_TEXT, BADGE_RED_SOFT_BORDER),
    "orange": (BADGE_ORANGE_BG, BADGE_ORANGE_TEXT, BADGE_ORANGE_BORDER),
    "violet": (BADGE_VIOLET_BG, BADGE_VIOLET_TEXT, BADGE_VIOLET_BORDER),
    "amber": (BADGE_AMBER_BG, BADGE_AMBER_TEXT, BADGE_AMBER_BORDER),
    "teal": (BADGE_TEAL_BG, BADGE_TEAL_TEXT, BADGE_TEAL_BORDER),
    "pink": (BADGE_PINK_BG, BADGE_PINK_TEXT, BADGE_PINK_BORDER),
    "lime": (BADGE_LIME_BG, BADGE_LIME_TEXT, BADGE_LIME_BORDER),
    "sky": (BADGE_SKY_BG, BADGE_SKY_TEXT, BADGE_SKY_BORDER),
    "sand": (BADGE_SAND_BG, BADGE_SAND_TEXT, BADGE_SAND_BORDER),
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


def label_badge_colors(label: str) -> tuple[str, str, str]:
    """(background, text, border) for a status/curation label. Never raises."""
    try:
        lowered = (label or "").strip().lower()
    except Exception:
        lowered = ""
    for phrase, role in _LABEL_BADGE_ROLES:
        if phrase and phrase in lowered:
            return _BADGE_ROLES[role]
    try:
        import hashlib

        digest = hashlib.md5(lowered.encode("utf-8")).digest()
        role = _LABEL_BADGE_FALLBACK_ROLES[digest[0] % len(_LABEL_BADGE_FALLBACK_ROLES)]
        return _BADGE_ROLES[role]
    except Exception:
        return _BADGE_ROLES["teal"]


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


def _install_interaction_tracking(app) -> None:  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
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

        def _paint(w, on: bool) -> None:
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
            def eventFilter(self, obj, event):
                try:
                    t = event.type()
                    if t == QEvent.Type.Enter:
                        if isinstance(obj, QAbstractButton):
                            if obj.isEnabled():
                                obj.setCursor(Qt.CursorShape.PointingHandCursor)
                            else:
                                obj.unsetCursor()
                    elif t == QEvent.Type.KeyPress:
                        if event.key() in nav_keys:
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
            app._interaction_ref = filt
        except Exception:
            pass

        def _on_focus_changed(old, new) -> None:
            try:
                _paint(old, False)
                if state["kbd"]:
                    _paint(new, True)
            except Exception:
                pass

        app.focusChanged.connect(_on_focus_changed)
    except Exception:
        pass


def selectable_labels(root) -> None:
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


def enable_table_copy(table) -> None:
    """Ctrl+C support + extended selection for a QTableWidget (best-effort)."""
    try:
        from PySide6.QtCore import QEvent, QObject, Qt
        from PySide6.QtWidgets import QApplication, QTableWidget

        table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)

        class _CopyFilter(QObject):
            def eventFilter(self, _obj, event):
                try:
                    if event.type() == QEvent.Type.KeyPress and event.matches(Qt.Key.Key_Copy):
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
            table._copy_filter_ref = table.findChildren(_CopyFilter)[-1]
        except Exception:
            pass
    except Exception:
        pass


def enable_list_copy(list_widget) -> None:
    """Ctrl+C support for a QListWidget (copies selected rows as lines)."""
    try:
        from PySide6.QtCore import QEvent, QObject, Qt
        from PySide6.QtWidgets import QApplication

        list_widget.setSelectionMode(list_widget.ExtendedSelection)

        class _ListCopyFilter(QObject):
            def eventFilter(self, _obj, event):
                try:
                    if event.type() == QEvent.Type.KeyPress and event.matches(Qt.Key.Key_Copy):
                        items = list_widget.selectedItems()
                        if items:
                            QApplication.clipboard().setText("\n".join(i.text() for i in items))
                            return True
                except Exception:
                    pass
                return False

        list_widget.installEventFilter(_ListCopyFilter(list_widget))
        try:
            list_widget._copy_filter_ref = list_widget.findChildren(_ListCopyFilter)[-1]
        except Exception:
            pass
    except Exception:
        pass
