# Development

## Prerequisites

- Python 3.10+ on Windows (packaging targets Windows `.exe`; other OS not targeted yet).
- R 4.x only needed for parity verification against the original inspectors (optional, port phase).

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy config.example.json config.json     # cmd; PowerShell: Copy-Item config.example.json config.json — Borealis demo preset is the default; edit base_url/api_token/collection if needed
```

Run tests:

```bash
pytest -q   # 101 tests (engine + dataverse + runner + storage + audit regressions; run pytest --collect-only -q for current count) — warning suppressed via pyproject filterwarnings
```

Launch the GUI:

```bash
python main.py
# or with overrides:
python main.py --config path/to/config.json
python main.py --dataverse https://demo.borealisdata.ca
```

Headless engine runs (no GUI — full pipeline on a staged directory; `--dataverse`/`--config` are GUI-only and rejected here):

```bash
python main.py --headless <staged_dataset_dir> --out report.json --persistent-id doi:10.5072/FK2/EXAMPLE
```

This walks the directory, dispatches every file to its format checks (lazy optional deps), runs the dataset-level inventory check, and writes the `DatasetReport` JSON (see `docs/report-contract.md`). Example: `engine/tests/test_runner.py` exercises `run_report` against `CUR_Res_CurationTools/data/Inspect_gpkg` (13 files, 0 findings).

Verify compilation without launching the GUI:

```bash
python -c "import compileall; compileall.compile_dir('.',force=True)"
python -c "import compileall; compileall.compile_dir('ui',quiet=1)"
```

## Layout

- `main.py` — entry: `argparse` for `--headless`/`--out`/`--persistent-id`/`--config`/`--dataverse` (the last two are GUI-only; headless rejects them); Qt/UI imports lazy under GUI branch (TYPE_CHECKING-only at import so `--headless` stays fast; PyInstaller collects via hidden-imports); sibling-folder loader for heavy libs; exit codes 0 clean / 1 error-findings / 2 usage-IO; `MainWindow` (`ui/main_window.py`) with TopNav + `QStackedWidget` (dashboard/detail/settings/about) + log strip.
- `config.py` — `DataverseConfig` (`base_url`, `api_token`, `collection` alias `subtree`/`collection_alias` compat), `AppConfig(workspace)`, `Config.load/save`, `PRESETS` (includes `Borealis Demo — demo.borealisdata.ca`).
- `dataverse_client.py` — `DataverseClient` (see `docs/dataverse-integration.md`), `normalize_files` (keeps UNF/tabular/original-format fields), `parse_ds_metadata_payload`, `search_item_state` (draft-aware) + draft-preferring dedup, curation/version/timestamp/notification parsers, retry on 10054.
- `download_manager.py` — `DownloadManager: quote/quote_from`, `inventory`, `missing_files`/`is_fully_staged`, `approve_and_download` (+ `download_originals` for tabular originals), `verify` → `(ok, problems, warnings)`, `hash_file`, zip-slip guard, streaming downloads, `save/load_metadata` per-dataset cache.
- `metadata_check.py` — `PROFILES`, `DEFAULT_PROFILE`, `check_metadata_completeness` (McMaster vs Minimal), ORCID regex, `requirements_profiles.json` support.
- `applog.py` — `AppLog` ring buffer, `log_response`, `get_app_log()`.
- `storage.py` — SQLite local state (`datasets`, `files`, `check_results`, `curation_actions`) plus JSON caches (`dataset_sizes.json`, `curation_labels.json`, `table_layout.json` with save/restore helpers).
- `engine/checks/base.py` — `Check` base class and `CheckResult(check_id, level, passed, message, details)` dataclass with `to_dict/from_dict`.
- `engine/checks/<format>_check.py` — 20 format modules (csv, xlsx, sav, dta, sas7bdat, json, xml, ipynb, sqlite, hdf5, nc, gpkg, tiff, images, pdf, text, code, containers, fastq, extensions); lazy `try/except ImportError` for heavy libs.
- `engine/checks/_util.py` — `missing_library`, `detect_encoding`, `find_emails`.
- `engine/checks/__init__.py` — `registry` of all checks.
- `engine/report.py` — `DatasetReport`/`FileEntry` with JSON round-trip (`to_dict`/`from_dict`/`save`/`load`).
- `engine/dispatcher.py` — maps file path to checks (compound names shed one compression layer: `.fq.gz` → fastq, `.tar.gz` → tar); dataset-level checks have empty `extensions`.
- `engine/runner.py` — `run_report(staged_dir, pid, label)` and `list_planned_checks(files)` (used by the Auto-Checks card); symlinks skipped, per-file isolation via `_safe_run`, `inventory.unchecked_types` hint for formats without a check.
- `engine/tests/test_audit_fixes.py` — 31 regression tests for the audit batches (dispatch, missing-lib contract, traversal/atomicity, caps, taxonomy).
- `ui/` — `widgets.py` kit (`AppButton` kinds primary/secondary/ghost/chip/nav + sizes sm/md/lg, `AppTable` movable/resizable/sortable/copy, `make_card`, `make_search_field`/`make_line_edit`, `make_combo`) used by every view; `main_window.py` (TopNav with dataset chips + close buttons, stack, status bar, shortcuts), `dashboard.py` (`COLUMNS` 12, `_SortItem` numeric/date sort, status/label/collection filters + Columns… menu; Status is plain text; `dashboard_cache.json` cache-first paint + `diff_dashboard_datasets` change-only refresh), `dataset_detail.py` (main column: completeness/manifest/auto-checks/version-log cards; sticky sidebar: sections nav/dataset timeline/assessment), `settings_dialog.py:SettingsPane` (General/Extensions tabs, install/uninstall + sizes + tool rows), `about_pane.py`, `workers.py` (parented QThread workers with `progress`/`finished`/`error`, `MetadataWorker` fetching metadata/inventory/curation/diff/versions/timestamps/notifications), `dialogs.py` (selectable), `log_panel.py` (QWidget strip under nav with Live toggle, `QSyntaxHighlighter` INAV-style), `download_dialog.py`, `requirements_dialog.py`, `theme.py` (tokens, QSS incl. chevron asset + unified 8px radius, `selectable_labels`, table/list copy filters, app-wide hover cursor).

## Adding a check

1. Implement `Check` in `engine/checks/<name>_check.py` with a unique `check_id` in the `format.<format>.*` namespace and the extensions it applies to; use lazy `try: import` for optional heavy deps and return a warning `CheckResult` via `_util.missing_library` if absent.
2. Import and register it in `engine/checks/__init__.py:registry` so `dispatcher` and `runner` discover it.
3. Add fixtures under `engine/tests/fixtures/` and a test in `engine/tests/test_formats.py` (or `test_port_spike.py`) asserting `CheckResult`s for a known-good and known-bad file.
4. Re-run `pytest`; the GUI picks the new check up automatically through `registry` → `list_planned_checks` → **Auto-Checks** card (missing-lib status shown as `Missing: pip install …`). Document its semantics in `docs/checks-reference.md`.

## Parity verification (port phase — completed)

1. Ran each R inspector on a sample directory from `CUR_Res_CurationTools/data/` and saved its CSV output.
2. Ran the corresponding Python check on the same directory and dumped `DatasetReport` JSON.
3. Asserted equivalent findings; encoded differences as test fixtures so CI keeps the two in sync.

Notable divergences documented in `docs/engine-port.md`: sas7bdat magic at offset 80, gpkg pure-SQLite, netcdf per-dim capped slices, containers zip integrity, fastq gzip-aware capped sampling, csv delimiter sniff fallback.

## Packaging

```bash
make build         # both artefacts: lite onefile exe + full onedir folder
make rebuild-lite  # lite exe only (~2 min), keeps dist/curation-app-full/
make build-full    # onedir folder only
```

- Lite onefile (`--windowed --onefile` + `--exclude-module` for heavy libs + `--add-data "ui/assets;ui/assets"`, ~63 MB): single exe, no unzip step; heavy libs load from a sibling `dist/curation-app-full/` when present.
- Full onedir (no excludes): complete builds for full check coverage.
- Top-level imports in `main.py` guarantee `pyi_rth_pyside6` collects the Qt plugins.
- Verify after building: output should end `Build complete! The results are available in: …\dist`; smoke-launch the exe and kill it.
- Installer (Inno Setup / WiX) is a later milestone.

## Conventions

- Python 3.10 typing, dataclasses for data structures, no external framework in `engine/` (stdlib + listed deps only).
- Checks are pure functions of local files — no network I/O inside `engine/`.
- Follow the module-per-format naming of the R scripts so the mapping stays obvious.
- Keep `docs/report-contract.md` in sync when the report schema changes; it is the interface between engine and GUI.
- Use selectable dialogs (`ui/dialogs.py: show_warning/show_critical/show_info`) for any error that may contain a traceback.
- Log every Dataverse request via `applog.log_response`; the strip (`Log` toggle) uses `QSyntaxHighlighter` (ERROR red, WARNING yellow, IPs, SQL keywords, XML tags, Java backtraces).
- Parent every `QThread` worker to its view, chain `deleteLater` on completion, and adopt running workers before discarding a view (see `MainWindow._open_dataset`) — never destroy a live `QThread`.
