# Development

Setup, layout, adding a check, parity verification, packaging, conventions. Prerequisites: Python 3.11+ on Windows; R 4.x only for parity verification (optional).

## Setup

```
uv sync                                     # create/update .venv from uv.lock incl. dev group
copy config.example.json config.json     # cmd; PowerShell: Copy-Item config.example.json config.json
# Borealis demo preset is the default; edit base_url/api_token/collection
uv run pytest                            # 952 tests (523 ui, 345 curation, 58 engine, 26 tools; 19 sample-data parity tests are deselected - run `uv run poe samples`)
uv run python main.py                    # GUI
uv run python main.py --config path/to/config.json
uv run python main.py --dataverse https://demo.borealisdata.ca
uv run python main.py --headless <staged_dir> --out report.json --format json --persistent-id doi:10.5072/FK2/EXAMPLE
uv export --format requirements-txt      # pip escape hatch (lockfile remains source of truth)
```

Headless rejects --dataverse/--config (GUI-only); --format accepts json (default), md, or both. The walk dispatches every file to its format checks and writes the DatasetReport JSON contract. Example: engine/tests/test_runner.py runs run_report against CUR_Res_CurationTools/data/Inspect_gpkg (13 files, 0 findings). Test suites live with the package they exercise: engine/tests/ (the engine), curation/tests/ (the curation core, Qt-free), tools/tests/ (the operational scripts) and ui/tests/ (the views); pytest --collect-only -q prints the current totals.

## Quality gates

