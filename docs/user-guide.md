# User guide

The Dataverse Docent is a desktop tool for curators reviewing datasets deposited in a Dataverse instance.

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

Lists datasets from the paginated Search API (100 per page, up to 1000). Each of the **12 columns** is sortable (numeric/date sort via `_SortItem`), reorderable by drag, and resizable — the header shows a visible divider on each column edge (highlighted on hover/press) for dragging; right-click the header or use **Columns…** to toggle visibility. On first paint every column auto-sizes to its content (scaled down proportionally if the total would overflow the window, since the queue has no horizontal scrollbar). Dragging any column edge locks the layout to your widths; **Columns… → Reset columns && sorting** restores the defaults and re-enables auto-fit. Saved widths always win over auto-fit across restarts. Status and Curation Label render as plain text.

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

**Filter bar** above the table: free-text search across title, ID, contact, depositor, collection, curation label, plus **Status** (`All Datasets`/`Draft unsubmitted`/`Published`/`In Review`/`Deaccessioned` — draft markers anywhere in the search record count, so new versions being drafted on top of a published version still appear under Draft), **Curation label** (`All Curation Labels` + the connected instance's own set + `No label`), and **Collection** (`All collections` + every subcollection in the pull) combos. The label set is pulled fresh on every refresh via the [Curation Status API](https://guides.dataverse.org/en/latest/api/curation-labels.html) — bulk report first, then the allowed set from draft datasets (retried across several, since the endpoint needs `PublishDataset` permission) — and remembered with the pull in `<workspace>/curation_labels.json`). The Curation Label column shows each draft's current label; the dataset page header shows it as a pill with setter/time tooltip. Instances without labels configured just show "All Curation Labels" + "No label". The table is cached: each crawl is saved to `<workspace>/dashboard_cache.json` (per instance + collection), the next app open paints the cached rows instantly, and the background refresh only reports what changed (`N new, M updated, K removed` or `No changes — N datasets up to date`). The status pill at the bottom of the dashboard carries `<base URL>/<alias>: X/Y datasets shown` (instance scope + filtered count), then — after a dot — the contextual message (`Double-click a row to open it`, load progress, or an error); the row ends with the 32×32 Docent mark at the bottom-right. Double-click a row (or use the visual row’s Persistent ID after sorting) to curate it.

Other controls: **Refresh** in the queue header (re-runs the paginated crawl), **Review configuration** in the top nav (edit review rulesets + response templates in `requirements_profiles.json`), the **Log** toggle (`Ctrl+L`), **?** (**About** page).

## Curating a dataset (dataset detail)

Opening a dataset pushes the **Dataset detail** view onto the stack (back via the **Dashboard** tab, or `Alt+Left`). The header shows the title with the version-aware Dataverse link beside it (`…/dataset.xhtml?persistentId=…&version=DRAFT` for drafts — DOIs are not resolvable for drafts), plus ID, status, and curation-label pills and the depositor line.

The view has a **main column** and a **sticky right sidebar** (the sidebar keeps its own scroll position while the main column scrolls):

- Main column, top to bottom: **Metadata check** (every check with status, no internal scrollbars) → **File Manifest** (downloaded-checkbox column, Open-folder button, column widths remembered between sessions) → **Auto-Checks** (legend + planned checks with lib-availability, then actual results after a run) → **Version log** (every version + published→draft diff; "Initial draft" when there is no previous version) → raw metadata toggle.
- Sidebar, top to bottom: **Sections** (jump buttons scrolling each box to the top of the main column) → **Dataset log** (newest-first timeline) → **Assessment Action**.

**Metadata check** shows rule-driven completeness for the selected ruleset (`McMaster` derived from `docs/CurationLog.pdf`/`docs/DepositorChecklist.pdf` or `Minimal`, plus any custom rulesets). Each row is Check (bold) / Value / Status (`✓ Complete` green vs `✗ Incomplete` red, requirement in the tooltip), with a summary `X/Y fields complete (ready for review / needs attention)`. Value is what the depositor entered; Requirement describes what is expected for the profile. Includes per-author ORCID format checks (every author must carry a valid `^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$`), an Author count row (`N authors: A; B (+M more)`), a License and Terms of Use row (license name + termsOfUse/termsOfAccess from the version), and README detection via the file inventory. The Value column can be drag-resized against Status. Change the profile to re-evaluate immediately. Rules are edited on the **Review configuration** page (top nav): the left column marks each metadata field from the Dataverse metadatablocks catalog as Required / Optional / Not checked and manages text-search rules (filenames, metadata values, staged file contents — e.g. README); License / Terms of Use / Terms of Access group under **License and Terms of Use**; the right column edits the standard response text per rule plus the draft header/footer. Rulesets apply per Dataverse (`*` = all instances) and are stored as `requirements_profiles.json` v2 next to the executable.

**File Manifest** lists every file (from the staged dir if downloaded, otherwise from the Dataverse inventory) with more horizontal room (main column takes most of the width). Columns: Name (folder > file > check tree), Size, Format, Scan. Restricted files, embargo dates, retention dates, and tabular ingest status/errors from the inventory appear in the name/scan tooltips. Click a row after checks to see its findings; **Open folder** reveals the staged directory in the file explorer.

**Raw metadata** (bottom toggle) shows citation blocks plus a `— Full JSON —` dump (capped 12000 chars) from `GET /api/datasets/:persistentId` — useful for curators verifying the stored metadata.

### Workflow steps

1. **Review metadata** — the detail auto-loads on open (`QTimer.singleShot(100)` via `MetadataWorker`); or click **Load metadata** (in the header button row) to re-fetch the file list and all fields without downloading. The inventory populates the manifest immediately.
2. **Review what changed** — if the dataset was published before, the **Version log** card lists all versions plus every metadata field that differs from the last published version (Previous vX → New Draft) and added/removed/replaced files. First-time submissions show “Initial draft”.
3. **Download** — click **Download All**. The app shows file count + total size first (tabular files quote the original upload size when known); datasets already fully staged are skipped with a verified notice instead of re-downloading. Nothing is downloaded until you approve in `DownloadApprovalDialog` (warning for very large datasets). Streaming download shows `X.Y MB` in the `QProgressBar`; tabular files fetch their original uploads (`.sav`/etc.) and the server-generated `.tab` derivatives are removed once the original is staged (originals-only), so verification checks the original by size. Metadata, manifest, and reports live under `workspace/downloads/<id>/` (`metadata.json`, `file-manifest.json`, `reports/`) and reload instantly on next launch. While the stream runs, a **Cancel** button appears beside **Download All**: stopping takes effect at the next chunk, files already staged are kept, and the truncated bundle part is removed (logged as `Cancelled by user`).
4. **Run checks** — click **Run checks** (`CheckWorker` dispatches every file to its format check; without staged files it tells you to download first). The `QProgressBar` is indeterminate and the status label shows per-file progress (`progress` signal).
5. **Inspect results**:
    - The **File Manifest** is a folder → file → check tree. File rows show `Clean · N passed` / `Warning · …` / `Error · …` / `Skipped` / `No automated check`; expand a file to see every check with its full message (passes included). Check rows carry PASS/WARN/FAIL/SKIPPED badges with `details` in the tooltip. Files with issues auto-expand.
    - Filter with the text field (matches filenames, check IDs and messages) and the status combo (All/Issues/Errors/Warnings/Skipped/Clean/No check). The **Dataset checks** card shows `inventory.*` results with full messages plus aggregate counts; per-file rows live only in the tree.
    - Click a file for aggregate counts, or a check for its full message + details, in the status bar.
6. **Export reports** — **Export reports…** saves `*_report.json` + `*_report.md` side-by-side (defaulting to `workspace/downloads/<id>/reports/`) via `DatasetReport.save()`/`save_markdown()`; the JSON is canonical and can be handed off to the review dashboard workflow, the Markdown is the human-readable view. Without a report it tells you to run checks first.
7. **Draft the depositor response** — switch to the dataset's **Response** tab (header toggle). It assembles the ruleset's standard text for every incomplete check plus every failed file check (warnings/errors) into an editable draft: uncheck findings to drop them, edit freely (auto-saved per dataset to `workspace/downloads/<id>/response_draft.md`), **Regenerate** to rebuild from current findings, **Copy** for the clipboard, **Export…** to save Markdown (logged in the Dataset log as `response_exported`).

All text (labels, table cells via `Ctrl+C`, log lines, dialogs) is selectable and copyable.

## Notes on checks

- Checks matching the file format run automatically; files with no applicable check (unknown extension) are listed but not inspected (`no checks`).
- **Lite build** bundles common formats (`Pillow`, `pypdf`, `lxml`, `openpyxl`, `tifffile`, `chardet`) so JPG/PNG/PDF/XML/XLSX/TIFF work offline; only heavy binary libs (`pyreadstat`, `netCDF4`, `h5py`, `scipy`) need the full build. Missing libs report `Missing …` in the **Curation checks** tab and as a warning `CheckResult` — not a failure. JPG/PNG/GIF/BMP/WEBP additionally fall back to a stdlib header parse when Pillow is absent. For heavy formats run `dist/curation-app-full/curation-app-full.exe` directly.
- OCR (PDF text extraction) and deep exif metadata are optional: without tesseract/exiftool they report “not executed”.
- All check definitions come from the curation toolbox; parity with the R inspectors is maintained by 198 tests (`docs/engine-port.md`; `pytest --collect-only -q` for current count). See `docs/checks-reference.md` for what each check examines and what PASS means.

## Log and troubleshooting

A **Log** page in the main stack (toggle with the **Log** button in the top nav or `Ctrl+L`) shows an in-memory ring buffer (`applog.py`) of every Dataverse request (`GET <url> → <status> (<ms>) <summary>`), plus worker messages. Timestamps are local time. Syntax highlighting (INAV-style) colors `ERROR` red, `WARNING` yellow, IPs, SQL keywords, XML tags, Java backtraces, and quoted strings; lines containing `ERROR`/`WARN` get higher priority. The header bar holds the severity legend (**ERROR**/**WARN** chips rendered in the highlighter's exact fills plus a muted *INFO · DEBUG plain* key, so colour never explains itself), a **Search log…** box (case-insensitive substring filter; Live tooltip shows match counts), a **● Live** toggle (pause to freeze the view for inspection — click again and buffered lines catch up), Clear, and hide buttons. The panel polls every 800 ms (`QTimer`) while live and supports copy. The full-page Log view and the Log dialog carry the same search box.

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
python main.py --headless <staged_dir> --out report.json --format both --persistent-id doi:10.5072/FK2/EXAMPLE
```

Walks the staged dir and writes `DatasetReport` JSON without launching the GUI (same `engine/runner.py:run_report`). `--format json|md|both` (default `json`) also writes the Markdown view. `--dataverse`/`--config` are GUI-only: headless operates purely on local files and rejects those flags. Exit codes: 0 clean, 1 error-level findings, 2 usage/IO failure.
