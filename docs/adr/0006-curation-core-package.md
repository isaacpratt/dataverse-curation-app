# ADR 0006 — The application core lives in `curation/`; `main.py` stays the entry point

- **Status:** Accepted
- **Date:** 2026-11-16

## Context

The repository had two real packages (`engine/`, `ui/`) and nine loose
root modules (`applog.py`, `config.py`, `dataverse_client.py`,
`dashboard_cache.py`, `download_manager.py`, `metadata_check.py`,
`response_draft.py`, `review_rules.py`, `storage.py`). The layering was
already real — the engine never imported the views, the views never
imported the engine — but the filesystem did not say so. A reader of the
root saw a flat pile of modules and had to know the import graph to
learn that `config.py` and `storage.py` belong to the middle layer, not
to the UI.

The 2026-11-13 code-cleaning audit made this finding R-01 and the
remediation bead `dv-hcg.24`. The `dataverse_client.py` shim (a
re-export of the `client/` package) made the ambiguity worse: two
spellings for the same code, one of them a file that looked like a
module but was a dead end.

Three constraints shaped the answer:

1. **The app is not a library.** `pyproject.toml` sets `package = false`
   (ADR 0004); nothing installs this tree, so there is no published
   import path to preserve. A compatibility shim would be dead code
   that only exists to be maintained.
2. **PyInstaller builds `main.py` in place.** Any layout that requires
   `sys.path` surgery or an installed package breaks the frozen build
   (ADR 0002 forbids `src/`).
3. **The core must stay Qt-free.** The engine is the part that has to
   run headless, in CI, and in the lite build; if the middle layer
   reaches for `PySide6`, that separation is gone.

## Decision

- **The application core lives under `curation/`.** The moved modules
  are `curation.applog`, `curation.config`, `curation.dashboard_cache`,
  `curation.download_manager`, `curation.metadata_check`,
  `curation.response_draft`, `curation.review_rules`,
  `curation.storage`, and the former `client/` package is now
  `curation.client`.
- **`main.py` stays the single entry point** for both the GUI and
  `--headless`, and the PyInstaller builds still point at it. No `src/`
  directory, no installable top-level package (ADR 0002 stands).
- **The `dataverse_client.py` shim is deleted.** Every import site was
  rewritten to the new absolute paths; no deprecated alias survives.
  The app's own test suite and views are the only consumers, and they
  are in this repository.
- **`curation/` may not import `ui/` or `PySide6`.** The dependency
  direction is machine-enforced by import-linter, alongside the
  existing engine contract: `engine/` → `curation/` → `ui/`, never
  backwards. One consequence was paid for explicitly: the table-layout
  sort direction is persisted as a plain `int` in
  `curation.storage`, and the view layer converts it to
  `Qt.SortOrder` (`ui/table_layout.py::_qt_sort_order`).
- **`engine/` and `ui/` stay at the repository root.** The engine is a
  separate, headless deliverable and the views are the app; neither
  belongs to the curation core.
- The name `curation` was chosen because it names the domain (curating
  a dataset in Dataverse) rather than a technical role such as
  `core` or `common`, which tend to become dumping grounds.

## Consequences

- The root now holds four directories (`engine/`, `curation/`, `ui/`,
  `tools/`) and two files (`main.py`, `config.example.json`); the
  layout reads the way the dependency graph actually works.
- Moving a module is a breaking change for anyone who was importing
  the app — acceptable, because there is no supported way to import it
  (ADR 0004) and no published package.
- The curation core is now provably Qt-free: the import-linter contract
  fails the build if `curation/` ever imports `ui/` or `PySide6`.
  This is what keeps the engine and the lite build honest.
- `curation/` is a package inside the repository, not an installed
  distribution: `from curation.client import DataverseClient` works
  from a clone and inside the frozen build because the whole tree
  travels with the exe.
- The type-check scope in `[tool.mypy] files` is now `["engine",
  "curation"]`, and the coverage source is `["engine", "ui",
  "curation"]` — both follow the directories.

## Links

- Beads: `dv-hcg` (audit), `dv-hcg.21` (client split), `dv-hcg.24`
  (root-module consolidation), `dv-hcg.26` (Qt-free dashboard cache),
  `dv-hcg.27` (mypy `--strict`), `dv-hcg.28` (UI typing ramp).
- `pyproject.toml` — import-linter contracts, mypy scope, coverage
  source.
- `curation/__init__.py` — the package docstring and the layer map.
- `docs/html/architecture.html` — component map.
- `docs/html/development.html` — the layout table.
- ADR 0002 — no `src/` layout; ADR 0004 — the app is not a package.
