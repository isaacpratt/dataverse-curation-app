# User guide

The Dataverse Curation App is a desktop tool for curators reviewing datasets deposited in a Dataverse instance.

## First run

1. Launch the app (`dist/curation-app-lite.exe` or `python main.py`). If no `config.json` exists, the Settings page opens automatically.
2. Choose which Dataverse to work against:
   - **Dataverse preset** — pick *Borealis Demo — demo.borealisdata.ca* to test against the public demo instance, or *Custom…* for your own installation. The **Base URL** field is filled from the preset but remains editable for any other instance.
   - **Base URL** — e.g. `https://demo.borealisdata.ca` or `https://dataverse.your-installation.ca`. You can change this any time and the choice is saved.
   - **API token** — an admin/curator token for that instance (leave blank for public-only browsing; drafts/in-review require a token).
   - **Collection alias** — e.g. `mcmaster` for a sub-collection, or empty for the **whole repository**. The demo root alias is `dv` — an empty field is recommended when unsure (verified against Borealis v6.8.4-SP). Aliases `root`/`:root` are treated as empty.
   - **Workspace** — a local folder where downloads and reports are kept.
   - Use **Test connection** to `GET /api/info/version` and verify the URL before saving.
   - **Extensions tab** — per-package Install/Uninstall with installed sizes for the optional curation libraries, plus the optional Tesseract (OCR) and ExifTool (deep metadata) binary paths.
3. Save; the app contacts the selected Dataverse (paginated `GET /api/search?q=*&type=dataset&per_page=100&start=…&subtree=…` with dedup) and shows the dashboard. The current Dataverse + collection are shown in the status bar.

You can switch instances at any time via the **Settings** button in the top nav (or `Ctrl+,`). Save applies `config.json` and reloads the dashboard; Back discards. The **?** button opens a short **About** page. The last choice is persisted in `config.json` (next to the exe; see `config.example.json`). Headless/CLI runs operate on a local staged directory only (`--dataverse`/`--config` are GUI-only).

## Dashboard

Lists datasets from the paginated Search API (100 per page, up to 1000). Each of the **12 columns** is sortable (numeric/date sort via `_SortItem`), reorderable by drag, and resizable — right-click the header or use **Columns…** to toggle visibility. Status and Curation Label render as plain text.

| Column | Source |
| --- | --- |
| Title | `name`/`title` |
| Persistent ID | `global_id`/`identifier` |
| Contact | `contacts[].name` |
| Depositor | `datasetContact` / fallback `depositorName` (shown as separate column) |
| Date Created | `createdAt` |
| Date Published | `published_at` / `publicationDate` |
| Collection | `name_of_dataverse (identifier_of_dataverse)` |
| Files | `fileCount` |
| Size | `total_size_bytes` (humanized B/KB/MB/GB; "—" when the search record carries no byte total — exact sizes appear in the download quote) |
| Status | draft/review markers in `publicationStatuses` win over `versionState`; `In Review` confirmed via locks (`Draft`/`Published`/`In Review`/`Deaccessioned`) |
| Curation Label | per-draft label from the bulk report or `curationStatus` |
| Downloaded | local staging date from `state.db` + staged-folder mtime |