CI (windows-latest) runs, via uv run and the committed lockfile: pre-commit run --all-files (EOF/whitespace, JSON/TOML/YAML, secrets, codespell, config.json-forbid, uv lock --check, check-only ruff, actionlint), ruff, pytest with engine coverage, compileall, the headless smoke (.github/workflows/ci.yml) and an OSV vulnerability scan of the locked set (tools/audit/audit_deps.py). CI runs the suite with -n auto (pytest-xdist) for the wall-clock win; locally the suite stays serial by default so a failure is easy to read — pass -n auto yourself when you want the parallel run. A second advisory job runs the engine tests and a headless smoke on ubuntu-latest (continue-on-error until it has been green for ~14 days — the engine is platform-agnostic Python, and a Windows-only CI misses newline and path bugs a file-scanning engine can hit). GitHub Actions are pinned by commit SHA; Dependabot (uv + github-actions weekly, pre-commit monthly) proposes updates (.github/dependabot.yml). Locally: uv run poe check (lint + typecheck + tests), uv run poe lint, uv run poe format-check (whole tree), uv run poe audit, uv run poe hooks, uv run poe typecheck, uv run poe probes, uv run poe license-report, uv run poe notice, uv run poe sbom, uv run poe release-artefacts, uv run poe complexity, uv run poe docs-links. mypy is in the dev group. Coverage is measured on production statements only: */tests/* is omitted from [tool.coverage.run], and the parity tests that read the sibling CUR_Res_CurationTools clone carry the samples marker, so they are deselected from the default run and uv run poe samples runs them on purpose. That makes uv run poe cover (engine, branch coverage) report the same number on a developer machine and on CI: 65.26% of 2301 statements, gated at 65 in [tool.coverage.report]. Both facts matter: before this, test modules inside the measured packages counted as covered source (83% of 6097 statements) and a machine with the sample data next to the repo measured 79% where CI measured 69% - numbers that described the machine, not the repository. Raise the floor with tests for uncovered production paths, never by widening what the measure counts.

poe typecheck gates the engine contract under mypy --strict: engine/ plus the curation core it is built on (curation/client, curation/download_manager.py, curation/storage.py, curation/review_rules.py, curation/metadata_check.py, curation/applog.py) — scope lives in [tool.mypy] files, so run bare uv run mypy. Strict means untyped definitions and calls are rejected, generics carry their type arguments, unreachable code and redundant casts are reported, and equality is strict. The only per-module relaxation is the documented one below — no module is ignored outright: the last 44 errors were fixed by annotating the engine, the client and the core services (dv-hcg.27, 2026-11-16). The engine test suite joined the same gate after the Qt-free seam landed (dv-hcg.26): the dashboard cache helpers it borrowed from ui/dashboard.py now live in the Qt-free curation/dashboard_cache.py, the size-formatter test moved to ui/tests/, and the suites joined under the documented test relaxation. Test roots now sit beside their packages (engine/tests, curation/tests, tools/tests, ui/tests) and all four are in [tool.mypy] files; no test root appears in [tool.mypy] exclude. As of 2026-11-20 (dv-a4w, ADR 0008, which supersedes ADR 0007) the contract is simpler: every application module — engine/, curation/, ui/, main.py and the in-scope tools/ helpers — is checked under full --strict, with no per-module relaxation. The earlier ui.* override was withdrawn after the enum sweep and shape fixes landed; the remaining work was ordinary annotation, not stub ambiguity. Only the test packages relax, and only three "you must annotate this" rules: disallow_untyped_defs = false, disallow_incomplete_defs = false, disallow_untyped_decorators = false; check_untyped_defs = true stays on so unannotated test bodies are still checked. Every other strict rule — disallow_untyped_calls, disallow_any_generics, warn_return_any and all shape checks — remains on for tests too. The single override block names the four test packages and nothing else. A consequence worth knowing: because check_untyped_defs checks an unannotated function's body as a typed context, calling a fully unannotated local helper still raises no-untyped-call; annotating the helper's parameters (the return type is optional under disallow_incomplete_defs = false) is enough. The gate is green with 0 errors across source and tests, and no module is ignored outright.

The repo pins its toolchain with uv.lock and .python-version (3.11), so every PyInstaller build resolves the same dependency set; a stale lock fails CI's uv lock --check before anything builds. The hook set is check-only (no auto-fixers other than whitespace/EOF fixers). core.hooksPath is beads-managed, so hooks are not auto-installed; run uv run pre-commit run --all-files manually, or rely on the CI step.

Complexity: enforcement and visibility. ruff's C901 (max-complexity 12) is the gate; the grandfathered functions carry noqa: C901 burn-down notes. uv run poe complexity writes the advisory view (radon) to reports/complexity.md — the over-budget blocks, the average and the maintainability index — and CI runs it as a non-blocking step and uploads the report as an artefact. radon and ruff count differently (and radon ignores noqa), so use ruff's count for the gate and radon's for the trend.
Architecture contracts are machine-enforced. uv run poe contracts (import-linter, also a step in poe check and in CI) keeps the dependency direction honest: engine/ may not import ui/ or PySide6 — the engine stays headless and Qt-free — the curation core may not import ui/ or PySide6 either, and the operational helpers in tools/ may not import ui/. The engine contract has no exceptions: since dv-hcg.26 the engine tests no longer borrow view helpers, so the contract lists zero ignore_imports. The curation contract landed with the curation/ consolidation (dv-hcg.24) and is just as strict — the table-layout sort direction is persisted as a plain int and converted to Qt.SortOrder in the view layer. The only documented exception left is the UI probes under tools/probes/, which drive the views on purpose.

## Environment variables

All DATAVERSE_* variables override the corresponding config.json value; none are required (the Borealis demo is the default target).

| Variable | Type | Resolution | Notes |
| --- | --- | --- | --- |
| DATAVERSE_BASE_URL | URL | env > config.json (default https://demo.borealisdata.ca) | Must be https:// with a host; plain HTTP is refused with a clear error (the token travels as X-Dataverse-key); trailing slashes trimmed |
| DATAVERSE_API_TOKEN | string | env > OS credential store (keyring) > config.json plaintext | Leading/trailing spaces stripped; empty means "no token (public-only)" |
| DATAVERSE_COLLECTION | string | env > config.json | Collection alias used for discovery (subtree) |
| DATAVERSE_WORKSPACE | path | env > config.json app.workspace (default ~/Documents/curation-workspace) | Where staged downloads and caches live |

## On-disk artefacts

Every file the app writes, its resolution rule and who writes it. Runtime caches are all listed as gitignored; a fresh clone starts clean.

| Path | Resolution | Written by | Contents |
| --- | --- | --- | --- |
| config.json | CWD (dev) · %APPDATA%\Dataverse Docent\ (installed) · exe folder, its parent or grandparent (portable/plain frozen); a new file lands in the exe's parent | Settings; poe build ships config.example.json only | base_url, collection, workspace, tesseract/exiftool paths, api_token_source ("keyring" by default; plaintext token only as fallback when the credential store is unavailable) |
| table_layout.json | CWD (dev/frozen); probes never write here | Table layout controller | per-table saved column widths/orders |
| dataset_sizes.json | CWD | Batch size prober | cached dataset byte sizes for queue hints |
| dashboard_cache.json | CWD | Dashboard | last-seen list state to avoid cold paint |
| requirements_profiles.json | Same policy as config.json | Review configuration | versioned review rulesets (field + text-search rules, per-rule response templates) |
| curation-workspace/*.db / *.db, *.sqlite | ~/Documents/curation-workspace (default) or app.workspace | curation/storage.py / actions log | SQLite local state (WAL): dataset inventory cache, check results, curation actions |
| downloads/ | app.workspace subfolder (default ~/Documents/curation-workspace/downloads) | Download manager | staged originals; skip-if-staged detection; never tracked |
| workspace/, .curation-workspace/ | CWD (if used) | reserved/caches | variant of the workspace concept used by older builds; gitignored |
| metadatablocks_cache.json, curation_labels.json | app.workspace | Metadatablock/labels caches | field catalog + allowed curation labels (best-effort, disposable) |
| .mypy_cache/, .ruff_cache/, .pytest_cache/, .pyi-cache/, __pycache__/ | CWD | tooling | local caches; all gitignored |

## Startup timing

The window paints its shell before the cached dashboard, local state reads or any network call: main.py shows the window, processes the first frame, paints it synchronously and reveals it, then calls MainWindow.start_background_load(). Until that reveal the window is cloaked out of DWM composition, so neither an empty client nor a native title bar can flash on screen. Settings, About, Requirements and Log are built on first navigation (their scroll pages join the stack then). To see where a launch spends its time, point DOCENT_STARTUP_LOG at a file; every phase appends one row (total ms since process start, ms since curation/startup_probe.py import, label), and the total includes the PyInstaller bootloader:

```
$env:DOCENT_STARTUP_LOG = "$env:TEMP\docent-startup.log"
dist\DataverseDocent\DataverseDocent.exe
Get-Content $env:TEMP\docent-startup.log
```

Warm onedir launches reach first paint in roughly 0.9-1.1 s on the reference machine; cold launches pay an antivirus pass over the ~160 MB folder. The probe is inert (one environment lookup per mark) when the variable is unset.

## Layout

| File | Role |
| --- | --- |
| main.py | --headless/--out/--format/--persistent-id/--config/--dataverse; lazy Qt (TYPE_CHECKING-only at import); sibling-libs loader (exe dir and its parent); exits 0/1/2; MainWindow with TopNav + QStackedWidget (dashboard/detail/settings/review-config/about/log) |
| curation/startup_probe.py | Opt-in DOCENT_STARTUP_LOG phase timings (process start → first paint); no-op unless the variable is set. The only tools/ module that became app code, because main.py and ui/dashboard.py import it at runtime |
| curation/config.py | DataverseConfig (base_url, token, collection alias), AppConfig (workspace, tesseract, exiftool), Config.load/save, resolve_config_path() (CWD → exe dir → level above exe), PRESETS, DATAVERSE_* env overrides |
| curation/client/ | DataverseClient (session/retry/downloads in curation/client/client.py + curation/client/downloads.py, parsers in curation/client/parsers.py) — total-driven discovery (_search_page → rows + total_count) and pooled inventory enrichment (enrich_datasets_with_inventory) — endpoints in Dataverse integration |
| ui/ring.py + ui/progress.py | Circular progress ring (catch-up easing, stall backoff, error tint) and the pure phase math (ease_step, phase_fraction) behind it |
| curation/download_manager.py | quote/quote_from, missing_files/is_fully_staged, approve_and_download (+ download_originals), verify → (ok, problems, warnings), zip-slip guard, per-dataset cache, per-PID download locks |
| curation/metadata_check.py | PROFILES, DEFAULT_PROFILE="McMaster", check_metadata_completeness, ORCID regex, requirements_profiles.json support |
| curation/review_rules.py | RULESETS_VERSION=2, FIELD_CATALOG, builtin McMaster/Minimal rulesets, per-Dataverse assignment, content-rule evaluation |
| curation/response_draft.py | build_response/render_response — draft from ruleset + report findings |
| curation/applog.py | AppLog ring (2000), log_response, redaction, get_app_log() |
| curation/storage.py | SQLite (datasets/files/check_results/curation_actions) + JSON caches (dataset_sizes, curation_labels, table_layout; the dashboard cache lives in curation/dashboard_cache.py) |
| engine/checks/base.py | Check base + CheckResult dataclass with to_dict/from_dict |
| engine/checks/<format>_check.py | 22 modules (csv, xlsx, sav, dta, sas7bdat, json, xml, ipynb, sqlite, hdf5, nc, gpkg, tiff, images, pdf, text, code, secret, containers, fastq, extensions, access); lazy heavy imports |
| engine/checks/_util.py | missing_library, skipped, detect_encoding, find_emails/find_pii (piigex regions=["intl"] + CA postal/SIN; foreign national IDs disabled), pii_result |
| engine/checks/__init__.py | registry auto-built from _MODULES (22 keys) |
| engine/constants.py | EngineCaps scan caps (samples, rows, members, pixels…) |
| engine/status.py | classify/summarize/file_status/status_label badge taxonomy |
| engine/report.py / report_md.py | DatasetReport/FileEntry JSON round-trip + Markdown rendering |
| engine/dispatcher.py | Registry-driven path → checks; one strippable outer layer (.fq.gz→fastq, .tar.gz→tar); empty extensions = dataset-level |
| engine/runner.py | run_report, run_report_to_file(fmt=json|md|both), list_planned_checks; symlinks skipped; _safe_run isolation; inventory.unchecked_types hint |
| curation/tests/test_audit_fixes.py | 22 regression tests for the audit batches (dispatch, missing-lib contract, traversal/atomicity, caps, taxonomy) |
| curation/dashboard_cache.py | Qt-free dashboard cache: slot keys, row fingerprints, change diffing, enrichment merge, load/save. Extracted from ui/dashboard.py so the engine tests can exercise it without importing the view layer (dv-hcg.26), now part of the curation core (dv-hcg.24) |
| ui/table_layout.py | The table layout controller: one per header; persists user gestures only (programmatic changes run inside suppressed()); owns the save, restore and reset |
| tools/probes/ | Offscreen UI probes (queue columns, manifest columns, page headings, card corner, buttons, gallery) — each against a throwaway workspace; the same contracts live in ui/tests/ |
| tools/ (grouped helpers) | build/ (PyInstaller, Velopack, version tag, smoke, clean), audit/ (OSV scan, SBOM, licenses, NOTICE, complexity), docs/ (link check), perf/ (measured constants), probes/, tests/ — see tools/README.md for the script-to-poe-task index |
| ui/ | widgets.py kit; main_window.py; dashboard.py (COLUMNS 12, _SortItem, cache-first + diff_dashboard_datasets); dataset/ (the dataset detail page, split into sections — see below); review_config.py; settings_dialog.py; about_pane.py; workers.py (5 QThreads); dialogs.py (selectable + describe_error + confirm_save_discard_cancel); workflow.py (Qt-free step derivation); checks_tree.py; icons.py; log_panel.py (LogPage); download_dialog.py; i18n.py + assets/strings.json (interface text); status_text.py (check taxonomy → display text); theme.py (single-source tokens, asset_path()/mark_icon_path()) |
| ui/dataset/ | The dataset detail page, split from one 4,400-line module (dv-hcg.22): page.py is the facade (layout, splitter, signals) over ten section mixins — metadata_section.py, metadata_load.py, checks_section.py, files_section.py, versions_section.py, log_rail.py, response_section.py, actions_section.py, header_section.py, workflow_section.py — over the shared contract in state.py (DetailState: the attributes the page owns and the calls the sections make across each other) and the shared formatting helpers in helpers.py. The facade is imported as from ui.dataset import DatasetDetailView |

## Adding a check

1Implementengine/checks/_check.py: unique check_id in format..*, extensions set, lazy try: import + _util.missing_library warning when absent.
→
2RegisterImport + append in engine/checks/__init__.py:_MODULES so registry, dispatcher, and runner discover it.
→
3TestFixtures beside the test that uses them (for example curation/tests/fixtures/) + cases in engine/tests/test_formats.py/test_port_spike.py asserting CheckResults for known-good and known-bad files; re-run pytest.
→
4DocumentGUI picks it up automatically (registry → list_planned_checks → Auto-Checks); document semantics in Checks reference (+ this page set).

## Parity verification (completed)

1. Ran each R inspector on a CUR_Res_CurationTools/data/ sample, saved CSV output.
1. Ran the matching Python check on the same directory, dumped DatasetReport JSON.
1. Asserted equivalent findings; differences encoded as CI fixtures.

Notable divergences documented in Engine port: sas7bdat magic at offset 80, gpkg pure-SQLite, netcdf per-dim capped slices, containers zip integrity, fastq gzip-aware capped sampling, csv delimiter-sniff fallback.

## Interface text (string catalogue)

All user-visible interface copy lives in one UTF-8 JSON file: ui/assets/strings.json. Modules never spell out UI wording; they look it up through ui/i18n.py.

| File | Role |
| --- | --- |
| ui/assets/strings.json | The catalogue. Nested objects give each screen a namespace (app, common, status, dashboard, detail, review, settings, download, log, checks, workers, main, ring, about, dialogs, workflow). Values are plain strings; {name} marks a placeholder filled at the call site. |
| ui/i18n.py | t(key, **values) renders one string, tn(key, count, **values) picks a plural variant, has/keys/reload support tooling and tests. A missing key returns the key itself, so a typo degrades instead of crashing a screen. |
| ui/status_text.py | Maps the engine's stable classifier keys (passed, failed-warning, failed-error, skipped) onto catalogue entries, so the GUI never reads the engine's English labels back as data. |
| ui/tests/test_strings.py | Fails the build when the catalogue and the code drift apart: unknown keys, missing placeholders, values that cannot format, a module that hard-codes interface copy again, catalogue entries nothing references (an orphan entry is rot — it looks like live copy but no screen can show it), and any prose literal in the interface layer that neither the catalogue nor the structural allowlist owns. |

```
from ui.i18n import t

self._btn = AppButton(t("detail.header.download_all"))
self._status.setText(t("detail.status.metadata_loaded", count=len(inventory)))
```

Conventions. Keep the English wording byte-identical when moving a string — the existing tests assert exact copy. Escape literal braces as {{ / }}. Namespaces follow the module that owns the text (detail.* for the dataset detail page, ui/dataset/); shared words such as common.save, common.cancel and status.badges.* are reused rather than duplicated. ui/assets already ships through the existing --add-data "ui/assets;ui/assets" PyInstaller rule, so frozen builds need no extra packaging step.

Keys must be static. Build the key at the call site, never from a fragment: t(f"main.caption.{kind}") hides the key from the string test, so a rename would render the raw key in the title bar. Keep a small lookup table instead (_CAPTION_KEYS = {"min": "main.caption.min", …}) — the test then sees every key as a plain string and can prove it exists.

The prose sweep catches text that travels. The call-based scan cannot see a title and message packed into a tuple and shown later, so test_strings.py also reads the literals themselves: anything that reads as words in ui/ or main.py must be in the catalogue or in the allowlist, which carries one line per exception and the reason it stays. CSS, HTML, SQL, URLs, date formats, regexes and key sequences are recognised by shape or by the call they are passed to.

Out of scope. The engine and the report contract are deliberately not externalised: check messages, result levels and the JSON/Markdown report fields are data consumed by other tools, not interface copy. QSS, object names, internal dictionary keys, URLs and format identifiers stay in code. The headless CLI messages in main.py are catalogue entries under app.cli.

Data tokens stay in code. A few strings look like copy but are part of a machine contract, so they are shared constants rather than catalogue entries: the dataset state token client.STATE_IN_REVIEW (rendered by the dashboard through dashboard.display_state.review), the Dataverse state names compared by the status filter (DRAFT, PUBLISHED, IN REVIEW, DEACCESSIONED), the cache-slot token behind dashboard_cache_key(), the "no label" filter sentinel, and the network-error needles in ui/dialogs.py that are matched against raw exception text. Translating any of them would change behaviour, not just wording.

## Packaging

```
uv run poe build         # dist/DataverseDocent/DataverseDocent.exe + example config (~55 s)
uv run poe pack          # dist/releases: Setup.exe + portable zip + nupkg + feed (~15 s)
uv run poe check-pack    # verify an existing dist/releases without repacking
uv run poe smoke         # size report + headless --help check (DOCENT_SMOKE_EXE=... to inspect another exe)

- One onedir build (dist/DataverseDocent/DataverseDocent.exe): --windowed --onedir --name DataverseDocent + the verified-safe trims (tkinter, turtle, PIL.ImageTk, PIL.SpiderImagePlugin, PIL._avif, unused Qt modules) + --icon ui/assets/docent-mark.ico + --add-data "ui/assets;ui/assets" + --collect-all piigex, with every format library kept in. Onedir since 2026-10-07 — the former onefile exe re-extracted ~250MB (AV-scanned) on every launch (~21s); the folder build shows its window in ~2.1s (pid-filtered measurement; source: 1.7s). This folder is what poe pack packages, so the installer's copy and the one you test by hand are the same bits; poe build also copies config.example.json alongside.

- Build cost, and what not to rebuild. PyInstaller re-analyses the whole import graph on every run - about 55 s of a full build, some 23 s of it in the PySide6 hooks (hook-PySide6.QtWidgets alone is ~18 s) - so --clean buys nothing and the one task dropped it; the Analysis cache it wipes is not what the time goes to. poe build now makes that one folder, and PyInstaller flags live in one list in tools/build/build_app.py, which prints the wall time and artefact size. Ordinary development needs no freeze at all: uv run python main.py starts in ~1.7 s and runs the same code (only the sys.frozen paths differ), so freeze when the thing you are testing is frozen-specific - config and profile locations, bundled assets, "Missing ..." reports - not for every UI change. Windows Defender scanning the ~1,400 files a build writes is a measurable slice; excluding the worktree and dist/ from real-time scanning is worth it on a development machine.

- Installer (Velopack). poe pack packs the onedir folder: dist/releases/ ends up with DataverseDocent-win-Setup.exe (one click, per-user, no admin), DataverseDocent-win-Portable.zip, DataverseDocent-0.1.0-full.nupkg and the releases.win.json feed. It needs the .NET 10 SDK and dotnet tool install -g vpk once per machine — build time only, nothing users install or need (CI already has SDKs; the release workflow pins the vpk version). VPK overrides the executable. The ids, title, channel, architecture and main exe are constants in tools/build/check_pack.py: --packId names %LocalAppData%\DataverseDocent and the update feed, so changing it orphans every existing install instead of updating it. Packing the same version twice is allowed locally (poe pack replaces that version's package, which vpk alone refuses) — pass --no-replace to get vpk's refusal back. Deltas need the previous release in the same folder: poe pack, then uv run python tools/build/pack_app.py --version 0.1.1 shows the delta size (209 KB for a one-file change against 102 MB full). Nothing is uploaded from a developer machine; vpk upload github is the release workflow's job.

- Top-level imports in main.py guarantee pyi_rth_pyside6 collects Qt plugins. Verify: output ends Build complete! …\dist, then smoke-launch and kill. The installer is Velopack's one-click Setup.exe (bead dv-4t6; the old Inno/WiX plan is superseded) - uv run poe pack packages the full folder and a tag-driven release workflow publishes it.

- One version, one literal: engine/__init__.py:__version__ is read by the wheel metadata ([tool.setuptools.dynamic]), the About pane and the updater, and uv run python tools/build/check_version.py --tag v0.2.0 fails when a release tag disagrees with it (the workflow runs it before anything is built).

## Releasing

A release is a tag push or a workflow dispatch, never a local upload. .github/workflows/release.yml runs the full CI gate first, refuses a tag that disagrees with engine.__version__ (tools/build/check_version.py), builds, packs (pack_app.py, the same entry point you run locally) and publishes with vpk upload github --publish; the delta is computed from the previous release, downloaded in the same job. Pushing the same tag twice is not possible, and re-running a failed job reuses the same inputs.

1. Make sure CI is green on master.

1. Set the version in engine/__init__.py (__version__ = "0.2.0"); commit it. The About pane and the wheel metadata read it from there.

1. Tag with the matching number: git tag v0.2.0; git show v0.2.0 should carry the release notes summary.

1. git push origin v0.2.0. The workflow runs the gate, builds, packs, publishes a win release and attaches the portable zip and SHA256SUMS.txt. For a prerelease, use v0.2.0-rc.1 — it builds for the win-beta channel and publishes as a pre-release, so prerelease feeds never leak into the stable updater.

- prerelease = win-beta job: -rc/-beta tags pack with --channel win-beta, producing assets.win-beta.json and a win-beta release marked pre-release. Everything names the channel (DataverseDocent-win-beta-Setup.exe, DataverseDocent-0.2.0-rc.1-win-beta-full.nupkg, RELEASES-win-beta), because vpk derives every file name from --channel - pack and upload with mismatched channels is the one misconfiguration that produces a release nobody can see. Upload goes from assets.win-beta.json: Setup.exe, portable zip and the nupkg, so poe check-pack --channel win-beta knows exactly what to verify. Stable tags pack win as before.

- Dispatch instead of tagging: Actions → Release → Run workflow with version: 0.2.0 (it creates the tag from the dispatched commit, or reuses the existing one). This re-runs a failed release without a second tag.

- Delta base: the job downloads the latest release of the same channel first, so releasing on schedule gives delta updates of a few MB. The summary step prints the delta size against the full package.

- Yanking a bad release: delete the GitHub release (Assets disappear; the tag may stay or go). Installed copies stop seeing it as an update once the feed regenerates; users can reinstall the previous version manually by downloading its Setup.exe. If the bad version applies a broken update in-app, the recovery is the previous full package, which is still on the release page.

- The release is a draft under the hood: vpk upload github publishes only with --publish; the flag is in the workflow, so an aborted job leaves a draft release you can complete or delete, never a half-published one visible to the updater.

- Permissions: the job requests contents: write and nothing else; github.token authors the release (no PAT, nothing to rotate). The feed flips from 404 to visible as soon as the repo is public (see bead dv-hcg.39).

## UI conventions

The shared kit in ui/widgets.py and the theme in ui/theme.py are the only sources of the app's look. A new view builds its controls through the kit; it does not invent its own stylesheet.

RuleHow|  |  |
| --- | --- |

One table and tree contractAppTable (a table), AppTree (a model-driven tree) and AppTreeWidget (a tree with cell widgets) — see Table component contract. A view that needs a different table subclasses one of them, it does not build a QTableWidget from scratch.|  |  |

One layout ownerTableLayout (ui/table_layout.py) per header. Never wire sectionResized straight to a save: a programmatic fit would overwrite the user's layout. A change counts as a user gesture only when the user could have caused it — the kit ignores a section the layout owns (stretch, fixed, or a stretched last section).|  |  |

One type scaleA label wears a token (its object name is the token) or takes its size from the theme's FONT_* constants. A raw font-size: Npx outside theme.py fails ui/tests/test_type_scale.py.|  |  |

One heading contractmake_page_heading() for a full-page title, make_section_heading() inside a page, make_card_title() on a card. All of them set an object name; none writes an inline stylesheet.|  |  |

One reset affordancemake_reset_columns_button(name) — the same ghost button with the rotate-ccw icon everywhere.|  |  |

One glyph per roleEvery mark that stands for an action, a state or a direction is a bundled Lucide asset from ui/assets/lucide/, tinted from a theme role, and named through ui.icons.ICON_ROLES (a role says what the mark is for: refresh, back, sidebar_hide, more…). A text character (×, ⋯, ✓, ▸) is never a stand-in for one, and neither is a hand-drawn path. There are three shapes: make_icon_button(glyph, tip=...) for an icon-only button (reset, stepper, chip delete), make_icon_text_button(label, glyph) for a labelled one (Reinstall), make_refresh_button(label) for the app's one refresh. Add the asset — same 24×24 face, stroke="currentColor", round caps — when a role has no glyph yet. ui/tests/test_icon_inventory.py fails on an unresolved name or a glyph-character button, and ui.icons.icon() warns once for an unknown name instead of returning a silent null icon. Two exceptions, both deliberate: the window caption buttons (QStyle.StandardPixmap, so they match the real Windows title bar) and the column-drag affordance, which stays the platform's own resize cursor — a painted grip on every header section would be permanent chrome for a gesture the cursor already announces.|  |  |

Colours come from the themeNo hex literal outside ui/theme.py (enforced by ui/tests/test_theme_tokens.py).|  |  |

Palette, then role, then componentOnly ui/theme.py and ui/widgets.py may name a palette entry. A view names a role (SURFACE_CARD, TEXT_DANGER, ACCENT_PRIMARY) — what the colour is for. The kit builds the component. A theme swap is then a table edit, not a hunt through views.|  |  |

One contrast contractThe pairings the app paints live in theme.CONTRAST_PAIRS and theme.BADGE_CONTRAST_PAIRS, with the ratio each must clear (text 4.5:1, graphics 3:1, disabled 3:1). ui/tests/test_contrast.py reads that table, so a palette change that breaks legibility fails the build. Add a pairing there rather than leaving it implicit at a call site.|  |  |

One button systemmake_action_button(text, kind=..., size=...) for every action button. The app-level rule and the widget-level copy both come from theme.button_qss(), so they cannot drift. The kinds are primary, secondary, ghost, chip, cell (a table action cell), link (a left-aligned brand row that navigates) and nav-active/nav. Never call action_button_style() from a view, and never hand-write a QPushButton rule.|  |  |

Labels wear tokensSet the object name (HeadlineLG, BodyMD, CaptionSM, MonoSM, HintSM, AccentSM, SuccessSM, WarningSM, DangerSM, LabelStrongSM) or use the kit's label builders; never paint a label's colour or size. A label whose text changes at runtime changes its object name and re-polishes.|  |  |

No inline stylesheets in a viewA view asks the theme for a rule (page_background_qss(), transparent_surface_qss(), surface_frame_qss(), input_qss()) or the kit for a component. A literal or an f-string in a view fails ui/tests/test_theme_conformance.py. The one escape is an explicit # theme-allow: marker on the line, with a reason.|  |  |

Kit-only inputsmake_line_edit(), make_search_field(), make_multiline_input(), make_plain_text_view(), make_list(), make_checkbox(), make_progress_bar(), make_combo(). A view never constructs a raw QLineEdit, QTextEdit, QListWidget, QCheckBox, QProgressBar, QComboBox or QPushButton. make_checkbox() returns the kit's AppCheckBox, which paints its own indicator — a 16px rounded square (RADIUS_SM) carrying the Lucide check asset in ON_PRIMARY when checked, so a check box never reads as a chosen radio button. The three faces (unchecked, checked, disabled) come from AppCheckBox.face_colours(), and ui/tests/test_checkbox_face.py reads the rendered pixels at 2x to prove the corner radius and the glyph.|  |  |

One badge vocabularymake_badge(text, label=...) — the label picks the role, so two badges of the same family never drift apart. Pass explicit role colours only when the badge is a known state (PASS / FAIL / SKIP).|  |  |

## Component gallery

The gallery (ui/gallery.py) shows every kit component on one page: the type scale, the role swatches, the button kinds and sizes, the badge roles, the standard inputs, the containers and the data components. It is the app's visual contract in executable form — when the theme changes, the gallery changes with it.

```
python main.py --gallery          # open the gallery
python -m ui.gallery               # the same, standalone
```

The gallery is itself a view, so it obeys the same rules as every other one: it names roles, not palette entries, and it builds components, not raw widgets. It is also the first thing to look at when a component looks wrong, because it puts that component next to every other one instead of in the middle of a page.

Adding a component? Add it to the kit, then add it to the gallery. ui/tests/test_gallery_contract.py checks that the gallery still builds, still shows a component of every kind, and that every button in it wears one of the theme's button object names — the gallery may not show a button the app cannot produce. The same suite covers the app-sheet/scoped-sheet agreement (promoted from the deleted button probe).

## Qt pitfalls

The bugs this app had were mostly Qt behaviours working exactly as documented. These are the ones that bite.

| Pitfall | What Qt does | What to do |
| --- | --- | --- |
| A widget-level stylesheet shadows the app-level one | Setting a stylesheet on a widget replaces the application stylesheet for that subtree. The app's QHeaderView::section rules stop applying inside a table that has its own sheet. | Repeat the rules from the theme's mixins: header_section_qss(flush=) and scrollbar_lane_qss(scope=) in ui/theme.py. One source, so the two sheets cannot drift. |
| sectionResized fires before the new size lands | Reading header.sectionSize(i) inside the handler returns the old value. A synchronous copy persists stale widths, and the last column's label drifts off-centre. | Defer the work: QTimer.singleShot(0, self._fit_queue_columns). |
| Children are not clipped to a parent's border-radius | A table flush inside a card paints its own corners, so a rounded card edge shows a notch where the table's square corner sits. | Flush tables and trees paint square top corners (they meet the card's top bar) and take the card's bottom radius themselves; the header's end caps stay square for the same reason. |
| A filled scrollbar lane paints over the card's corner | The vertical scrollbar's lane inherits the page colour, so the card's border ends in a white notch at the bottom right. | Keep the lanes transparent (scrollbar_lane_qss) so the card's own surface shows through; thumbs and grooves keep coming from the global theme. |
| An ancestor's background bleeds through a transparent widget | A styled lavender ancestor makes a table body transparent, and the rows render page-coloured instead of white. | Set the background explicitly in the widget's own sheet (flush_table_style()). |
| Qt derives cell-widget geometry from the item content box | With a stylesheet active, the app's QTableWidget::item rule (padding + border) shrank every action cell, clipping the buttons inside it. | Zero the vertical padding for the action cells (QTableWidget::item { padding: 0px 12px; }). |
| Combo popup rows ignore the QSS item metrics | The app sheet declares QComboBox QAbstractItemView::item with min-height 22px + 6px padding (~34px), but the popup sizes items through its delegate, not the stylesheet — rows painted at ~20px and clipped descenders. | The kit installs _ComboPopupRowDelegate (ui/widgets.py): the row height is max(34, fontMetrics().height() + 12), so rows meet the menu contract at 100% and at Windows display scaling. Fixed pinned padding, not the QSS rule. |
| QHeaderView.lastVisibleSection() does not exist in PySide6 | Calling it raises AttributeError. | Walk the header: logicalIndex(v) over the visual range, then isSectionHidden(logical). |
| App-level QSS does not reach a label that has its own stylesheet | The label's own sheet wins for the properties it sets; the app's token rule still supplies the rest, but a label that sets font-size itself has left the type scale. | Set the object name to the token and leave the stylesheet empty — that is what make_* builders do. |
| The offscreen platform has no fonts | Every glyph renders as tofu, so a text measurement says nothing. | Verify layout by geometry and pixels (section sizes, viewport widths, corner colours), never by the rendered text. |
| Native sort indicator strays | The style CE_HeaderSortIndicator paints at section top-centre under the header QSS, not beside the label; no QSS position or nested QPainter fixes it. | Use SortArrowHeaderView (ui/widgets.py) — arrow as child-label overlay, refreshed on paint; stock sort state is kept. |
| A click on the header widget never reaches the header | QHeaderView is a QAbstractItemView: its mouse handling lives on the viewport. QTest.mouseClick(header, ...) therefore emits no sectionClicked — not even with a stock QTableWidget — while QTest.mouseClick(header.viewport(), ...) sorts normally. | Click the viewport, or send the press/release pair to it (ui/tests/test_header_sort.py). The kit's arrow is a child label over the section and is transparent for mouse events, so QApplication.widgetAt() at the arrow returns the viewport — that is the click a curator makes. |
| QFont point size vs QSS pixel sizes | apply_theme() sets QFont point size 9 while QSS tokens paint 11–22px; measures and paint disagree, elision can drift. | Known open mismatch, tracked as bead dv-06b. |
| A QThread destroyed while it is still running aborts the process | Qt prints QThread: Destroyed while thread is still running and calls abort(). A worker parented to a widget dies with that widget — so quitting the app while the extensions scan is walking the installed packages killed the process, and an offscreen probe that ended with a worker live died the same way. | Register every worker with ui.workers.register_worker() and check isInterruptionRequested() between steps. Two hooks stop them: QApplication.aboutToQuit (the app quitting) and an atexit hook (the process ending without a clean quit). The registry lives in ui/workers.py; a new worker class must register itself. |

## UI probes

The probes in tools/probes/ are the pixel-and-geometry checks behind the table bugs. Each one runs offscreen against a throwaway workspace, prints a PASS/FAIL line per check and exits non-zero on a failure.

```
python tools/probes/run_all.py                # every probe, one command (what CI runs)
python tools/probes/probe_queue_columns.py    # the queue's columns fill the viewport, never clip
python tools/probes/probe_manifest_columns.py  # the manifest fits, persists the user's widths, resets
python tools/probes/probe_headings.py          # every full-page heading wears the same token
python tools/probes/probe_card_corner.py       # a card's bottom-right corner stays connected
```

The other probes cover the Auto-Checks and Metadata rows, the Extensions table, finding dispositions, the preview card, the About updates section, the navigation rail, the review rules table, the gallery's input controls, the icon sheet, review-row selection, the two rule cards, the entry-check params form and the two check sections; tools/probes/README.md lists all of them with the contract each one checks.

CI runs the probes. The workflow has a second job, probes, that installs the requirements and runs python tools/probes/run_all.py offscreen. The runner executes every probe_*.py and exits non-zero when any of them failed, so the pixel-and-geometry checks are part of the build rather than a habit.
The temp-workspace rule. A probe must never write to the user's workspace/table_layout.json: a probe that saves there leaves the real app with a layout nobody chose. tools/probes/_common.py:boot() points cfg.app.workspace at a fresh temp directory and applies the theme; every probe goes through it. A new probe must do the same, and must stub out anything that would reach the network (the manifest probe replaces _on_load_metadata).
A Qt message is a defect until it is classified. Qt does not raise on a stylesheet it cannot parse: it logs Could not parse stylesheet of object QLabel(...) and drops the sheet, so the widget renders without its face and the page looks almost right. That is how a badge with one closing brace too many stayed invisible (bead dv-bjj): the only symptom was a line on stderr, and nothing failed. Both gates now record every Qt message and fail on an unclassified one — tools/probes/_common.py installs a qInstallMessageHandler (the probe report fails, and run_all.py repeats the messages in its summary) and pytest-qt's qt_log_level_fail = "WARNING" fails the test that emitted it. Exactly two messages are allowed, because they come from the environment and not from this app: QFontDatabase: Cannot find font directory (the offscreen plugin has no fontconfig; both bootstraps point QT_QPA_FONTDIR at the platform's fonts first) and This plugin does not support propagateSizeHints() (the offscreen plugin cannot ask a window manager about a fixed size). Adding a third to the allowlist is a decision with a reason, not a way to make a run quiet: probe_qt_warnings.py proves the gate by provoking a broken sheet and requiring that it is caught.

The same contracts live in ui/tests/ as pytest suites, so CI runs them: test_table_layout.py (the controller), test_table_geometry.py (the queue's geometry), test_page_headings.py (the heading contract), test_type_scale.py (the type scale), test_contrast.py (the contrast contract), test_kit_stylesheets.py (every sheet builder emits balanced braces and no unsubstituted placeholder) and test_theme_conformance.py (the layering guards). The probes stay useful for the things pytest cannot see — a pixel colour at a card's corner, a screenshot to eyeball.

```
python -m pytest ui/tests -q              # the UI contracts
python -m pytest engine/tests -q          # the engine contracts
python -m pytest curation/tests -q        # the curation contracts
python -m ruff check ui/           # lint
```

ui/tests/conftest.py provides a session-scoped qapp and win (one offscreen application, one main window). The window is shared, so every test sets its own preconditions; a test that needs the dashboard on screen calls win._show_dashboard() first — the queue's fit is a no-op while the table is hidden.

## Planned: dark mode (beads epic: dv-4jm)

Dark mode is not implemented. It is tracked as beads epic dv-4jm (children dv-zds → dv-m2q → dv-m8m → dv-q7t → dv-ceb). Open the epic with bd show dv-4jm; it is the next planned step in the UI standardisation, recorded here so the ordering is explicit. Step 1 is done (the second role table, dv-zds): the role layer is a mapping per theme now, so the remaining steps select a table instead of rewriting the views. The app still paints light — there is no theme picker, and the stylesheet is not per-theme yet.

The reason it is now possible at all is the role layer. A dark theme is not a second set of colours scattered through the views — it is a second role table. The palette stays a palette (PRIMARY is still #004ccd); the roles decide what each palette entry is used for, and the role table decides which palette entry each role points at.

What a dark theme needs, in order:

1. A second role table. (done — dv-zds) The roles are a mapping rather than a flat set of aliases: TEXT_PRIMARY points at the light surface's ink in one theme and the dark surface's ink in the other. ui/theme.py now declares LIGHT_ROLE_TABLE and DARK_ROLE_TABLE (the same 94 role names in both), a ROLE_TABLES registry, and the resolver theme.role(name, theme=None); theme.set_active_theme(name) points the theme's own rules at another table. The light table is exactly what the app paints today — ui/tests/test_theme_role_tables.py proves the light mappings did not move, that both tables declare the same roles, and that the dark table clears the same contrast floors on its own surfaces.
1. A second contrast contract. The floors do not change (text 4.5:1, graphics 3:1), but the pairs do: every role pair in CONTRAST_PAIRS is redeclared for the dark theme and checked by the same test. A dark palette that fails legibility fails the build exactly as a light one does. (Step 1 already checks the dark table against those floors; the contract itself is still the light one.)
1. The app stylesheet, per theme. theme.global_qss() becomes global_qss(theme), and the kit's component chrome follows. The QSS that hardcodes a surface (the card faces, the scrollbar lanes, the table rows) is the part that has to be re-pointed at roles first.
1. The painted assets. The icons are tinted from a role, which already works; the app mark and the taskbar icon are the exception and need a dark variant.
1. The gallery, showing both. The gallery is where a theme is reviewed, so it should be able to show the light theme and the dark theme side by side. Every contrast decision becomes a glance instead of a judgement call.

Two things are deliberately not planned yet: a theme picker in Settings (the role table makes it possible, but it is a UX decision, not a refactor), and automatic switching by the operating system (the same, plus a preference to persist).

What is already done. The palette/role split, the second role table (step 1), the contrast contract and its test, the one button system, the conformance guards, and the gallery. None of them needs redoing for dark mode — they are the work that makes it a table edit instead of a re-skin.

## Conventions

- Python 3.11 typing, dataclasses; no external framework in engine/ (stdlib + listed deps). Checks are pure functions of local files — no network I/O inside engine/.
- Module-per-format naming mirrors the R scripts; keep Report contract in sync with schema changes — it is the interface between engine and GUI.
- Selectable dialogs (ui/dialogs.py:show_warning/show_critical/show_info) for traceback-bearing errors; log every request via applog.log_response; the Log page's QSyntaxHighlighter paints ERROR red, WARNING yellow, IPs, SQL keywords, XML tags, Java backtraces.
- Parent every QThread to its view, chain deleteLater, adopt before discarding (MainWindow._open_dataset) — never destroy a live QThread.
- Theme: no hardcoded hex outside theme.py (enforced by ui/tests/test_theme_tokens.py).
- Layers: palette → role → component. Only theme.py and widgets.py may name a palette entry; a view names a role and builds components (enforced by ui/tests/test_theme_conformance.py).
- Legibility: every pairing the app paints is declared in theme.CONTRAST_PAIRS / theme.BADGE_CONTRAST_PAIRS and checked (enforced by ui/tests/test_contrast.py).
- Buttons: one system. make_action_button() in a view, theme.button_qss() as the single generator, never a hand-written QPushButton rule.
- Labels: tokens, not painted styles. The object name carries the token and the theme owns the rule; a label that changes at runtime changes its token.
- Type scale: no raw font-size: Npx outside theme.py (enforced by ui/tests/test_type_scale.py); a label wears a token.
- Tables: one controller per header (ui/table_layout.py); only user gestures are persisted; a programmatic fit runs inside layout.suppressed().
- Interface text: no hardcoded copy outside ui/assets/strings.json (enforced by ui/tests/test_strings.py). Add a catalogue key first, then reference it with t().
- Performance constants are measured, not guessed: the queue's painting window is benchmarked by tools/perf/bench_paint_window.py (25k synthetic rows) and the enrichment cap by tools/perf/bench_enrichment_cap.py (5k synthetic collection, simulated GET latency, exact fetch count). Both print --markdown tables. Re-run them before changing a cap, and record the numbers in the constant's comment and the decision log.
