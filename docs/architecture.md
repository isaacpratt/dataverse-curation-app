# Architecture

The Dataverse Curation App is a single-process PySide6 desktop application. It talks to Dataverse over the Native/Search API, downloads approved datasets to a local workspace, runs a Python check engine (ported from the R scripts in CUR_Res_CurationTools), checks citation-block metadata completeness, and renders findings in a desktop GUI with a live request log.

## Component overview

```
┌──────────────┐   ┌────────────────────┐   ┌────────────────────┐
│   Dataverse  │──▶│ dataverse_client   │──▶│ download_manager   │
│ (Native API) │   │ dvmeta CLI +       │   │ quote → approve →  │
└──────────────┘   │ paginated search   │   │ bundle → originals │
                   │ locks confirmation │   │ → verify (ok/prob/ │
                   └────────────────────┘   │   warn)            │
                                            └─────────┬──────────┘
                                                     │ staged files
                                                     ▼
                   ┌────────────────────┐   ┌──────────────────┐
                   │  storage.py        │◀──│ engine/          │
                   │  SQLite state.db + │   │ dispatcher,      │
                   │  JSON caches       │   │ checks/*, runner │
                   └────────────────────┘   │ report.py        │
                                            └────────┬─────────┘
                   ┌────────────────────┐            │
                   │  ui/ (PySide6)     │◀── results ┘
                   │  dashboard, detail │
                   │  settings/about    │   metadata_check.py
                   │  log strip         │   applog.py
                   └────────────────────┘
```

## Components

