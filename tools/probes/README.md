# UI probes

Offscreen checks for the things pytest cannot see: a pixel colour at a
card's corner, a column geometry after a drag, a screenshot to eyeball.

Each probe prints a PASS/FAIL line per check and exits non-zero when a
check fails, so it drops straight into CI or a pre-commit hook.

## Running them

```powershell
python tools/probes/run_all.py                # every probe, one command (what CI runs)
python tools/probes/probe_queue_columns.py    # the queue's columns fill the viewport, never clip
python tools/probes/probe_manifest_columns.py  # the manifest fits, persists the user's widths, resets
python tools/probes/probe_headings.py          # every full-page heading wears the same token
python tools/probes/probe_card_corner.py       # a card's bottom-right corner stays connected
python tools/probes/probe_metadata_rows.py    # the Metadata card's rows, drawer, ghost rows and no-scrollbar rule
python tools/probes/probe_extensions_rows.py  # the Extensions rows fit their Reinstall/Uninstall buttons, and the last row is never clipped
python tools/probes/probe_auto_checks_affordances.py  # the Auto-Checks filter narrows the card, and repeated skips collapse into one row
python tools/probes/probe_disposition_rows.py # finding rows carry one disposition, a note and a header roll-up
python tools/probes/probe_preview.py          # the preview card fits 960px, with the too-large and not-staged fallbacks
python tools/probes/probe_about_updates.py    # the About updates section fits, and the restart action appears when pending
python tools/probes/probe_rail_nav.py         # one navigation map: the workflow rail stays visible folded and unfolded
python tools/probes/probe_qt_warnings.py      # a Qt message is a gate: a broken sheet is caught, the two platform ones are classified
python tools/probes/probe_review_table.py     # the review rules table: Field | Level | Check rows, no header band, no h-scroll
python tools/probes/probe_gallery_inputs.py   # the gallery's number field and value list: whole steppers, whole chips, no h-scroll
python tools/probes/probe_icon_sheet.py       # every mark is a bundled Lucide glyph, painted at 16 and 20px
python tools/probes/probe_review_selection.py # hover never paints a chosen-row band; a click chooses the row
```

`run_all.py` runs each `probe_*.py` in turn and exits non-zero when any
of them failed, so CI calls one command. The CI workflow has a second
job (`probes`) that does exactly that.

Run them from the repository root. They need no arguments and no
network.

## The temp-workspace rule

**A probe must never write to the user's `workspace/table_layout.json`.**
A probe that saves there leaves the real app with a column layout nobody
chose, and the next session opens with the wrong widths.

`tools/probes/_common.py:boot()` handles this: it points
`cfg.app.workspace` at a fresh temp directory and applies the theme. Every
probe goes through it — a new probe must do the same.

```python
from _common import Report, boot


def main() -> int:
    app, cfg = boot()  # temp workspace + themed app
    ...
    return report.finish()  # 0 when every check passed
```

Stub out anything that would reach the network. The manifest probe
replaces `DatasetDetailView._on_load_metadata` with a no-op, because the
view fetches the dataset's metadata on a timer and the probe only looks
at columns.

## The Qt-warning gate

**A Qt message is a defect until someone classifies it.** Qt does not raise
on a stylesheet it cannot parse: it logs `Could not parse stylesheet of
object QLabel(...)` once and drops the sheet, so the widget renders without
its face and the page looks almost right. That is how a badge that had one
closing brace too many (a fragment left as a plain string inside an f-string
expression) stayed invisible — the whole symptom was one line on stderr, and
nothing failed (bead `dv-bjj`).

`boot()` installs a `qInstallMessageHandler` before the `QApplication`
exists, so the first stylesheet and the first font lookup are covered:

- `Report.finish()` ends with a **no unexpected Qt warnings** check, so any
  probe that provoked an unclassified message fails.
- The handler echoes each one as `UNEXPECTED Qt message: …` on stderr, and
  `run_all.py` repeats them under a `WARNING` heading in its summary.
- Two messages are allowlisted in `_common.ALLOWED_MESSAGES`, because they
  come from the environment and not from this app:
  - `QFontDatabase: Cannot find font directory` — the offscreen plugin has
    no fontconfig. `configure_fonts()` points `QT_QPA_FONTDIR` at the
    platform's own font directory first, so geometry assertions measure real
    metrics. (`ui/tests/conftest.py` does the same for pytest.)
  - `This plugin does not support propagateSizeHints()` — the offscreen
    plugin cannot ask a window manager about a fixed size.
- Anything else fails. Adding a third pattern is a decision with a reason
  recorded next to it, never a way to quiet a run.

