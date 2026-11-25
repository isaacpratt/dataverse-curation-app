---
page_type: explanation
tgdp_template: Concept       # Concept | Explanation
audience: developer          # curator | developer | contributor | all
---
# Why the UI has so many rules

The interface conventions look numerous until you see them as answers to the same problem: Qt is permissive, and almost every visual defect this app had was Qt behaving exactly as documented. A view that is free to paint for itself produces a button that loses its face, a table that overwrites your column widths or a card with a white notch in its rounded corner. The rules remove that freedom and make the important properties machine-checkable. This page explains the reasoning; it is not a checklist of steps for building a view.

## One kit, and a palette beneath it

The shared kit in `ui/widgets.py` and the theme in `ui/theme.py` are the only sources of the app's look. A view composes components; it does not invent a stylesheet or construct raw inputs. That single decision explains most of the rest: with one place that builds buttons, lists, badges and tables, there is one place to fix a bug and one place to change a look.

Under the kit sits the [three-layer contract](architecture.md#ui-layering-palette-role-component). The palette names what a colour is, the role names what it is for, and the component is what the user touches. Only the theme and the kit may name a palette entry. A view asks for `SURFACE_CARD` or `TEXT_DANGER`; which palette colour that resolves to is the theme's business. A theme swap is therefore a table edit rather than a hunt through views. Hardcoded hex outside `ui/theme.py` fails `test_theme_tokens.py`, and a view that names a raw palette entry, paints its own stylesheet, builds a raw input or hand-writes a button sheet fails `test_theme_conformance.py`. The guards parse source with `ast`, so they are cheap, exact and need no window.

The contrast contract is the same idea applied to legibility. The pairs the app actually paints are declared in `theme.CONTRAST_PAIRS` and `theme.BADGE_CONTRAST_PAIRS` with the ratio each must clear — 4.5:1 for text, 3:1 for graphics and 3:1 even for disabled controls, which are exempt from WCAG 1.4.3 but should still read as present. A test reads the table, so a palette change that breaks legibility fails the build. The contract earned its keep by catching a disabled primary button at 2.35:1, muted text at 2.54:1 and a green badge at 3.30:1.

There is one button system because two copies of a button rule drift. `theme.button_qss(kind)` generates the app-level rule and the widget-level copy from the same function; the kit's `make_action_button()` carries the scoped copy, because a widget-level stylesheet replaces the application sheet for that subtree and a button face inside a styled panel does not paint otherwise. The kinds — primary, secondary, ghost, chip, cell, link and the nav variants — each express a level of emphasis, not a colour. The `cell` kind exists because the normal action padding made two buttons need 294 pixels in a 240-pixel column; it is the same system at cell width.

## Icons and text are catalogued too

Every mark that stands for an action, a state or a direction is a bundled Lucide asset, tinted from a theme role and named through `ui.icons.ICON_ROLES`. A role says what the mark is for — refresh, back, sidebar hidden or shown, more — so two refresh buttons cannot land on different glyphs. A text character such as ×, ⋯, ✓ or ▸ is never a stand-in, and neither is a hand-drawn path. Three kit shapes cover the uses: an icon-only button, a glyph-plus-label button and the app's single refresh button. An unknown icon name warns once instead of returning a silent null icon, and an inventory test fails on an unresolved name or a button whose whole label is a glyph. Two exceptions are deliberate: the window caption buttons, which use platform artwork so they match the real title bar, and the column-drag affordance, which stays the platform's resize cursor rather than becoming permanent chrome on every header.

User-visible copy lives in `ui/assets/strings.json` and is rendered through `ui/i18n.py`. A missing key returns the key itself, so a typo degrades visibly instead of crashing a screen. The string test fails when the catalogue and code drift — unknown keys, missing placeholders, prose hard-coded in the interface layer, and orphan entries that no screen can show. Keys must be static at the call site so the test can see them; a small lookup table is better than an f-string. The engine and the report contract are deliberately outside the catalogue: check messages and report fields are data for other tools, not interface copy. A few strings that look like copy — state tokens, Dataverse state names, cache-slot sentinels — are machine contracts and stay in code, because translating them would change behaviour.

## One table, one layout owner

`AppTable`, `AppTree` and `AppTreeWidget` are the three table shapes, and each header has one `TableLayout` controller that owns the construction snapshot, restore, persistence and reset. The reason is that a programmatic resize and a user gesture are indistinguishable to Qt's signals. Wiring `sectionResized` straight to a save means a content fit or a window resize rewrites the layout the user chose — which is exactly how the file manifest once lost its widths on every refresh. A change counts as a gesture only when the user could have caused it, and the app's own changes run inside `layout.suppressed()`.

Only user gestures are persisted, in versioned `workspace/table_layout.json` entries. An entry written for a different column shape, or a newer schema than the app understands, is ignored rather than half-applied.

## Qt pitfalls as hard-won rationale

Most of the rules above exist because of a specific Qt behaviour. Each paragraph below pairs what Qt does with what the app does instead.

**A widget stylesheet shadows the application one.** Setting a stylesheet on a widget replaces the application stylesheet for that subtree, so the app's header rules stop applying inside a table that has its own sheet. The app repeats the shared rules from the theme's `header_section_qss()` and `scrollbar_lane_qss()` generators, keeping one source so the two sheets cannot drift.

**`sectionResized` fires before the new size lands.** Reading `header.sectionSize(i)` inside the handler returns the old value, persisting stale widths and drifting the last label off-centre. The fit is deferred with `QTimer.singleShot(0, …)`.

**Children are not clipped to a parent's border radius.** A table flush inside a card paints its own square corners, leaving a notch at the rounded edge. The app paints square top caps, which meet the card's top bar, and gives the table the card's bottom radius itself. The same reasoning keeps scrollbar lanes transparent: a filled lane inherits the page colour and paints a white notch over the card's corner.

**An ancestor's background bleeds through a transparent widget.** A styled ancestor can make a table body render page-coloured instead of white. Flush tables set their background explicitly in their own sheet.

**Qt derives cell-widget geometry from the item's content box.** With a stylesheet active, the item padding shrinks every action cell and clips the buttons inside it. Action cells zero the vertical padding. Combo popup rows have a similar problem: they are sized by the delegate, not by the QSS item rule, so the kit installs a row delegate with a fixed minimum height that holds at both 100% and scaled DPI.

**Some API surfaces are missing or surprising.** `QHeaderView.lastVisibleSection()` does not exist in PySide6, so the header is walked through its visual range instead. A click on the header widget never reaches the header, because it is a `QAbstractItemView` whose mouse handling lives on the viewport; tests and real clicks must target the viewport. The native sort indicator paints at section top-centre under the header QSS and no stylesheet positions it, so `SortArrowHeaderView` draws its own arrow as a transparent child-label overlay while keeping the stock sort state.

**A label that has its own stylesheet has left the type scale.** The label's own sheet wins for the properties it sets. The app sets the object name to a token and leaves the stylesheet empty, which is what the kit builders do; a label whose text changes at runtime changes its token and re-polishes. All sizes come from `ui/theme.py`'s four `FONT_*` constants, with a 12px floor for the smallest text; a raw `font-size: Npx` in any module under `ui/` fails the type-scale test. The one computed size is the progress-ring percentage (`ui/ring.py`), which must fit a circle whose diameter is decided at runtime; the same test pins it as the only `setPixelSize()` call outside the theme and keeps its 6px floor.

**The three faces are bundled, not assumed.** `ui/assets/fonts/` ships Inter (12/13px body), Fraunces (16/22px display) and JetBrains Mono (identifiers, raw payloads), each with its OFL licence. `theme.register_fonts()` loads them through `QFontDatabase.addApplicationFont()` before the app font and stylesheet are set; `apply_theme()` checks `QFontDatabase.families()`, not `QFont.family()`, because Qt returns a requested name even when the family is absent. The CSS stacks keep system fallbacks if a file fails to load, and `ui/tests/test_fonts.py` asserts what each token actually resolves to.

**Mono is opt-in, not a default.** The log, tabular-preview and gallery read-only views render in Inter, as do the dashboard's PID/date cells (they used a raw `QFont` that bypassed the QSS stack entirely) and the diagnostics label. The one deliberate mono field is the raw metadata view, which passes `mono=True` to `make_multiline_input()`. `ui/tests/test_fonts.py` scans `ui/` so a view cannot quietly reintroduce a system-dependent mono face.

**The offscreen platform has no fonts.** Every glyph would render as tofu, so text measurement says nothing about layout. Pixel-and-geometry probes assert section sizes, viewport widths and corner colours rather than rendered text, and point the offscreen plugin at the platform fonts so the geometry it does measure is real.

**Qt does not raise on a stylesheet it cannot parse.** It logs one line and drops the sheet, so a widget renders without its face and the page looks almost right. That is how a badge with one brace too many stayed invisible for weeks. Every Qt message is now recorded and must be one of exactly two classified platform messages; an unclassified message fails its probe and its pytest, and a probe deliberately provokes a broken sheet to prove the gate works. Adding a third allowlist entry is a decision with a reason, never a way to quiet a run.

**A QThread destroyed while running aborts the process.** Qt prints a warning and calls `abort()`. A worker parented to a widget dies with that widget, so quitting during a scan could kill the app. Every worker registers with `ui/workers.py`, checks for interruption between steps, and is adopted before a view is discarded; hooks cover both a clean quit and an unclean process end.

An earlier mismatch between the QFont point size and the pixel sizes painted by QSS was fixed by setting `font.setPixelSize(FONT_BODY)` in `apply_theme()`, so Qt measures what the stylesheet paints. The rule it established remains: text sizes come from the theme's pixel tokens, never from an ad-hoc point size in a view.

## The gallery is the contract, executable

`ui/gallery.py` puts every kit component on one page: the type scale, role swatches, button kinds and sizes, badge roles, standard inputs, containers and data components. It is the visual contract in executable form — when the theme changes, the gallery changes with it. It is also a view, so it obeys the same rules as every other one, and it is the first place to look when a component seems wrong because it shows that component beside all the others.

Adding a component means adding it to the kit and then to the gallery. The gallery contract test checks that every kind is shown and that every button wears a theme object name — the gallery may not exhibit a button the app cannot produce. Pixel probes then check the rendered ink and fit of the controls at real widths.

## Why dark mode is a table edit

Dark mode ships with the app. **Settings → General** offers **Light**, **Dark** and **Auto (follow system)**, with an auto-switch checkbox for following the operating system; the component gallery can show both themes side by side. The role layer is why this was a selection rather than a re-skin: the palette stays a palette, the roles decide what each palette entry is for, and `DARK_ROLE_TABLE` decides which entry each role points at in the dark theme. Both tables declare the same role names, and the light mappings are pinned so they cannot move by accident.

The same layering governs the rest. The contrast floors do not change, but `CONTRAST_PAIRS_DARK` and `BADGE_CONTRAST_PAIRS_DARK` redeclare the pairs and are checked by the same test, so an illegible dark combination fails the build. QSS that hardcoded a surface had to be re-pointed at roles — that was the real work. Painted icons are tinted from roles, and dark variants of the app mark and taskbar icon ship for dark surfaces. Doing this before the role layer existed would have meant rewriting every view.
