# Dataverse Docent

Desktop curation assistant for Alliance Dataverse instances. It pulls datasets submitted for review, lets the curator approve a download, runs automated format-specific checks on the files, checks metadata completeness, and presents per-file and dataset-level findings in a desktop GUI with an exportable curation report.

## Status

- Phase 0 — scaffold complete
- Phase 1 — R-to-Python engine port: **21 check modules ported, 291 tests passing** (`docs/html/engine-port.html`; MATLAB `.mat` deferred to keep `scipy` optional; run `pytest --collect-only -q` for the current count)
- Phase 2 — report runner complete: `python main.py --headless <dir>` produces the `DatasetReport` JSON end-to-end (`engine/runner.py:run_report`)
- Phase 3 — Dataverse client + download manager complete: total-driven paginated Search discovery (draft-aware, `per_page=1000`) with in-process pooled inventory enrichment, per-dataset `IN_REVIEW` lock confirmation, approval-gated zip download with streaming, original-format fetch for tabular ingests, skip-if-staged, checksum verification with `.tab` warnings (not errors), zip-slip guard; live-verified against `https://demo.borealisdata.ca`
- Phase 4 — PySide6 GUI complete: dashboard (12 sortable/column-togglable columns with pill delegates, status/label/collection filters, content-width auto-fit with visible resize handles and reset-to-defaults), dataset detail (main column: completeness/manifest/auto-checks/version-log cards; sticky sidebar: sections nav, dataset timeline, assessment that pushes curation labels), settings/about stack panes, Log stack page with severity legend + Live toggle, selectable text + table copy everywhere
- Phase 5 — packaging complete: PyInstaller lite build (onedir folder, all 21 checks lazy-import optional libs) beside a full onedir build whose heavy libs the lite exe picks up; `Makefile` targets `build` / `rebuild-lite` / `build-full`
- **All planned phases complete** (291 tests: 200 engine + 91 UI). Remaining work is queued but does not block the app — the live plan is `docs/html/proposals.html`: a live authenticated pass, two P1 UX items, measuring the painting-window/enrichment-cap constants, and an installer.

## Context

The app is built on two existing projects:

| Project | Role in this app |
| --- | --- |
| [CUR_Res_CurationTools](../CUR_Res_CurationTools) | R inspection scripts and functions ported into the Python check engine |
| [rdm-review-dashboard](../rdm-review-dashboard) | Reference for Dataverse interaction, review workflow state, and reviewer/admin access patterns |

Design decisions: native PySide6 desktop app (single process), API-token authentication against the Dataverse Native/Search API, SQLite for local state, PyInstaller packaging. See `docs/html/architecture.html`.

## Repository layout

```
dataverse-curation-app/
├── docs/html/            # documentation (source of truth): architecture, engine port, checks, dataverse, report contract, dev, user guide
├── engine/               # Python check engine (ports of the R inspectors)
│   ├── checks/           # one module per format (21), plus base.py/_util.py
│   ├── report.py         # DatasetReport JSON contract
│   ├── dispatcher.py     # extension -> check mapping
│   ├── runner.py         # run_report / list_planned_checks
│   └── tests/            # pytest suite (200 tests; see CI)
├── ui/                   # PySide6 views (main window, dashboard, detail, settings/about panes, log page, workers, dialogs, theme, widgets incl. AppTable content-fit, progress ring)
├── dataverse_client.py   # Native/Search API client (total-driven paginated search + pooled inventory enrichment, versions/compare/timestamps/notifications/curation labels)
├── download_manager.py   # approval-gated downloads, originals, skip-if-staged, verify (ok/problems/warnings)
├── metadata_check.py     # citation-block completeness (McMaster / Minimal profiles)
├── applog.py             # in-memory request log (Log page)
├── storage.py            # SQLite local state + JSON caches (sizes, labels, table layout)
├── main.py               # entry point (GUI + --headless)
└── config.example.json   # configuration template (copy to config.json)
```

## Quick start (development)

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy config.example.json config.json   # Windows cmd (PowerShell: Copy-Item config.example.json config.json); default is the Borealis demo (demo.borealisdata.ca); edit base_url/api_token for your instance
pytest                        # 291 tests (run pytest --collect-only -q for current count)
python main.py                # launch the desktop GUI — pick the Dataverse in the top-nav Settings page (demo preset included)
# headless against a staged directory (--dataverse/--config are GUI-only):
python main.py --headless <staged_dir> --out report.json --format json --persistent-id doi:10.5072/FK2/EXAMPLE
```

Requirements: Python 3.10+ (Windows recommended). `make` needs Git Bash on Windows; without it, run `.\build-lite.ps1` in PowerShell (same flags as `Makefile:rebuild-lite`). Headless exit codes: 0 clean, 1 error-level findings, 2 usage/IO failure. R is only needed for parity verification against the original scripts during the port phase, not at runtime.

## Packaging (portable)

```bash
make build         # both: lite onedir + full onedir folder in dist/
make rebuild-lite  # lite folder only (~2 min), keeps dist/curation-app-full/
make build-full    # onedir folder only
```

Outputs: `dist/curation-app-lite/curation-app-lite.exe` (onedir folder, fast launches — common formats JPG/PNG/PDF/XML/XLSX/TIFF bundled, work offline) next to `dist/curation-app-full/` (heavy libs pyreadstat/netCDF4/h5py/scipy — run its exe directly for SPSS/SAS/Stata/NetCDF/HDF5/MAT). Missing optional libs report “Missing …” in the Auto-Checks card rather than failing; JPG/PNG/GIF/BMP/WEBP fall back to a stdlib header parse when Pillow is absent.

## Documentation

- `docs/html/architecture.html` — components, threading, storage, packaging
- `docs/html/engine-port.html` — R-to-Python port matrix and go/no-go criteria
- `docs/html/checks-reference.html` — what each auto-check examines, PASS semantics, issue taxonomy
- `docs/html/dataverse-integration.html` — Native/Search API endpoints, auth, discovery + download flow
- `docs/html/report-contract.html` — the JSON report format shared by engine and GUI
- `docs/html/development.html` — setup, testing, adding checks, packaging
- `docs/html/user-guide.html` — how a curator uses the app (dashboard, detail, metadata, log)
- `docs/html/proposals.html` — proposed but not yet implemented changes (queued UX work, deferred checks, open decisions)

## Roadmap

1. Port spike: prove the Python port matches the R inspectors on the sample data in `CUR_Res_CurationTools/data/` — **done**
2. Check engine: implement all format checks, emit `DatasetReport` JSON — **done**
3. Dataverse client and download workflow (approval + checksums) — **done**
4. PySide6 GUI: dashboard, dataset detail, settings/about panes, report view, log strip — **done**
5. Packaging: PyInstaller build (lite/full) and installer — **done** (Inno Setup / WiX optional)

## License

MIT — see [LICENSE](LICENSE). The engine checks are ported from the MIT-licensed `CUR_Res_CurationTools` (© 2026 Curation Services Team, Digital Research Alliance of Canada); see LICENSE for full third-party attributions.
