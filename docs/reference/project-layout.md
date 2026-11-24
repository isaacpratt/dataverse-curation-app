---
page_type: reference
tgdp_template: Reference     # Reference | Glossary
audience: contributor        # curator | developer | contributor | all
---
# Project layout reference

Facts about the repository's structure, tasks and test roots. Detailed setup, conventions and rationale live in the development guide and [architecture](../explanation/architecture.md).

## Repository layout

| File / directory | Role |
| --- | --- |
| `main.py` | `--headless`/`--out`/`--format`/`--persistent-id`/`--export-record`/`--config`/`--dataverse`/`--gallery`; lazy Qt (TYPE_CHECKING-only at import); sibling-libs loader (exe dir and its parent); exits 0/1/2; MainWindow with TopNav + QStackedWidget (dashboard/detail/settings/review-config/about/log) |
| `config.example.json` | Configuration template (see [Configuration reference](configuration.md)) |
| `curation/startup_probe.py` | Opt-in `DOCENT_STARTUP_LOG` phase timings (process start → first paint); no-op unless the variable is set. The only `tools/`-origin module that became app code, because `main.py` and `ui/dashboard.py` import it at runtime |
| `curation/config.py` | `DataverseConfig` (base_url, token, collection alias), `AppConfig` (workspace, tesseract, exiftool), `Config.load/save`, `resolve_config_path()` (CWD → exe dir → level above exe), `PRESETS`, DATAVERSE_* env overrides |
| `curation/client/` | `DataverseClient` (session/retry/downloads in `client.py` + `downloads.py`, parsers in `parsers.py`) — total-driven discovery (`_search_page` → rows + `total_count`) and pooled inventory enrichment (`enrich_datasets_with_inventory`); endpoints in [Dataverse API](dataverse-api.md) |
| `curation/download_manager.py` | `quote`/`quote_from`, `missing_files`/`is_fully_staged`, `approve_and_download` (+ `download_originals`), `verify` → `(ok, problems, warnings)`, zip-slip guard, per-dataset cache, per-PID download locks |
| `curation/metadata_check.py` | `PROFILES`, `DEFAULT_PROFILE="McMaster"`, `check_metadata_completeness`, ORCID regex, `requirements_profiles.json` support |
| `curation/review_rules.py` | `RULESETS_VERSION=2`, `FIELD_CATALOG`, builtin McMaster/Minimal rulesets, per-Dataverse assignment, content-rule evaluation |
| `curation/response_draft.py` | `build_response`/`render_response` — draft from ruleset + report findings |
| `curation/applog.py` | AppLog ring (2000), `log_response`, redaction, `get_app_log()` |
| `curation/storage.py` | SQLite (datasets/files/check_results/curation_actions) + JSON caches (dataset_sizes, curation_labels, table_layout; the dashboard cache lives in `curation/dashboard_cache.py`) |
| `curation/dashboard_cache.py` | Qt-free dashboard cache: slot keys, row fingerprints, change diffing, enrichment merge, load/save. Extracted from `ui/dashboard.py` so engine tests can exercise it without importing the view layer |
| `curation/curation_record.py` | Local curation-record bundle export (used by `--export-record`) |
| `engine/checks/base.py` | `Check` base + `CheckResult` dataclass with `to_dict`/`from_dict` |
| `engine/checks/<format>_check.py` | 24 modules (csv, xlsx, sav, dta, sas7bdat, json, xml, ipynb, sqlite, hdf5, nc, gpkg, tiff, images, pdf, text, code, secret, containers, fastq, extensions, access, varmeta, readme); lazy heavy imports |
| `engine/checks/_util.py` | `missing_library`, `skipped`, `detect_encoding`, `find_emails`/`find_pii` (piigex `regions=["intl"]` + CA postal/SIN; foreign national IDs disabled), `pii_result` |
| `engine/checks/__init__.py` | Registry auto-built from `_MODULES` (24 keys) — see [Check ID index](checks.md#check-id-index) |
| `engine/checks/guidance.py` | Per-check "Why this matters" / "How to fix" registry |
| `engine/constants.py` | `EngineCaps` scan caps (samples, rows, members, pixels…) |
| `engine/status.py` | `classify`/`summarize`/`file_status`/`status_label` badge taxonomy |
| `engine/report.py` / `engine/report_md.py` | `DatasetReport`/`FileEntry` JSON round-trip + Markdown rendering |
| `engine/dispatcher.py` | Registry-driven path → checks; one strippable outer layer (`.fq.gz`→fastq, `.tar.gz`→tar); empty extensions = dataset-level |
| `engine/runner.py` | `run_report`, `run_report_to_file` (`fmt=json|md|both`), `list_planned_checks`; symlinks skipped; `_safe_run` isolation; `inventory.unchecked_types` hint |
| `engine/verdict.py` | Readiness verdict `assess` / `format_line` |
| `ui/ring.py` + `ui/progress.py` | Circular progress ring (catch-up easing, stall backoff, error tint) and the pure phase math (`ease_step`, `phase_fraction`) behind it |
| `ui/table_layout.py` | The table layout controller: one per header; persists user gestures only (programmatic changes run inside `suppressed()`); owns the save, restore and reset |
| `tools/probes/` | Offscreen UI probes (queue columns, manifest columns, page headings, card corner, buttons, gallery) — each against a throwaway workspace; the same contracts live in `ui/tests/` |
| `tools/` (grouped helpers) | `build/` (PyInstaller, Velopack, version tag, smoke, clean), `audit/` (OSV scan, SBOM, licenses, NOTICE, complexity), `docs/` (link check), `perf/` (measured constants), `probes/`, `tests/` — see `tools/README.md` for the script-to-poe-task index |
| `ui/` | `widgets.py` kit; `main_window.py`; `dashboard.py` (COLUMNS 12, `_SortItem`, cache-first + `diff_dashboard_datasets`); `dataset/` (the dataset detail page — see below); `review_config.py`; `settings_dialog.py`; `about_pane.py`; `workers.py` (5 QThreads); `dialogs.py`; `workflow.py` (Qt-free step derivation); `checks_tree.py`; `icons.py`; `log_panel.py` (LogPage); `download_dialog.py`; `i18n.py` + `assets/strings.json` (interface text); `status_text.py` (check taxonomy → display text); `theme.py` (single-source tokens, `asset_path()`/`mark_icon_path()`); `gallery.py` (component gallery) |
| `ui/dataset/` | The dataset detail page: `page.py` is the facade (layout, splitter, signals) over ten section mixins — `metadata_section.py`, `metadata_load.py`, `checks_section.py`, `files_section.py`, `versions_section.py`, `log_rail.py`, `response_section.py`, `actions_section.py`, `header_section.py`, `workflow_section.py` — over the shared contract in `state.py` (`DetailState`) and formatting helpers in `helpers.py`. The facade is imported as `from ui.dataset import DatasetDetailView` |

## Test roots

| Root | Scope |
| --- | --- |
| `engine/tests/` | The check engine (Qt-free) |
| `curation/tests/` | The curation core (Qt-free); fixtures under `curation/tests/fixtures/` |
| `tools/tests/` | The operational scripts |
| `ui/tests/` | The views (pytest-qt, offscreen) |

`pytest --collect-only -q` prints current totals. Parity tests that read the sibling `CUR_Res_CurationTools` clone carry the `samples` marker and are deselected from the default run; `uv run poe samples` runs them.

## Poe task index

All tasks run as `uv run poe <task>`.

| Task | Function |
| --- | --- |
| `check` | lint + typecheck + tests |
| `lint` | ruff lint |
| `format-check` | formatting check over the whole tree |
| `typecheck` | mypy over `[tool.mypy] files` (engine, curation, ui, main.py, in-scope tools; tests relax only three "must annotate" rules) |
| `cover` | engine branch coverage, gated at 65 in `[tool.coverage.report]`; `*/tests/*` omitted from measurement |
| `contracts` | import-linter: `engine/` may not import `ui/` or PySide6; `curation/` likewise; `tools/` may not import `ui/` (UI probes are the documented exception) |
| `samples` | opt-in parity tests against the sample-data clone |
| `probes` | offscreen UI probes |
| `audit` | OSV vulnerability scan of the locked set (`tools/audit/audit_deps.py`) |
| `license-report` / `notice` / `sbom` | license inventory, NOTICE, SBOM |
| `release-artefacts` | release-artefact checks |
| `complexity` | advisory radon view written to `reports/complexity.md` (ruff C901 at max-complexity 12 is the gate) |
| `docs-links` | docs link check |
| `docs` / `docs-serve` | Zensical build / preview |
| `hooks` | pre-commit hooks |
| `build` | PyInstaller onedir build → `dist/DataverseDocent/DataverseDocent.exe` + `config.example.json` |
| `pack` | Velopack release directory in `dist/releases/` (Setup.exe, portable zip, nupkg, feed) |
| `check-pack` | verify an existing `dist/releases/` without repacking |
| `smoke` | size report + headless `--help` check (`DOCENT_SMOKE_EXE=...` to inspect another exe) |

## UI probes

Probes in `tools/probes/` are pixel-and-geometry checks run offscreen against a throwaway workspace; each prints a PASS/FAIL line per check and exits non-zero on failure. `tools/probes/run_all.py` runs every `probe_*.py` (what CI runs).

| Probe | Contract |
| --- | --- |
| `probe_queue_columns.py` | The queue's columns fill the viewport, never clip |
| `probe_manifest_columns.py` | The manifest fits, persists the user's widths, resets |
| `probe_headings.py` | Every full-page heading wears the same token |
| `probe_card_corner.py` | A card's bottom-right corner stays connected |
| other probes | Auto-Checks and Metadata rows, Extensions table, finding dispositions, preview card, About updates section, navigation rail, review rules table, gallery input controls, icon sheet, review-row selection, the two rule cards, entry-check params form, the two check sections |

`tools/probes/_common.py:boot()` points `cfg.app.workspace` at a fresh temp directory and applies the theme; every probe goes through it and stubs out anything that would reach the network. Qt messages are classified: two environment messages are allowed (`QFontDatabase: Cannot find font directory`, `This plugin does not support propagateSizeHints()`); anything else fails the run. The same contracts live in `ui/tests/` as pytest suites (`test_table_layout.py`, `test_table_geometry.py`, `test_page_headings.py`, `test_type_scale.py`, `test_contrast.py`, `test_kit_stylesheets.py`, `test_theme_conformance.py`, `test_strings.py`, `test_gallery_contract.py`).

## Interface text (string catalogue)

All user-visible interface copy lives in one UTF-8 JSON file: `ui/assets/strings.json`. Modules never spell out UI wording; they look it up through `ui/i18n.py`.

| File | Role |
| --- | --- |
| `ui/assets/strings.json` | The catalogue. Nested objects give each screen a namespace (app, common, status, dashboard, detail, review, settings, download, log, checks, workers, main, ring, about, dialogs, workflow). Values are plain strings; `{name}` marks a placeholder filled at the call site |
| `ui/i18n.py` | `t(key, **values)` renders one string, `tn(key, count, **values)` picks a plural variant, `has`/`keys`/`reload` support tooling and tests. A missing key returns the key itself |
| `ui/status_text.py` | Maps engine classifier keys (passed, failed-warning, failed-error, skipped) onto catalogue entries |
| `ui/tests/test_strings.py` | Fails on unknown keys, missing placeholders, values that cannot format, hard-coded interface copy, orphan catalogue entries and unowned prose literals |

The engine and report contract are deliberately not externalised: check messages, result levels and JSON/Markdown report fields are data. QSS, object names, internal dictionary keys, URLs and format identifiers stay in code. Headless CLI messages in `main.py` are catalogue entries under `app.cli`. Data tokens (dataset state tokens, Dataverse state names, cache-slot tokens, the "no label" sentinel, network-error needles) stay in code as shared constants.

## Startup timing

The window paints its shell before the cached dashboard, local state reads or any network call: `main.py` shows the window, processes the first frame, paints it synchronously and reveals it, then calls `MainWindow.start_background_load()`. Until that reveal the window is cloaked out of DWM composition. Settings, About, Requirements and Log are built on first navigation. `DOCENT_STARTUP_LOG` points at a file where every phase appends one row (total ms since process start, ms since `curation/startup_probe.py` import, label); the total includes the PyInstaller bootloader. The probe is inert when the variable is unset.

```powershell
$env:DOCENT_STARTUP_LOG = "$env:TEMP\docent-startup.log"
dist\DataverseDocent\DataverseDocent.exe
Get-Content $env:TEMP\docent-startup.log
```

Warm onedir launches reach first paint in roughly 0.9–1.1 s on the reference machine; cold launches pay an antivirus pass over the ~160 MB folder.

## Performance constants

| Constant | Measured by | Result |
| --- | --- | --- |
| Queue painting window | `tools/perf/bench_paint_window.py` (25k synthetic rows) | 2,000 rows confirmed (~0.9 s per repaint, ~7.6 s uncapped) |
| Enrichment cap | `tools/perf/bench_enrichment_cap.py` (5k synthetic collection, 100 ms simulated GET) | 200 rows confirmed (~4 s per refresh, ~100 s uncapped) |

## See also

- [Checks reference](checks.md)
- [Configuration reference](configuration.md)
- [Glossary](glossary.md)
