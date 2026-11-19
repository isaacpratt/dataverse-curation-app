# Changelog

All notable changes to this project are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed (UI)

- **Check boxes look like check boxes** — the kit's indicator was a 16px box with a half-height radius filled with the accent colour when checked: a solid blue circle, the visual language of a radio button, with no check mark at all. It is now a 16px rounded square (4px corners, `BORDER_CONTROL` edge) carrying the Lucide `check` glyph in `ON_PRIMARY` when checked, with distinct unchecked, checked, disabled and hover faces. `make_checkbox()` keeps its signature (it returns the kit's `AppCheckBox`, still a `QCheckBox`), every existing call site is unchanged, and `ui/tests/test_checkbox_face.py` checks the rendered pixels at 2x.

### Changed (layout)

- **The application core moved to `curation/`** — the loose root modules (`applog`, `config`, `dashboard_cache`, `download_manager`, `metadata_check`, `response_draft`, `review_rules`, `storage`) and the `client/` package now live under `curation/`, which is the middle layer the dependency graph already had (ADR 0006). `main.py` stays the single entry point for both the GUI and `--headless`, and the PyInstaller builds are unchanged. The `dataverse_client.py` compatibility shim is gone — the app is not a library, so the old absolute paths were rewritten in place instead of being kept alive by a re-export. A new import-linter contract keeps `curation/` free of `ui/` and `PySide6`: the table-layout sort direction is persisted as a plain `int` in `curation.storage` and converted to `Qt.SortOrder` in `ui/table_layout.py`.
- **The dataset detail page was split into sections** — `ui/dataset_detail.py` (4,419 lines, the largest module in the repo) is now the `ui/dataset/` package: `page.py` is the facade (layout, splitter, signals) over ten section mixins (metadata, metadata loading, checks, files, versions, the dataset log, the response draft, the actions, the header, the workflow rail), all sharing one typed contract in `state.py` (`DetailState`: the attributes the page owns, the page's signals, and the calls the sections make across each other) and the shared formatting helpers in `helpers.py`. The facade is imported as `from ui.dataset import DatasetDetailView`; the rendering and the copy are unchanged. A new test pins the split: every cross-section call the contract declares must be implemented by a section, and no section module may grow past 1,000 lines.
- **Signing policy decided** — distributed Windows builds will be signed through **SignPath Foundation**, a managed signing service that signs open-source Windows software for free: no institutional certificate to buy or hold, and no key material in the repository. The signing step is wired in `dv-4t6.6` and skips cleanly when the `SIGNPATH_*` secrets are absent, so forks and local builds are unaffected. The first releases stay unsigned with a published `SHA256SUMS.txt`, a documented SmartScreen click-through in the user guide, and a checksum check. The policy, the cert source and the renewal story are recorded in `SECURITY.md` and linked from the release workflow.

### Changed (tooling)

- **mypy `--strict` on the engine contract** — the scope in `[tool.mypy] files` (`engine/`, `curation/`, plus the engine test suite) is now checked under `--strict`, with no per-module ignore list. 44 strict-subset errors were fixed by annotating the engine, the client and the core services.
- **The UI layer is type-checked too** — `ui/` and `main.py` joined `[tool.mypy] files` (dv-hcg.28, ADR 0007): 308 mypy errors in the view layer are now 0. The ramp rewrote 252 forgiveness-mode enum aliases to their scoped PySide6 names (`Qt.CursorShape.PointingHandCursor`, `Qt.ItemDataRole.UserRole`, `QHeaderView.ResizeMode.Interactive`, …) and fixed the shape bugs the census listed: an `int(QSize)` that was never a width, a mixin calling methods it never declared, an attribute annotated in one place and redefined in another, `itemFromIndex` called on `QAbstractItemModel`, and functions used for their return value. `ui.*` is checked under a documented relaxation of `--strict` (the "annotate everything" rules off, `check_untyped_defs` and every shape check on) because PySide6 ships no usable stubs for the widget tree; `main.py` keeps the full strict settings.
- **Dependency direction is machine-enforced** — `poe contracts` (import-linter, also in `poe check` and CI) forbids `engine/` → `ui/`/`PySide6`, `curation/` → `ui/`/`PySide6` and `tools/` → `ui/`. The engine contract has no exceptions: the dashboard cache helpers the engine tests used to borrow from `ui/dashboard.py` moved to the Qt-free `curation/dashboard_cache.py`, so `engine/tests/` no longer imports the view layer and joined the strict mypy gate.

## [0.2.0] - 2026-11-16

### Changed (tooling)

- **uv is the package manager** — `uv.lock` is the source of truth; `uv sync --group dev` creates the environment; the committed lock is enforced by `uv lock --check` in CI and pre-commit; `requirements.txt` is gone; the app builds as `uv sync` without producing a wheel (`[tool.uv] package = false`); PEP 639 metadata (SPDX `MIT`, repository/docs/issues URLs, authors, classifiers); Python floor aligned to 3.11 (`.python-version`, CI).
- **poe (poethepoet) is the task runner** — `poe check` (lint + format check + typecheck + tests), plus `poe fmt`, `format-check`, `audit`, `hooks`, `license-report`, `sbom`, `docs-links`, `probes`; cross-platform task definitions.
- **pre-commit is the local gate** — check-only hooks: JSON/TOML/YAML validation, large-file/case-conflict/merge-conflict/Windows-illegal-names, private-key detection, whitespace/EOF fixers, codespell (Canadian English), `uv lock --check`, ruff, actionlint, and a `forbid-config-json` guard aimed squarely at the token file.
- **Ruff format is adopted** (whole tree, enforced in CI/pre-commit/`poe check`); ruff rule set extended (pep8-naming, ruff-specific, simplify, pytest-style, mccabe `max-complexity=12`, import hygiene); docstring rules (D103) active.
- **CI** runs on windows-latest with SHA-pinned actions: pre-commit, ruff, engine coverage gate (75%), `compileall`, headless smoke, UI probes, workflow lint, and an OSV dependency audit of the locked set (failing). Dependabot opens grouped weekly update PRs.
- **pytest** runs with `--strict-markers` and `xfail_strict`; the global `RuntimeWarning` suppression was removed (there was nothing to hide).
- **Coverage gates**: repo total ≥ 65 (actual 68.9%, branch), engine ≥ 75 (actual 77.3%).

### Changed (app)

- **Token storage**: the API token now lives in the OS credential store (Windows Credential Manager via `keyring`, keyed by instance base URL); `config.json` keeps only `api_token_source: "keyring"` with a blank token. Load precedence is env > keyring > plaintext; legacy plaintext tokens migrate on first save; clearing the token in Settings deletes the credential store entry; log redaction now also masks `Authorization: Bearer`, `X-Dataverse-key`, `Api-Key` and `password`/`secret=` patterns; log line format gained `WARN`.
- **Configuration**: `config.json` gains `version: 1`; schema validation reports the exact field on bad shapes (values, types, sections) instead of silently coercing; writes only canonical keys (legacy `collection_alias`/`subtree` are read-only migration inputs); env overrides (`DATAVERSE_BASE_URL` — https + host required, `DATAVERSE_API_TOKEN`, `DATAVERSE_COLLECTION`, `DATAVERSE_WORKSPACE`) are validated/normalised; docs carry a one-table env reference and an on-disk artefacts reference.
- **client/ package**: `dataverse_client.py` (2,836 lines) decomposed into `client/` (`constants`, `errors`, `http`, `parsers` (pure payload parsing), `caches`, `downloads` (`_DownloadsMixin`), `client` (session/discovery)); `dataverse_client.py` remains a compatibility shim — every existing import works unchanged.
- **Agent hygiene**: `AGENTS.md` is canonical (`CLAUDE.md` points at it; stale "454 tests" copy removed); `.editorconfig` added; root module-size guideline; binary assets untouched under `.gitattributes` (`uv.lock` is `-diff linguist-generated`; `config.json` is `-diff -text`).
- **Docs**: README rewritten (quick start, doc index, license); `SECURITY.md` added (token handling, reporting, dependency/CVE policy, threat model); `development.html` gains an on-disk artefacts map, an environment-variables table, corrected coverage numbers and the whole-tree format gate; `docs/html` gained an offline link check (advisory in CI).

### Fixed

- `storage.py` datetime: `timezone.utc` → `UTC` alias (py311).
- `poe typecheck` was red (pre-existing mypy errors); the engine contract gate is green again.
- Pillow 13 compatibility (surfaced during the mypy run).

## [0.1.0] - 2026-10 (untagged initial packaged builds)

### Added

- Desktop GUI (PySide6): dashboard queue, dataset detail, Settings, About, Log, Review configuration panes.
- Engine: 22 format checks ported from `CUR_Res_CurationTools` (MIT) — CSV, XLSX, SAV, DTA, SAS7BDAT, JSON, XML, IPYNB, SQLite, HDF5, NetCDF, GPKG, TIFF, images, PDF, text/code, containers, FASTQ, Secrets, Access checks; dispatcher + runner; missing optional libraries degrade to warnings.
- Dataverse client: total-driven paginated discovery, lock-based in-review detection, enrichment (inventory, sizes, depositors), guestbook flow, bundle + original-format downloads with checksum verify, curation-label bulk report, version compare.
- Local SQLite state (WAL), in-memory request log with token redaction, component-kit UI with theme token contrast contract, 513 tests, UI probes, and PyInstaller lite/full builds.
