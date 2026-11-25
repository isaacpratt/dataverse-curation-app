# Golden screenshots

Golden images catch visual drift that geometry assertions cannot: a colour
token repainted wrongly, a border lost, a card pushed a few pixels. Agents
**propose** candidates; only the human **blesses** baselines. That boundary
is the point of the gate — an agent must never silently accept its own
output as truth.

## Run

```bash
# Propose candidates (native Windows platform, not offscreen):
QT_QPA_PLATFORM=windows uv run pytest -m goldens

# Human blessing — regenerates the named baseline(s) and the environment pin:
uv run poe golden-update
```

The default suite deselects `goldens` (`-m 'not samples and not goldens'` in
`pyproject.toml`): baseline images are machine-specific and the offscreen
CI renderer substitutes glyphs, so a CI golden would fail for the wrong
reason. `baseline.meta` pins Python, PySide6, Qt, OS build and the Qt
platform; any mismatch fails loudly rather than producing a meaningless
diff.

## Tolerance table

| Check | Default | Per-image override |
| --- | --- | --- |
| Pixels differing by more than 12/255 | ≤ 0.5% | `TOLERANCES[name]` in `golden/__init__.py` |
| Any single channel differing by more than 64/255 | fail | not overridable |
| Image size mismatch | fail | not overridable |

A failing run prints the changed percentage, maximum channel delta and
bounding box **before** writing anything; `candidates/<name>.png` is the
image to compare against `baseline/<name>.png`.

## Bless procedure

1. Run the goldens with `QT_QPA_PLATFORM=windows` on the pinned machine.
2. Inspect `candidates/` next to `baseline/`; confirm every change is intended.
3. Run `uv run poe golden-update` (blesses all candidates and rewrites
   `baseline.meta`), then commit the changed PNGs and meta together.
4. Re-run `QT_QPA_PLATFORM=windows uv run pytest -m goldens`; two consecutive
   runs on unchanged code must pass.

## Captures

One image per case: dashboard empty and seeded, Settings, About, Log,
Review configuration, gallery, the seeded dataset detail (header, metadata,
file manifest and auto-checks), and the kit state sheet (disabled, hover,
focus and selected). Conditional states cannot be inferred from a single
screenshot, so each state is rendered deliberately in its own case.
