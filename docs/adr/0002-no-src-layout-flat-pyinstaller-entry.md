# ADR 0002 — No `src/` layout; a flat root with `main.py` as the entry point

- **Status:** Accepted
- **Date:** 2026-09-15 (layout), ratified 2026-11-16

## Context

The application is packaged with PyInstaller and run as a desktop program, not
imported as a library. Its modules (`config.py`, `applog.py`, `storage.py`,
`download_manager.py`, `metadata_check.py`, `review_rules.py`) are imported by
absolute top-level name from the views, the workers and the tests
(`from config import Config`, `import applog`). A `src/` layout would require
either an installed package (the app is not one) or `sys.path` surgery in
every entry point, including the PyInstaller frozen build.

At the same time the 2026-11-13 audit found that the flat root had grown
opaque: `dataverse_client.py` had reached 2,836 lines and mixed HTTP,
parsing, caching and download logic in one module.

## Decision

- **The repository keeps a flat root layout.** No `src/` directory, no
  top-level package that must be installed to run the app.
- **`main.py` stays the single entry point** for both the GUI and
  `--headless`, and the PyInstaller builds point at it.
- **Large modules are split into packages, not moved under `src/`.**
  `dataverse_client.py` became `client/` (constants, errors, http, parsers,
  caches, downloads, client) with `dataverse_client.py` kept as a thin
  compatibility shim so every existing import still resolves.
- **Root modules stay flat until they grow:** `engine/`, `ui/`, `client/` and
  `tools/` are packages; the remaining root modules are single-purpose.
- Module-size guideline (reviewers' expectation, not a hard gate): views
  ≤ ~1,000 lines, engine modules ≤ ~1,500; exceptions carry a dated comment.

## Consequences

- Running from a clone is `uv run python main.py` — no install step, no
  `PYTHONPATH` juggling, and the frozen build has the same entry point.
- Imports in the app are absolute and stable (`from config import Config`),
  which is why moving a module is a breaking change; the `dataverse_client`
  shim is the pattern for deprecating a path.
- The root will keep accumulating small modules until the `curation/`
  consolidation bead (`dv-hcg.24`) lands; the guideline above is what keeps
  that from becoming a pile.

## Links

- Beads: `dv-hcg` (audit), `dv-hcg.21` (client split), `dv-hcg.24`
  (root-module consolidation), `dv-hcg.34` (module-size guideline).
- `AGENTS.md` — repository layout map.
- `docs/html/architecture.html` — component map.
