# Dataverse Docent — Documentation

Desktop curation assistant for Alliance Dataverse instances: pulls datasets submitted for review, runs automated format checks, checks metadata completeness, and presents findings with an exportable curation report. This site is built from the Markdown tree in `docs/` by Zensical; the retired hand-authored HTML lives in `docs/html/` for reference only.

22 check modules550 testsPySide6 desktopEngine v0.2.0Verified vs code 2026-11-16

## Start here

### 🗺 Architecture

Components, threading, data flow, storage, the UI layering contract (palette → role → component), the table contract, packaging, decision log.
Read →

### 🔍 Checks reference

What each of the 22 auto-checks examines, PASS semantics, issue taxonomy.
Read →

### 🪪 Entry correctness

The looks_correct rule handler: nine entry checks for depositor metadata (length, pattern, blocklist, vocabulary, dates, URLs), what ships enrolled (nothing), and how to enroll it in phases.
Read →

### 🔌 Dataverse integration

Endpoints, auth, discovery, curation labels, download flow, retries.
Read →

### 📄 Report contract

The DatasetReport JSON shared by engine, GUI, and headless mode.
Read →

### 🔄 Engine port

R → Python port matrix, divergences, go/no-go criteria.
Read →

### 🧭 User guide

Dashboard, dataset detail, workflow steps, log, troubleshooting, headless.
Read →

### 🛠 Development

Setup, layout, adding a check, UI conventions, the component gallery, Qt pitfalls, probes, the planned dark-mode step, packaging.
Read →

### 📌 Proposals

The remaining plan by bucket — queued UX, verification, deferred checks, packaging, open decisions — plus the shipped record.
Read →

### ⚖️ Decision records

The repository-level decisions — toolchain, layout, packaging, token storage — as short, dated ADRs in docs/adr/.
Read →

## Project status

Snapshot 2026-11-18 - all six phases complete. The app is feature-complete for its documented scope: 22 check modules, 969 tests (77 engine + 345 curation + 26 tools + 521 UI), 21 UI modules. Discovery is total-driven Search at per_page=1000 plus pooled in-process inventory enrichment (no crawler dependency); the dashboard, dataset detail, downloads, auto-checks and export paths work end-to-end; one onedir build is packaged as a Velopack installer; startup paints and reveals the shell before cache/network work (~1 s warm, measured via DOCENT_STARTUP_LOG), so no blank frame or title-bar flash precedes it. The remaining plan is queued, not blocking — see below.

0ScaffoldRepo, GUI shell, storage done
→
1Engine port22 checks, 969 tests done
→
2Report runnerrun_report end-to-end done
→
3Client + downloadsSearch + enrichment, approval gate done
→
4PySide6 GUIDashboard, detail, settings, log done
→
5PackagingOne onedir build + Velopack installer done

## Remaining work at a glance

Nothing open blocks the app. The plan is queued in beads (bd ready / bd list — beads win on disagreement); Proposals points there.

| Bucket | Open items | Priority | Detail |
| --- | --- | --- | --- |
| Verification | Live authenticated pass — deferred until later, not a release blocker. Guest verification is done against the demo Borealis instance (a real Dataverse, not production); drafts and curation labels await a token | later | Proposals → |
| UX | Remaining P2s · step-4 quick wins · busy-indicator naming | P2–P3 | Proposals → |
| Performance | Both constants measured: painting window 2,000 rows confirmed (25k rows — ~0.9 s per repaint, ~7.6 s uncapped), enrichment cap 200 rows confirmed (5k collection, 100 ms GET — ~4 s per refresh, ~100 s uncapped) | done | Proposals → |
| Engine checks | MATLAB .mat and OCR parity (deferred); frdr/schema skipped by design | deferred | Proposals → |
| Packaging | Code signing (SignPath) — 0.2.0 ships unsigned with a documented SmartScreen click-through | milestone | Proposals → |
| Decisions | auth-fallback UX for refused datasets | call | Proposals → |

## Quick start

