---
name: Dataverse Docent
description: A quiet, exact instrument for curating Dataverse datasets.
colors:
  primary: "#004ccd"
  primary-hover: "#003da9"
  primary-pressed: "#002a78"
  primary-disabled: "#8aa9e8"
  tertiary: "#4142cf"
  surface: "#faf8ff"
  surface-card: "#ffffff"
  surface-tint: "#eaedff"
  surface-raised: "#e2e7ff"
  surface-row: "#f2f3ff"
  on-surface: "#131b2e"
  text-muted: "#424656"
  text-subtle: "#57657a"
  outline-variant: "#c3c6d8"
  outline: "#737687"
  control-outline: "#8b90a3"
  error: "#ba1a1a"
  error-surface: "#fff0ef"
  success: "#15803d"
  warning: "#b45309"
typography:
  headline:
    fontFamily: "Inter, 'Segoe UI', sans-serif"
    fontSize: "22px"
    fontWeight: 600
  title:
    fontFamily: "Inter, 'Segoe UI', sans-serif"
    fontSize: "16px"
    fontWeight: 600
  body:
    fontFamily: "Inter, 'Segoe UI', sans-serif"
    fontSize: "13px"
  label:
    fontFamily: "Inter, 'Segoe UI', sans-serif"
    fontSize: "11px"
    fontWeight: 600
  mono:
    fontFamily: "'JetBrains Mono', Consolas, monospace"
    fontSize: "12px"
rounded:
  lg: "8px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "20px"
  xxl: "24px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "#ffffff"
    rounded: "{rounded.lg}"
    padding: "8px 16px"
  button-secondary:
    backgroundColor: "{colors.surface-card}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.lg}"
    padding: "7px 14px"
  input:
    backgroundColor: "{colors.surface-card}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.lg}"
    padding: "7px 10px"
---

# Design System: Dataverse Docent

## Overview

**Creative North Star: "The Quiet Instrument"**

Dataverse Docent is a curation instrument, not a marketing surface. Every screen is built for scanning: a queue of datasets, a check result, a log line. The visual world is accordingly restrained — a single brand blue, a lavender-neutral tonal ramp, sentence-case headings, and one corner radius everywhere.

Density is deliberate and even: 32/36/40px controls, 11–22px type, generous page margins, no cramped rows. Motion is minimal — tree expand/collapse only — because the user's attention belongs to the data.

*Assumption (confirm or correct): the north star and voice are proposed by this document and can be re-chosen at any time.*

**Key Characteristics:**
- One accent, one radius: brand blue `#004ccd`, 8px corners on everything structural.
- Tonal surfaces, never shadows: depth comes from surface tints and 1px borders.
- Sentence case everywhere, including table headers (casing lives in the model data so Qt measures what it paints).
- States are readable without colour alone: icons (check, lock, cross) carry done/blocked/error alongside colour.

## Colors

A Material-3-like ramp: brand blue and violet accents on a lavender-neutral surface scale. Text is near-black navy on white cards; muted text is slate, never pure gray on colour.