`probe_qt_warnings.py` proves the gate end to end: it checks the classifier,
provokes a deliberately broken sheet (printing muted for that one call, so
the probe's own output stays clean) and requires the handler to catch it,
then checks the badge path that lost its face and that a real badge sheet is
one balanced rule.

The same rule runs in `pytest`: `pyproject.toml` sets
`qt_log_level_fail = "WARNING"` with the same two `qt_log_ignore` patterns,
so a test that emits any other Qt message fails where it happened.
`ui/tests/test_kit_stylesheets.py` is the companion static check — every
sheet builder in `ui/theme.py` and the kit's chrome is built with each
branching argument, and its braces must balance with no `{TOKEN}` left
unsubstituted.

## Writing a probe

- `Report.check(ok, label, detail)` prints the line and counts a
  failure. `Report.finish()` returns the exit code.
- Build the widget, show it, and let the layout settle: `app.processEvents()`
  a few times. Geometry before the first paint is a placeholder.
- Assert on **geometry and pixels**, not on rendered text. The offscreen
  platform has no fonts, so every glyph is tofu and a text measurement
  says nothing.
- `probe_card_corner.py` saves a PNG of the card it checked under
  `reports/probes/` (the probes' shared `save_artifact()` helper does the
  same for the About-updates screenshots). That is the screenshot to eyeball
  when a probe fails.

## What each probe covers

| Probe | Contract |
|---|---|
| `probe_queue_columns.py` | The queue has no horizontal scrollbar, so the visible column widths add up to the viewport width exactly — after a column drag, a column move, a window resize and a widening again. |
| `probe_manifest_columns.py` | The file manifest fits every column to its content (Name keeps a 260px floor), the user's width survives a refresh, the saved entry carries the schema version, and the reset button restores the fitted widths and clears the entry. |
| `probe_headings.py` | Settings, About, Log and Review configuration each have exactly one `HeadlineLG` heading, no inline stylesheet, and the same 22px semibold metrics. |
| `probe_card_corner.py` | A table card's bottom-right corner has no page-coloured notch: the scrollbar lanes are transparent, so the card's border curve stays unbroken. |
| `probe_metadata_rows.py` | The Metadata card renders the Auto-Checks-style rows: the Title row carries no bar, the author drawer expands and collapses, the Not-checked filter shows its ghost rows, and the card carries no inner scroll area and no visible inner scrollbar. |
| `probe_extensions_rows.py` | The Settings → Extensions table: every row fits its Reinstall/Uninstall buttons, and the last row is not clipped by the table's own edge. |
| `probe_auto_checks_affordances.py` | The Auto-Checks card: a findings filter narrows it to Errors or Warnings and restores every row on All, and the same skipped check repeated across files collapses into one row carrying the count. |
| `probe_disposition_rows.py` | A finding row carries one disposition combo, an overflow action and a Note affordance; the pick persists to `state.db` and the header roll-up follows it. Passed rows carry no combo. |
| `probe_preview.py` | The preview card fits a 960px window, renders the CSV head inside the card, offers Open folder for a too-large file and explains a not-staged file. |
| `probe_about_updates.py` | The About pane's Updates section fits 960px with and without a downloaded update; the Restart and install action appears only when one is pending. |
| `probe_rail_nav.py` | One navigation map: the workflow rail stays visible when the sidebar folds and unfolds, the dataset log moves to the page foot, and the old nav card/menu/collapse controls stay gone. |
| `probe_qt_warnings.py` | Qt messages are a gate: the two platform messages are classified, a deliberately broken stylesheet is caught by the handler, the badge sheet is one balanced rule, and the probe's own run reports no unexpected message. |
| `probe_review_table.py` | The review rules table keeps one row shape at 1440x900 and 960x720: three columns (Field, Level, Check) with no header band, both 32px dropdowns centred 4px above and below in their 40px rows, no elided dropdown text, no reset control or saved column layout, and no horizontal scrollbar. |
| `probe_gallery_inputs.py` | The gallery's new input controls render whole at 1440px: every number-field stepper is a 32px button fully inside its field with a non-null Lucide icon, every value-list chip sits fully inside its wrapping flow with its own delete button, and the gallery never grows a horizontal scrollbar. |
| `probe_icon_sheet.py` | Every role glyph has a tile on the gallery's icon sheet and paints real ink at both 16 and 20px, the re-pointed controls carry their glyph (refresh = rotate-ccw plus label, sidebar toggle = panel-right-close/open, ring = the Lucide check), and a screenshot of the sheet is saved. |
| `probe_review_selection.py` | Hovering another field row leaves the Response pane on the clicked rule and paints no selected band under the pointer; the clicked row keeps the selected face and a real click retargets the pane. A screenshot with the other row hovered is saved. |

## The same contracts in pytest

The probes' rules also live in `ui/tests/` as pytest suites, so `pytest`
alone covers them in CI:

- `ui/tests/test_table_layout.py` — the layout controller
- `ui/tests/test_table_geometry.py` — the queue's geometry
- `ui/tests/test_page_headings.py` — the heading contract
- `ui/tests/test_type_scale.py` — the type scale
- `ui/tests/test_gallery_contract.py` — the button-sheet agreement and the gallery exhibit (promoted from `probe_buttons.py` / `probe_gallery.py`, now deleted)
- `ui/tests/test_interactions.py` — real input: Tab focus, header click, disabled ink
- `ui/tests/test_kit_exports.py` — the kit's importable surface
- `ui/tests/test_kit_stylesheets.py` — every sheet builder emits balanced braces and no unsubstituted placeholder (the `dv-bjj` gate, static side)

```powershell
python -m pytest ui/tests -q
```

Keep the probe and the test in step: the probe shows *what* broke, the
test stops it from coming back. When a probe's contract moves into
pytest, delete the probe — a rule that lives in both places drifts.

## Promote or delete

A probe is a temporary instrument. Once its contract is in
`ui/tests/`, the probe is redundant: port it in the same change and
delete the probe file. A probe that has outlived two changes without
being promoted or deleted is dead weight — promote it or remove it.
