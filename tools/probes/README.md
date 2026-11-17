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

## Writing a probe

- `Report.check(ok, label, detail)` prints the line and counts a
  failure. `Report.finish()` returns the exit code.
- Build the widget, show it, and let the layout settle: `app.processEvents()`
  a few times. Geometry before the first paint is a placeholder.
- Assert on **geometry and pixels**, not on rendered text. The offscreen
  platform has no fonts, so every glyph is tofu and a text measurement
  says nothing.
- `probe_card_corner.py` saves a PNG of the card it checked. That is the
  screenshot to eyeball when a probe fails.

## What each probe covers

| Probe | Contract |
|---|---|
| `probe_queue_columns.py` | The queue has no horizontal scrollbar, so the visible column widths add up to the viewport width exactly — after a column drag, a column move, a window resize and a widening again. |
| `probe_manifest_columns.py` | The file manifest fits every column to its content (Name keeps a 260px floor), the user's width survives a refresh, the saved entry carries the schema version, and the reset button restores the fitted widths and clears the entry. |
| `probe_headings.py` | Settings, About, Log and Review configuration each have exactly one `HeadlineLG` heading, no inline stylesheet, and the same 22px semibold metrics. |
| `probe_card_corner.py` | A table card's bottom-right corner has no page-coloured notch: the scrollbar lanes are transparent, so the card's border curve stays unbroken. |
| `probe_metadata_rows.py` | The Metadata card renders the Auto-Checks-style rows: the Title row and its required bar, the author drawer expands and collapses, the Not-checked filter shows its ghost rows, and the card carries no inner scroll area and no visible inner scrollbar. |

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