| Component | File(s) | Responsibility |
| --- | --- | --- |
| Dataverse client | `dataverse_client.py`, `config.py` | Auth (`X-Dataverse-key`), dataset discovery (dvmeta CLI draft crawl when available, otherwise paginated `GET /api/search?q=*&type=dataset&per_page=100&start=…&subtree=…` with draft-aware state + dedup preferring draft rows), `IN_REVIEW` lock confirmation (`GET /api/datasets/:persistentId/locks`), dataset metadata, file inventory (`GET /api/datasets/:persistentId/versions/:draftId`, keeps UNF/tabular/original-format fields), bundle + original-format downloads (`GET /api/access/dataset/:persistentId?version=draft` streaming, no JSON Accept; `GET /api/access/datafile/{id}?format=original`), version compare (`…/versions/:latest-published/compare/:draft`), version list, lifecycle timestamps, notifications inbox (in-app format, PID-matched `SUBMITTEDDS`), curation labels (bulk CSV report → per-dataset fallback → single allowed-set pull) |
| Download manager | `download_manager.py` | Size quote before download (original size preferred for tabular), approval gate, skip-if-fully-staged (original path + size for tabular), zip bundle streaming with progress, original-format fetch for tabular ingests then removal of staged `.tab` derivatives (originals-only), zip-slip guard, checksum verification returning `(ok, problems, warnings)` (originals verified by size; non-tabular mismatches are problems), workspace staging + `metadata.json`/`file-manifest.json` persistence |
| Check engine | `engine/` | 21 per-format checks (`engine/checks/*_check.py`, `base.py:Check`/`CheckResult`), dispatch by extension/MIME (`dispatcher.py`), aggregation into `DatasetReport` (`report.py`), planned-check enumeration (`runner.py:list_planned_checks`), lazy imports for heavy libs; secrets (`hush-scan`) and structured PII (`piigex` + CA pack) ship in lite and full |
| Metadata completeness | `metadata_check.py` + `review_rules.py` | Rule-driven completeness from versioned rulesets (`mcmaster-default` from `docs/CurationLog.pdf`/`docs/DepositorChecklist.pdf`, `minimal`), per-author ORCID + author count + license/terms handlers, README/text-search content rules, configurable `requirements_profiles.json` v2 |
| Local state | `storage.py` | SQLite (`state.db`: datasets/files/check_results/curation_actions) plus JSON caches: `dataset_sizes.json` (summed inventory sizes), `curation_labels.json` (per-instance label sets), `dashboard_cache.json` (last crawl per instance+collection for instant paint + change-only refresh), `table_layout.json` (column widths/sort/hidden/order; `restore_table_state` returns `bool` so callers lock content auto-fit when a saved view was applied) |
| App log | `applog.py` | In-memory ring buffer (`AppLog`), `log_response` for every request (method, URL, status, ms, summary), surfaced in the log strip under the nav bar |
| GUI | `ui/` | Dashboard (`dashboard.py`, 12 columns plain text, status/label/collection filters, `dashboard_cache.json` cache-first paint + `diff_dashboard_datasets` change-only summary), dataset detail (`dataset_detail.py`, main column + sticky sidebar cards), settings/about stack pages (`settings_dialog.py:SettingsPane` with extensions tab incl. install/uninstall + sizes, `about_pane.py`), log strip (`log_panel.py` card with Live toggle, `QSyntaxHighlighter`), workers (`workers.py: CrawlWorker`/`DownloadWorker`/`CheckWorker`/`MetadataWorker`), selectable dialogs (`dialogs.py`), shared component kit (`widgets.py: AppButton`/`AppTable`/`make_card`/`make_search_field`/`make_line_edit`/`make_combo` — one source of truth for buttons/tables/cards/inputs; `AppTable.fit_columns_to_content` sizes Interactive columns to header/cell/widget content with min/max clamps and proportional downscale when the total overflows the viewport, locks on manual resize or restored view, re-fits after **Reset**, and emits `columns_fitted` for the dashboard's split header) + shared theme + copy helpers (`theme.py`, incl. visible `QHeaderView` section dividers with hover/pressed states) |

## Threading model

The GUI thread never blocks. Network requests (crawl/search, metadata, download) and engine runs execute on `QThread` workers parented to their views, with `deleteLater` chained on completion; progress is reported back through Qt signals (`progress`, `finished`, `error`). One check run at a time per dataset; results are written as a `DatasetReport` so a crash does not lose work. When a detail view is discarded mid-task, its running workers are adopted by the main window so no live `QThread` is ever destroyed. The log strip polls `applog.get_app_log().lines()` on a `QTimer` (800 ms, pausable via the Live toggle).

Heavy optional dependencies (`pyreadstat`, `netCDF4`, `h5py`, `tifffile`, `Pillow`, `pypdf`, `lxml`, `openpyxl`) are imported lazily inside each check; a missing lib yields a `CheckResult(level="warning", passed=True, message="Missing: pip install … — check not executed")` rather than an error.

## Data flow for one dataset

1. Dashboard refresh calls `dataverse_client.list_draft_datasets()`; the client uses the dvmeta CLI draft crawl when installed, otherwise paginates `GET /api/search` (`per_page=100&start=…`) with draft-aware state derivation and dedup preferring draft rows. `CrawlWorker` then confirms `IN_REVIEW` locks and pulls curation labels (bulk CSV report → per-dataset fallback → single allowed-set pull); rows render as plain text. The last crawl is cached per instance+collection (`dashboard_cache.json`): app open paints the cache instantly, the background refresh diffs (`diff_dashboard_datasets`, local enrichment excluded from the fingerprint) and reports only `N new, M updated, K removed` / `No changes`, then re-saves the cache.
2. The curator opens a dataset: the detail view shows instantly from session/disk cache if present, then auto-loads (`QTimer.singleShot(100)`) via `MetadataWorker` — dataset metadata + file inventory + curation status/history/allowed labels + version diff + version list + lifecycle timestamps + review-submission lookup — and shows the file inventory, citation fields, metadata completeness (default profile `McMaster`), version log, and dataset timeline.
3. **Download All** computes a quote (file count + total size; original size preferred for tabular) from the inventory and checks what's already staged — fully-staged datasets skip with a verified notice; otherwise, on approval, the bundle is streamed (`GET /api/access/dataset/:persistentId?version=draft`, with `:latest` fallback) into `workspace/downloads/<persistent_id>/`, unzipped with zip-slip protection, original uploads are fetched per tabular file (`GET /api/access/datafile/{id}?format=original`) and staged `.tab` derivatives are removed (originals-only), and verification runs (`download_manager.verify()` → `(ok, problems, warnings)` — originals by size, others by checksum).
4. **Run checks** (`CheckWorker` → `engine/runner.py:run_report`) walks the staged directory, maps each file to its format check(s) via the dispatcher, runs the dataset-level `extensions` check, and aggregates into a `DatasetReport` (`engine/report.py`) which exports as JSON defaulting to `workspace/downloads/<persistent_id>/reports/`.
5. The GUI renders the main column (completeness, manifest with downloaded checkboxes, auto-checks with legend, version log) and the sticky sidebar (section jumps, dataset timeline, assessment that can push the chosen curation label back to Dataverse). The header link is version-aware: `dataset.xhtml?persistentId=…&version=DRAFT` for drafts.

## Local storage

- `workspace/state.db` — SQLite (schema in `storage.py`): `datasets`, `files`, `check_results`, `curation_actions` (append-only local timeline).
- `workspace/downloads/<persistent_id>/` — staged dataset files (preserves `directoryLabel` subfolders) plus `metadata.json`, `file-manifest.json`, and `reports/<id>_report.json` exports.
- `workspace/dataset_sizes.json` — summed inventory sizes for the dashboard Size column.
- `workspace/curation_labels.json` — per-instance curation-label sets, keyed by base URL.
- `workspace/dashboard_cache.json` — last dashboard crawl per instance+collection (instant paint on open + change-only refresh via `diff_dashboard_datasets`).
- `workspace/table_layout.json` — persisted table view state (column widths, sort, hidden columns, visual order) for the dashboard queue, dataset-page tables, extensions table, and review-fields tree.
- `config.json` — Dataverse URL, API token, collection alias, workspace path. Next to the exe (or `config.example.json` default); gitignored. Overridable via `--config` / `--dataverse` CLI flags.
- `requirements_profiles.json` — versioned review rulesets (field + text-search rules, per-rule response templates, per-Dataverse assignment; editable via the top-nav **Review configuration** page).

## Report contract

The engine and GUI communicate through `DatasetReport` JSON, defined in `docs/report-contract.md` and implemented in `engine/report.py`. The GUI renders this structure directly, without knowing individual checks. Headless mode (`python main.py --headless <dir> --out report.json`) exercises the same contract without the GUI.

## Extensibility

Adding a format check is a new module in `engine/checks/` implementing `engine/checks/base.py:Check` (`check_id` in `format.<format>.*`), registered in `engine/checks/__init__.py:registry`. See `docs/development.md`. The **Auto-Checks** card and `list_planned_checks` pick it up automatically; missing libs are surfaced as “Missing: pip install …”. Check semantics (`docs/checks-reference.md`) are part of the contract.

## Packaging and deployment

- Lite exe: PyInstaller `--windowed --onefile` with `--exclude-module` only for the heavy binary libs (`pyreadstat`, `netCDF4`, `h5py`, `scipy`) plus `--add-data "ui/assets;ui/assets"` and `--collect-all piigex` (piigex's detectors package walks the on-disk tree at import — plain `--hidden-import` leaves modules only in the PYZ archive, so the walk fails with `WinError 3` under `_MEI`). Common libs (`Pillow`, `pypdf`, `lxml`, `openpyxl`, `tifffile`, `chardet`) are bundled so JPG/PNG/PDF/XML/XLSX/TIFF work offline. Qt/UI imports are lazy in `main.py` (TYPE_CHECKING at import, real import in GUI branch) with PyInstaller hidden-imports covering `pyi_rth_pyside6` (the engine is imported through `ui/workers.py`, so no extra hook is needed). `Makefile` targets: `build` (both artefacts), `rebuild-lite` (exe only, cached, no --clean), `build-full` (onedir folder, exe at `dist/curation-app-full/curation-app-full.exe`), `smoke`; PowerShell: `.\build-lite.ps1`.
- `config.example.json` plus the `docs/` checklist PDFs are copied alongside the exe. Missing optional libs report “Missing …” rather than failing; frozen builds point at the full exe instead of `pip install`. JPG/PNG/GIF/BMP/WEBP have a stdlib header fallback when Pillow is absent. For heavy formats run the full exe directly — sibling `sys.path` injection cannot load pure-Python modules from an onedir `_internal` (only `.pyd` shims live there).
- Optional tools (tesseract for OCR, external exiftool) degrade gracefully — no R dependency at runtime. The Python engine replaces R; R is only needed during the port for parity verification.
- Network resilience: `dataverse_client._get_json` retries 3× on `ConnectionError`/`ChunkedEncodingError`/`ConnectionResetError` (WinError 10054) with backoff; dialogs are selectable (`ui/dialogs.py`) for copying tracebacks.

## Decisions record

| Date | Decision |
| --- | --- |
| 2026-08-17 | Desktop app over web app; PySide6 native single-process |
| 2026-08-17 | Dataverse auth via config API token (server-side style, like the dashboard's `DATAVERSE_API_KEY`) |
| 2026-08-17 | Evaluate Python port of R checks vs. bundling portable R (~400 MB); see `docs/engine-port.md` — Python port chosen (~50–100 MB) |
| 2026-08-21 | Dataset discovery via dataverse-metadata-crawler (`dvmeta` CLI, draft-version crawl) + per-dataset `IN_REVIEW` lock confirmation; Search API paginated fallback for frozen builds |
| 2026-08-25 | Paginated discovery via `GET /api/search` (`start` not `page`, dedup by persistentId, `subtree` empty = whole repository, `:root` special-cased); streaming download without JSON Accept; retry on 10054 |
| 2026-08-25 | Metadata completeness as first-class feature (McMaster profile from CurationLog/Depositor Checklist, configurable requirement profiles) |
| 2026-08-26 | Lite packaging with lazy imports — lite build excludes heavy libs, missing deps reported as warnings not errors |
| 2026-09-08 | Detail page reworked to main column + sticky sidebar (completeness, manifest, auto-checks, version log; sections nav, dataset timeline, assessment); settings/about converted from modal dialogs to stack panes; log dock converted to a strip under the nav |
| 2026-09-09 | Verification split into problems vs warnings (`.tab` mismatches are notes with UNFs); original-format fetch for tabular ingests; skip-if-staged downloads; metadata/manifest/report persistence per dataset; table-width persistence; QThread parenting + worker adoption on view teardown |
| 2026-09-11 | UI standardized on `ui/widgets.py` kit (AppButton/AppTable/make_card/search+line inputs/make_combo); RinUI QML rejected (beta, QML-only, solo-maintained); intentional one-offs documented in the kit docstring (inline `action_button_style` faces, tinted queue/metric cards, header-less about card, Live toggle, split chips) |
| 2026-09-14 | Audit fix batch: compound-extension dispatch, missing-lib warning guards, atomic download staging + traversal guards, Timeout/429/503 retries with bundle retry loop, worker-lifecycle hardening (adoption on close, quit on shutdown), crawl/label thread-pool, batched sqlite + debounced filters, engine scan caps and taxonomy alignment |
| 2026-09-15 | Dashboard Status column back to plain text; dashboard table cached (`dashboard_cache.json`, cache-first paint + `N new, M updated, K removed` / `No changes` summary); Extensions tab repaired (RECORD-based sizes, styled Install/Uninstall, tool status wording); file-manifest staged detection via basename fallback + Download button state; dataset-log sidebar stretch |
| 2026-09-15 | MIT license (© 2026 Isaac Pratt and McMaster, third-party attributions in LICENSE); checklist PDFs moved to `docs/`; `updated_layout/` design mock removed (no code depended on it) |
| 2026-09-23 | Caption-button hit codes (HTMIN/MAX/CLOSE), window min-size + stacked-page minimum override (no first-open height jump), metadata Value↔Status drag resize, file-manifest horizontal room, originals-only downloads (drop staged `.tab`), tabular ingest status API + manifest notes, per-author ORCID + author count + license/terms rules, local-time log + search box, restricted/embargo/retention tooltips, click-before-scroll combos |
| 2026-09-23 | Code/UI audit fix batch: Settings package sizes off GUI thread (`_SizeWorker`), stage-download per-PID locks + failure logging, config Windows ACL (`icacls`), `requests.Session` pooling, log timer gated to page visibility + search debounce, dead modules removed (`LogDialog`/`LogPanel`/`RequirementsDialog`), shared `_human_size` with GB/TB, `setAccessibleName` on icon-only controls, crawler git dep pinned, unused `pandas` dep dropped, regression tests for redaction/config/storage/headless |
| 2026-09-25 | Theme single source of truth: all hardcoded hex colours removed from `ui/*.py` outside `theme.py` (tokenize-based pass, concat-safe; enforced by `ui/tests/test_theme_tokens.py`); UX critique batch — queue keyboard parity (Enter opens focused row, F5 refresh, Escape clears search), plain-language error dialogs with details + Retry (`dialogs.py:describe_error`), destructive Delete/Revert confirmations + `● unsaved` chip in Review configuration, visible focus indicators (buttons/tables/tabs) and contrast swaps to `SUCCESS_DARK`/`AMBER_700` for small text, dashboard first-run empty-state card (primary **Open Settings**) with metrics reading `—` until the first crawl |