### Primary
- **Dataverse Blue** (#004ccd): the one command colour — primary buttons, links, the progress fill, selected tabs. Inks on white clear 4.5:1.
- **Pressed Blue** (#002a78): pressed primary buttons; hover darkens to `#003da9`.
- **Disabled Blue** (#8aa9e8): disabled primary faces, drawn with the dark primary text colour (never white at 2.35:1).

### Secondary
- **Curation Violet** (#4142cf): tertiary accent — ready-state pills and tertiary icons.

### Neutral
- **Page** (#faf8ff): the background behind everything.
- **Card** (#ffffff): cards, tables, sheets, inputs, tooltips.
- **Tint** (#eaedff) / **Raised** (#e2e7ff) / **Row** (#f2f3ff): header bands, hover faces, alternating rows.
- **Ink** (#131b2e) / **Muted** (#424656) / **Subtle** (#57657a): primary text, captions and hints, field placeholders.
- **Edge** (#c3c6d8): card and section borders.
- **Control edge** (#8b90a3): input and button boundaries — held to 3:1 on white, heavier than the decorative card edge.

### State
- **Error** (#ba1a1a) on **Error surface** (#fff0ef) with a `#ffb4ab` edge: fail rows, author-contacted pills.
- **Success green** (#15803d text / `#16a34a` graphic): pass rows, done steps, success copy.
- **Warning amber** (`#b45309` text / `#d97706` graphic): caution lines, large-download flags.
- Sixteen badge roles (neutral, blue, green, red, orange, violet, amber, teal, pink, lime, sky, sand, indigo, grey, soft green, soft red) give every curation label a scan-able fill; each role's text clears its fill in the contrast contract.

### Named Rules
**The One Accent Rule.** The brand blue is used for commands and selection, never decoration. Its rarity is the point.
**The Contrast Contract Rule.** Every text/surface pairing the app paints is a test (`CONTRAST_PAIRS` in `ui/theme.py`); a palette change that breaks legibility fails the build.

## Typography

**Display Font:** Inter (with 'Segoe UI' fallback) — 700 weight, used for metric values.
**Body Font:** Inter — 13px regular/medium for copy, table cells, and values.
**Label/Mono Font:** JetBrains Mono (Consolas fallback) for the log, identifiers, and raw payloads.

**Character:** A working sans with obvious weight steps: bold values, semibold labels, regular body. No display face, no italics for emphasis.

### Hierarchy
- **Display** (700, 22px): metric-card values only.
- **Headline** (600, 22px): page titles (Dataset, Settings, Review configuration…).
- **Title** (600, 16px): section headings inside a page.
- **Section** (600, 15px): card titles.
- **Body** (400, 13px): row text, values, descriptions.
- **Small** (400, 12px): secondary values, badges (12px variant), workflow steps.
- **Label** (600, 11px): field/metric labels (strong, primary ink) and muted section labels; table headers (600, 11px, muted).
- **Micro** (700, 10px): log-level badges and compact pills.

### Named Rules
**The One Scale Rule.** All sizes come from `FONT_*` in `ui/theme.py`. No view writes a raw `font-size:` (enforced by `test_no_raw_font_sizes_outside_the_theme`).

## Layout

A single-window desktop app with a top nav and stacked pages. Page margins are 24px; card header/body insets are 16px horizontal and 12px vertical; card bodies space children 8px apart with 12px header spacing. A card header is two rows: the title row carries only the title, its (i) tooltip and a summary (e.g. "4/13 fields complete"); every tool — search, filter combos, reset, actions — sits on one tools row below it, made of 36px fields and buttons with 8px gaps. Tables fill their card edge-to-edge (flush corners, no inner frame). The dataset page splits into a main column and a right rail (Sections, Dataset log).

Window behaviour: the app is resize-safe from narrow to wide — columns fit to content with a minimum of 48px, headers elide with tooltips carrying the full title, and long labels elide rather than widening the layout.

## Elevation & Depth

No shadows, anywhere. Depth is tonal: the page (`#faf8ff`) sits below cards (`#ffffff`), which sit below header bands and raised panels (`#eaedff`–`#e2e7ff`). Separation is a 1px `outline-variant` border, never a drop shadow. The focus ring is a 2px high-contrast outline with offset — the one non-flat gesture in the system, reserved for keyboard focus.

## Shapes

One radius: 8px on cards, inputs, buttons, badges, menus, and table corners. Square corners are kept only where a surface joins another (combo popup seam, tab pane seam, flush table headers inside cards) so the junction reads as one face. Cards carry a 1px `outline-variant` border; interactive controls carry the heavier 3:1 `control-outline`.

## Components

Built through the kit in `ui/widgets.py`; styled through mixins in `ui/theme.py`. A view never paints for itself (enforced by `ui/tests/test_theme_conformance.py`).

### Buttons
- **Shape:** 8px radius; heights 32 (sm), 36 (md), 40 (lg) — every target clears the 24px minimum.
- **Primary:** `#004ccd` fill, white 600 12px text; hover `#003da9`, pressed `#002a78`, disabled `#8aa9e8` with dark ink.
- **Secondary:** white fill, 1px `control-outline`, ink text; hover tints `#e2e7ff` with a brand edge; pressed `#d5e3fc`.
- **Ghost / Link / Nav:** transparent until hover; nav-active and checked toggle panes wear the secondary fill `#d5e3fc`.
- **Focus:** keyboard arrival paints a `#b4c5ff` tint plus a 2px `#004ccd` offset outline; mouse clicks never do.

### Chips and Badges
- **Status badges:** 700 weight, role colours per curation label (see Colors). Fill, text, and 1px edge are three roles; each clears contrast.
- **Filter chips:** secondary-button face; checked state draws the secondary fill.
- **Dataset chips:** a 32px split chip — label half opens, × half closes — one shared border and radius; long titles elide with tooltips.

### Cards / Containers
- **Corner style:** 8px, `outline-variant` 1px border, white face.
- **Header:** tinted band (`--surface-container-low` …) with a 15px semibold title, an 8px underline rule, and a (i) help affordance whose explanation lives in the tooltip.
- **Body:** 16px/12px insets, 8px child spacing; flush tables/trees bleed edge-to-edge.

### Inputs / Fields
- **Style:** white fill, 1px `control-outline`, 8px radius, 7px/10px padding; placeholders are real text at 4.5:1 (never the platform pale grey).
- **Focus:** 1px brand border + 2px offset focus ring.
- **Search/combo:** 36px tall; combos are owner-drawn with a Lucide chevron, square top corners meeting the field flush; wheel over an unfocused combo never changes its value.
- **Labels:** 11px semibold on primary ink (`LabelStrongSM`); loaded values are 12px on primary ink (`ValueSM`); unfetched placeholders stay muted (`BodySM`) so "not checked yet" never impersonates data.

### Tables & Trees
- **Headers:** sentence case, 11px 600 muted on `#eaedff`, 1px bottom rule; sort state by weight, never by re-casing.
- **Rows:** 40px default (tables), 30px (trees), row selection with the secondary fill; trees indent 18px with Lucide branch marks.
- **Empty states:** a dashed empty-state card names the state and the next action ("No datasets loaded yet — add an API key…").

### Navigation & Workflow
- **Top nav:** white bar with a 1px bottom rule; active location wears the secondary fill; Log/Settings toggles read identically when their pane is open.
- **Workflow rail:** six clickable steps (Metadata → Respond); done steps lead with a green Lucide check, blocked steps with a lock, the current step with a brand tint; connectors are `›` in the edge colour. Steps are guidance, never gates — every step is pressable in every state.

### Log
Lnav-style text colouring, text-only legend chips (ERROR / WARN / INFO · DEBUG), monospaced body with deterministic identifier colours by hash — never random per run.

## Do's and Don'ts

### Do:
- **Do** name a colour by its role (muted text, card surface) and let the theme resolve it — a palette change is then a one-line edit.
- **Do** keep the stored header label identical to the painted label (sentence case in the data) so Qt measures what it draws.
- **Do** give every interactive control a ≥32px target, an accessible name, and a keyboard-focus tint.
- **Do** carry state by icon as well as colour (check = done, lock = blocked, × = fail) so it survives greyscale and colour-blind reading.

### Don't:
- **Don't** write a stylesheet, a hex literal, or a raw input widget in a view — ask the theme or the kit (the build's static guards refuse it).
- **Don't** put white text on the disabled blue `#8aa9e8` (2.35:1); disabled primaries pair the face with the dark ink colour.
- **Don't** add a second radius, a shadow, or a new font size without going through the tokens in `ui/theme.py`.
- **Don't** let a placeholder ("Not checked yet", "Search…") wear the same colour as loaded data.