```
uv sync                                  # create .venv from uv.lock incl. dev group
copy config.example.json config.json   # PowerShell: Copy-Item config.example.json config.json
uv run pytest                            # 969 tests
uv run python main.py                    # GUI — pick the Dataverse in Settings
uv run python main.py --gallery          # the component gallery: every kit component on one page
uv run python main.py --headless <staged_dir> --out report.json --format json --persistent-id doi:10.5072/FK2/EXAMPLE
```

Requirements: Python 3.11+ (Windows recommended). Headless exit codes: 0 clean, 1 error-level findings, 2 usage/IO failure.

## Documentation audit — what was fixed

The documentation was re-checked against the code (engine/checks/__init__.py:registry, main.py CLI, engine/report.py, ui/ views, Makefile) on 2026-10-06 and 2026-10-07, when these HTML pages became the source of truth (the docs/*.md mirrors were retired), again on 2026-11-03 after the guestbook, section-help and startup batches, and on 2026-11-04 for the Settings dirty guard and dataset step rail. The tables below record the verified state.
| Stale claim | Where | Verified truth |
| --- | --- | --- |
| "20 check modules (19 R inspectors…)", "101 tests" | README, engine-port, development, user-guide | 22 registered modules (registry has 22 keys incl. format.secrets + inventory.access + inventory.extensions); 513 collected tests (218 engine + 295 UI) via full pytest --collect-only -q output (always sum the complete output) |
| Module list omitting secret_check | development layout | Added secret_check + missing engine files (constants.py, status.py, report_md.py) and UI files (review_config.py, checks_tree.py, icons.py) |
| test_audit_fixes.py “31 tests” | development | Collects 32 |
| "200 engine tests", "79 UI tests", "18 engine + 10 UI suites", test_dataverse 45, test_enrichment 9 | README layout, index layout, development | Recount 2026-11-12: 218 engine + 295 UI tests (513 total); 21 engine + 42 UI suites; test_dataverse 44, test_enrichment 14 |
| --format json|md|both missing | development layout, user-guide headless | Documented; run_report_to_file(..., fmt=…) verified in engine/runner.py |
| “Set/delete label not yet wired to UI” | dataverse-integration | Wired - Assessment Action pushes via set_curation_label (ui/dataset/actions_section.py:_on_commit) |
| “Log strip under the nav” | architecture, user-guide | LogPage is a stack page (ui/main_window.py:618), opened from the nav Log button / Ctrl+L; timer gated to page visibility |
| Storage caches omit dashboard_cache.json | development layout | Added (helpers live in ui/dashboard.py) |

## Repository layout

```
dataverse-curation-app/
├── docs/html/            # documentation (source of truth — edit these pages)
├── engine/               # Python check engine
│   ├── checks/           # 22 format modules + base.py / _util.py
│   ├── report.py         # DatasetReport JSON contract (+ Markdown export)
│   ├── report_md.py      # Markdown rendering
│   ├── status.py         # badge taxonomy (classify/summarize)
│   ├── constants.py      # shared scan caps (EngineCaps)
│   ├── dispatcher.py     # extension → check mapping
│   ├── runner.py         # run_report / run_report_to_file / list_planned_checks
│   └── tests/            # pytest suite (212 tests)
├── ui/                   # PySide6 views (21 modules, 242 tests)
├── curation/             # the app core — no Qt, no view imports (import-linter enforces both)
│   ├── client/           # client package: constants, errors, http, parsers, caches, downloads, DataverseClient
│   ├── download_manager.py # approval-gated downloads + verify
│   ├── metadata_check.py # citation-block completeness (McMaster / Minimal)
│   ├── review_rules.py   # versioned review rulesets (v2)
│   ├── response_draft.py # depositor-response draft builder
│   ├── dashboard_cache.py # Qt-free dashboard cache helpers
│   ├── applog.py         # in-memory request log
│   ├── config.py         # configuration load/save, presets, env overrides
│   └── storage.py        # SQLite local state + JSON caches
├── main.py               # entry point (GUI + --headless)
└── config.example.json   # configuration template
```

## How to use these pages

Each page is a single self-contained HTML file (inline CSS + inline SVG, no network needed). Open any of them directly in a browser, or serve docs/html/ statically. These pages are the editable source of truth — the docs/*.md markdown mirrors were retired on 2026-10-07.