**Filter bar** above the table: free-text search across title, ID, contact, depositor, collection, curation label, plus **Status** (`All Datasets`/`Draft unsubmitted`/`Published`/`In Review`/`Deaccessioned` — draft markers anywhere in the search record count, so new versions being drafted on top of a published version still appear under Draft), **Curation label** (`All Curation Labels` + the connected instance's own set + `No label`), and **Collection** (`All collections` + every subcollection in the pull) combos. The label set is pulled fresh on every refresh via the [Curation Status API](https://guides.dataverse.org/en/latest/api/curation-labels.html) — bulk report first, then the allowed set from draft datasets (retried across several, since the endpoint needs `PublishDataset` permission) — and remembered with the pull in `<workspace>/curation_labels.json`). The Curation Label column shows each draft's current label; the dataset page header shows it as a pill with setter/time tooltip. Instances without labels configured just show "All Curation Labels" + "No label". The table is cached: each crawl is saved to `<workspace>/dashboard_cache.json` (per instance + collection), the next app open paints the cached rows instantly, and the background refresh only reports what changed (`N new, M updated, K removed` or `No changes — N dataset(s) up to date`). The progress label otherwise shows `X / Y dataset(s) shown — double-click a row to open`. Double-click a row (or use the visual row’s Persistent ID after sorting) to curate it.

Other controls: **Refresh** in the queue header (re-runs the paginated crawl), **Requirements** in the top nav (edit `requirements_profiles.json`), the **Log** toggle (`Ctrl+L`), **?** (**About** page).

## Curating a dataset (dataset detail)

Opening a dataset pushes the **Dataset detail** view onto the stack (back via the **Dashboard** tab, or `Alt+Left`). The header shows the title with the version-aware Dataverse link beside it (`…/dataset.xhtml?persistentId=…&version=DRAFT` for drafts — DOIs are not resolvable for drafts), plus ID, status, and curation-label pills and the depositor line.

The view has a **main column** and a **sticky right sidebar** (the sidebar keeps its own scroll position while the main column scrolls):

- Main column, top to bottom: **Metadata completeness** (every check with status, no internal scrollbars) → **File Manifest** (downloaded-checkbox column, Open-folder button, column widths remembered between sessions) → **Auto-Checks** (legend + planned checks with lib-availability, then actual results after a run) → **Version log** (every version + published→draft diff; "Initial draft" when there is no previous version) → raw metadata toggle.
- Sidebar, top to bottom: **Sections** (jump buttons scrolling each box to the top of the main column) → **Dataset log** (newest-first timeline) → **Assessment Action**.

**Metadata completeness** shows citation-block completeness for the selected **Requirements profile** combo (`McMaster` derived from `CurationLog.pdf`/`DepositorChecklist.pdf` or `Minimal`). Each row is Check (bold) / Value / Status (`✓ Complete` green vs `✗ Incomplete` red, requirement in the tooltip), with a summary `X/Y fields complete (ready for review / needs attention)`. Value is what the depositor entered; Requirement describes what is expected for the profile. Includes ORCID format check (`^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$`) and README detection via the file inventory. Change the profile to re-evaluate immediately.

**File Manifest** lists every file (from the staged dir if downloaded, otherwise from the Dataverse inventory). Columns: ✓ (downloaded), Filename (with `directoryLabel` subfolder), Size, Format, Scan Status. Click a row after checks to see its findings; **Open folder** reveals the staged directory in the file explorer.

**Raw metadata** (bottom toggle) shows citation blocks plus a `— Full JSON —` dump (capped 12000 chars) from `GET /api/datasets/:persistentId` — useful for curators verifying the stored metadata.

### Workflow steps

1. **Review metadata** — the detail auto-loads on open (`QTimer.singleShot(100)` via `MetadataWorker`); or click **Load metadata** (in the header button row) to re-fetch the file list and all fields without downloading. The inventory populates the manifest immediately.
2. **Review what changed** — if the dataset was published before, the **Version log** card lists all versions plus every metadata field that differs from the last published version (Previous vX → New Draft) and added/removed/replaced files. First-time submissions show “Initial draft”.
3. **Download** — click **Download All**. The app shows file count + total size first; datasets already fully staged are skipped with a verified notice instead of re-downloading. Nothing is downloaded until you approve in `DownloadApprovalDialog` (warning for very large datasets). Streaming download shows `X.Y MB` in the `QProgressBar`; tabular files additionally fetch their original uploads (`.sav`/etc., not just `.tab`); after download, checksums from the inventory are verified automatically (`DownloadManager.verify` — `.tab` mismatches are reported as notes with UNFs, not errors). Metadata, manifest, and reports live under `workspace/downloads/<id>/` (`metadata.json`, `file-manifest.json`, `reports/`) and reload instantly on next launch.
4. **Run checks** — click **Run checks** (`CheckWorker` dispatches every file to its format check; without staged files it tells you to download first). The `QProgressBar` is indeterminate and the status label shows per-file progress (`progress` signal).
5. **Inspect results**:
   - The **File Manifest** scan column updates (`Clean` / `Flagged`); the **Auto-Checks** card shows aggregated findings; **Metadata completeness** shows field-level completeness.
   - Click a file row to see its message + `details` tooltip.
6. **Export report** — **Export report…** saves the full `DatasetReport` JSON (defaulting to `workspace/downloads/<id>/reports/`) via `DatasetReport.save()`; the JSON can be handed off to the review dashboard workflow. Without a report it tells you to run checks first.

All text (labels, table cells via `Ctrl+C`, log lines, dialogs) is selectable and copyable.

## Notes on checks

- Checks matching the file format run automatically; files with no applicable check (unknown extension) are listed but not inspected (`no checks`).
- **Lite build** excludes heavy libs (`pyreadstat`, `netCDF4`, `h5py`, `tifffile`, `Pillow`, `pypdf`, `lxml`, `openpyxl`, `scipy`). Missing libs are reported as `Missing: pip install …` in the **Curation checks** tab and as a warning `CheckResult` in the report — not a failure. Install the lib or use the full build to enable those checks.
- OCR (PDF text extraction) and deep exif metadata are optional: without tesseract/exiftool they report “not executed”.
- All check definitions come from the curation toolbox; parity with the R inspectors is maintained by 53 tests (`docs/engine-port.md`). See `docs/checks-reference.md` for what each check examines and what PASS means.

## Log and troubleshooting

A **Log** strip under the top nav bar (toggle with the **Log** button or `Ctrl+L`) shows an in-memory ring buffer (`applog.py`) of every Dataverse request (`GET <url> → <status> (<ms>) <summary>`), plus worker messages. Syntax highlighting (INAV-style) colors `ERROR` red, `WARNING` yellow, IPs, SQL keywords, XML tags, Java backtraces, and quoted strings; lines containing `ERROR`/`WARN` get higher priority. The header bar holds a **● Live** toggle (pause to freeze the view for inspection — click again and buffered lines catch up), Clear, and hide buttons. The panel polls every 800 ms (`QTimer`) while live and supports copy.

Selectable error dialogs (`ui/dialogs.py`): all `show_warning`/`show_critical` text can be selected/copied — important for pasting tracebacks.

| Symptom | Fix |
| --- | --- |
| `401` from Dataverse | Token expired/insufficient; regenerate in Dataverse → top-nav **Settings** |
| `ConnectionResetError 10054` | Transient close — retries 3× automatically; check VPN/proxy, then retry |
| `400 invalid collection alias` | Alias not found — try empty (whole repository) or verify spelling (`dv` is the Borealis root, not `borealis`) |
| Empty dashboard | No datasets for `q=*&type=dataset` in that `subtree`; widen the collection in Settings; without a token only published are returned |
| Check “Missing: pip install …” | Optional lib absent in lite build — `pip install <pkg>` in dev, or use full build |
| Check “not executed” | Optional tool missing; install tesseract/exiftool and set the path in Settings |
| `ContextualVersion` 406 | Missing `&` before `persistentId` in versioned URL — fixed; re-pull if you saw this on an old build |
| Download interrupted | Re-download; previous stage is cleaned up, prior reports are kept |
| Checksum mismatch on `.tab` files | Expected for tabular ingest products: Dataverse regenerates `.tab` bytes server-side, so the stored checksum can predate the download. Compare the file's UNF (shown in the message) against Dataverse, or download the original format (e.g. `.sav`) for a byte-exact check. Other formats mismatching indicate real corruption or transit alteration — re-download first |
| `NameError: QWidget` in Settings | Fixed in 2026-08-26 build — re-unzip `curation-app-lite-win.zip` |

## Headless mode

```bash
python main.py --headless <staged_dir> --out report.json
python main.py --headless <staged_dir> --out report.json --persistent-id doi:10.5072/FK2/EXAMPLE
```

Walks the staged dir and writes `DatasetReport` JSON without launching the GUI (same `engine/runner.py:run_report`). `--dataverse`/`--config` are GUI-only: headless operates purely on local files and rejects those flags.
