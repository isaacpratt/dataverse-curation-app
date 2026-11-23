# ADR 0002 — No `src/` layout; a flat root with `main.py` as the entry point

- **Status:** Accepted
- **Date:** 2026-09-15 (layout), ratified 2026-11-16

## Context

The application is packaged with PyInstaller and run as a desktop program, not
imported as a library. Its modules (`config.py`, `applog.py`, `storage.py`,
`download_manager.py`, `metadata_check.py`, `review_rules.py`) were imported by
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
  `dashboard_cache.py` (the Qt-free dashboard cache helpers) is one of them:
  it is pure data handling that the engine tests need without the view
  layer, so it sits at the root beside `storage.py` and `applog.py`
  (dv-hcg.26). The `curation/` consolidation bead (dv-hcg.24) will decide
  where it lands.
- Module-size guideline (reviewers' expectation, not a hard gate): views
  ≤ ~1,000 lines, engine modules ≤ ~1,500; exceptions carry a dated comment.

## Amendment — 2026-11-16 (ADR 0006)

The `curation/` consolidation (dv-hcg.24) landed and resolved the open
question above:

- The loose root modules and the `client/` package now live under
  **`curation/`** — the middle layer the dependency graph already had.
- The `dataverse_client.py` compatibility shim is **deleted**. The app is
  not a library and is never installed (ADR 0004), so the old absolute
  paths were rewritten in place rather than kept alive by a re-export.
- "Flat root" above is now read as "**no `src/` layout, no installable
  package**", not as "every module is a loose file at the top level".
  The root holds `engine/`, `curation/`, `ui/`, `tools/`, `main.py` and
  `config.example.json` — and `main.py` is still the single entry point.

The `client/` package row in the decision list above is historical: it
became `curation/client/`.

## Consequences

- Running from a clone is `uv run python main.py` — no install step, no
  `PYTHONPATH` juggling, and the frozen build has the same entry point.
- Imports in the app are absolute and stable (`from curation.config import
  Config`), which is why moving a module is a breaking change; since the
  app is not a library, the fix is to rewrite the import sites rather
  than to keep a shim (ADR 0006).
- The root no longer accumulates small modules: they belong to
  `curation/` (the core), `engine/` (the checks) or `ui/` (the views),
  and the import-linter contracts keep those layers apart.

## Links

- Beads: `dv-hcg` (audit), `dv-hcg.21` (client split), `dv-hcg.24`
  (root-module consolidation), `dv-hcg.26` (Qt-free dashboard cache),
  `dv-hcg.34` (module-size guideline).
- `AGENTS.md` — repository layout map.
- `docs/explanation/architecture.md` — component map.
- ADR 0006 — the curation core package.
