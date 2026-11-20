# User guide

The Dataverse Docent is a desktop tool for curators reviewing datasets deposited in a Dataverse instance: first run, dashboard queue, dataset detail, response drafts, log, troubleshooting, headless mode.

## First run

1. Launch (dist/DataverseDocent/DataverseDocent.exe or python main.py). With no config.json, the Settings page opens automatically.
1. Choose the Dataverse: preset (Borealis Demo — demo.borealisdata.ca or Custom…; the Base URL field stays editable), API token (blank = public-only browsing; drafts/in-review need a token), Collection alias (e.g. mcmaster; empty = whole repository; the demo root alias is dv — aliases root/:root are treated as empty, verified against Borealis v6.8.4-SP), Workspace folder. Test connection hits GET /api/info/version before saving.
1. Install & updates: install DataverseDocent-win-Setup.exe from the GitHub releases page (per-user, no admin; or unzip the portable zip). Later versions arrive inside the app — the About page checks the release feed once a day and offers to restart and apply the update when one is published; you never download an installer again. The build is unsigned, so SmartScreen asks More info → Run anyway once.
1. Extensions tab: per-package Install/Uninstall (uninstall asks for confirmation before removing) with installed sizes and a Version column for the optional curation libraries; the Installed column shows a check or cross rather than words (hover for the words). Tesseract (OCR) and ExifTool (deep metadata) paths live in the same table.
1. Save → the app contacts the instance (paginated GET /api/search?q=*&type=dataset&per_page=1000&start=…&subtree=…, total-driven, with dedup) and the dashboard loads; the bottom status pill shows the current Dataverse + collection. Switch instances anytime via top-nav Settings (Ctrl+,) — Save applies config.json and reloads the dashboard, Back discards; the last choice is persisted in %APPDATA%\Dataverse Docent\config.json for an installed build (a portable build keeps it beside the exe; see config.example.json). ? opens About. Headless/CLI runs ignore --dataverse/--config (local staged directory only).

Windows may warn about an unsigned build. The first releases are not code-signed, so SmartScreen (or your institution's AV) can show “Windows protected your PC”. Choose More info → Run anyway if you trust the source — the app is MIT-licensed and open source at github.com/isaacpratt/dataverse-curation-app. Before you run an artefact, check it against the checksum published with the release: open SHA256SUMS.txt from the release and compare it with Get-FileHash -Algorithm SHA256  in PowerShell. Later releases are signed by SignPath Foundation, and Windows then shows the publisher name instead of “Unknown publisher”. The policy is recorded in SECURITY.md.

## Dashboard (curation queue)

Lists every dataset in the collection, found by paginated Search (per_page=1000, driven by the server's total count — no dataset cap in practice). All 13 columns are sortable (numeric/date-aware _SortItem, click header or press Space/Return on the focused section), draggable, resizable with visible edge dividers (hover/press highlight), and togglable via right-click header or Columns…. First paint auto-fits content (proportionally downscaled on overflow — the queue has no horizontal scrollbar); dragging any edge locks your widths; Columns… → Reset columns && sorting restores defaults and re-enables auto-fit (saved widths always win across restarts). Status and Curation Label render as plain text.

While a crawl runs, a small circular progress ring appears beside the status line: it fills as discovery, enrichment, lock checks and label reads complete, glides toward each new value instead of jumping, clears itself when the crawl finishes, and turns red if the crawl fails. Rows appear as they are found (cache-first paint), and the Size column fills in as each dataset's file inventory is fetched (drafts first, capped at 200 per refresh — rows past the cap show “—” until you open them). In a very large collection the table paints the first 2,000 matching rows and says how many are hidden; narrowing the filter shows the rest.

| Column | Source |
| --- | --- |
| Dataset Title | name/title |
| Persistent ID (hidden by default) | global_id/identifier |
| Submitting Author | contacts[].name |
| Depositor (hidden by default) | datasetContact / depositorName |
| Date Created | createdAt |
| Date Published (hidden by default) | published_at / publicationDate |
| Collection (hidden by default) | name_of_dataverse (identifier_of_dataverse) |
| Files | fileCount |
| Size | total_size_bytes humanized (B/KB/MB/GB; “—” when the search record carries no byte total — exact sizes come from the download quote). A dimmed “—” means the size cannot be had: your account read no version of that dataset |
| Status | Draft/review markers in publicationStatuses win over versionState; In Review confirmed via locks |
| Access | What your account could read: Draft not readable, Not readable, No published version or Curation state hidden — empty when everything read. Hover for the reason and the server's own words |
| Curation Label | Per-draft label (bulk report or curationStatus) |
| Downloaded | Local staging date from state.db + staged-folder mtime |

Filter bar: free-text search (title, ID, contact, depositor, collection, curation label) + Status (All / Draft unsubmitted / Published / In Review / Deaccessioned — draft markers anywhere in the search record count) + Curation label (All + the instance's own set + No label) + Collection (All + every subcollection in the pull). The label set is pulled fresh on every refresh via the Curation Status API — bulk report first, then the allowed set from draft datasets (retried across several, since the endpoint needs PublishDataset permission) — and remembered in /curation_labels.json; the dataset page header shows the label as a pill with setter/time tooltip. Instances without labels configured just show “All Curation Labels” + “No label”.

The queue is cached per instance+collection (dashboard_cache.json): instant paint on open, background refresh reports only what changed (N new, M updated, K removed / No changes — N datasets up to date). The status pill at the bottom of the dashboard carries /[]: X/Y datasets shown (instance scope + filtered count), then — after a dot — the contextual message (“Double-click a row to open it”, load progress, or an error); the row ends with the 16×16 Docent mark at the bottom-right. Double-click (or Enter on the focused row — use the visual row's Persistent ID after sorting) opens a dataset; F5 refreshes; Escape clears search. The window is responsive at its 960px floor — the queue's tools row fits by eliding combo labels, and the detail sidebar folds away below the fold width.

The three metric cards are also filters: click Pending Datasets (Draft + In Review), In Review, or In Progress (rows with any curation label, any state) to narrow the queue; the Status combo gains a matching Pending (Draft + In Review) entry. The queue header is two rows: the title on its own, then every tool — search, the three filters, Columns… and Refresh — on one row below. The search field carries its label as placeholder + accessible name (no separate visible label), and its filter combos elide their text when the window is narrow (full text stays in the drop-down). Other controls: Refresh in the queue header (re-runs the paginated crawl), Review configuration in the top nav (edit review rulesets + response templates in requirements_profiles.json), the Log toggle (Ctrl+L), ? (About), and Help (the file-text button — a searchable, task-grouped index of every card's (i) explanations, built from the tips themselves so it never drifts). Without a token only published datasets return; the first-run empty state offers a primary Open Settings action and metrics read — until the first crawl. Right-click the queue: Run checks for N visible rows queues a background file-checks pass over exactly the rows the table paints (never more than the 2,000-row painting window); results land in each dataset's cached checks-report.json, so opening one finds them ready. The count is written to the log, and the same menu offers to cancel a run in flight.

## Curating a dataset
Back via the Dashboard tab or Alt+Left. The sidebar keeps its own scroll position while the main column scrolls. Draft headers link dataset.xhtml?persistentId=…&version=DRAFT (DOIs don't resolve for drafts). Everything selectable; table cells copy with Ctrl+C. Keyboard: Ctrl+Enter runs checks (or commits on the Response page), Ctrl+D downloads all, Ctrl+Shift+O opens the staged folder — the Run checks button's tooltip lists the chords.

Metadata check shows rule-driven completeness for the selected ruleset (McMaster derived from the McMaster Curation Log / Depositor Checklist — source PDFs retired 2026-10-07, rules live in code — or Minimal, plus any custom rulesets). Rows read like the Automated checks card — one row per rule: an icon for the outcome (complete / incomplete / not checked), the rule's name in bold, a one-line verdict sentence (what the depositor entered), a badge on the right. Required vs optional lives on the row tooltip: Required blocks approval per the active ruleset; Optional is a recommendation and never blocks. Checks are grouped under collapsible block headings (Citation, License & Terms of Use, Geospatial, Content) with a counts subtitle, and repeatable compound fields (authors, publications, contacts, descriptions) expand into an inline drawer — one block per entry with the subfields (Name: Ada Lovelace) as caption lines; single-entry fields show their subfields directly. Hovering a row shows the requirement text. The filter combo switches between All / Complete / Incomplete and Not checked (rules the ruleset marks unchecked — hidden by default, no verdict, no disposition). Includes per-author ORCID format checks via the author Identifier subfield (every author needs a valid ^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$, configurable as its own rule in Review configuration), an Author count row, a License and Terms of Use row, and README detection via the file inventory. Changing the profile re-evaluates immediately.

The dataset page groups results into two top-level sections: Dataset checks (metadata completeness plus the automated checks about the dataset and its inventory — executables, system junk, zero-byte files, access conditions and embargo dates) and File checks (the renamed manifest, which owns every per-file result). A finding appears in exactly one of them; each section has its own summary and filter.

Review configuration (top nav) edits the rules in two left-hand cards: Metadata Field Rules marks each metadata field from the Dataverse metadatablocks catalog as Required / Optional / Not checked, and Content-based Rules manages text-search rules (filenames, metadata values, staged file contents — e.g. README). License / Terms of Use / Terms of Access group under License and Terms of Use; the right column edits the standard response text per rule plus the draft header/footer. Each field row is one shape — Field | Level | Check — with two centred dropdowns and no header band, reset control or user column sizing, so the table always fits: the Level dropdown marks the field Required / Optional / Not checked and the Check dropdown picks the test itself. Must be non-empty is the historical test; Looks plausibly correct checks the entry itself — minimum length, a regular expression, blocked or placeholder phrases, an allowed-values list, parseable ISO dates, date-range order, plausible URLs — configured in the Entry checks panel under the response text while that check is picked. That panel is a normal form: short labels above full-width controls — a Lucide minus/plus stepper for Minimum length (0 turns it off), a Pattern field with its Whole value checkbox on the next line, Blocked phrases and Allowed values as one-phrase-at-a-time chip fields, then the five flags on their own rows. Every explanation is a tooltip on its label and control, and nothing is clipped at 960px. Failures cite the reason (e.g. [too short: 12 of 50 characters]), empty values report incomplete, and a rule with no checks configured fails closed rather than passing silently. Rulesets apply per Dataverse (* = all instances), are stored as requirements_profiles.json v2 beside config.json (the working directory in a dev run, %APPDATA%\Dataverse Docent\ when installed, the portable root otherwise), and show a ● unsaved chip while edited, and Save/Revert sit in a footer shared with Settings.

File checks lists every file (staged dir if downloaded, else the Dataverse inventory) with most of the column width. Columns: Name (folder › file › check tree), Size, Format, Scan. Restricted files, embargo/retention dates, and tabular ingest status/errors appear in the name/scan tooltips. The Dataset checks card also names restricted and embargoed files through inventory.restricted_files / inventory.embargoed_files, with each finding carrying the embargo date and the dataset's terms of access; the Metadata check's Access, Embargo & Terms of Access row shows the same conditions for the selected ruleset. Click a row after checks for its findings; Open folder reveals the staged directory. Preview (sidebar) shows the head of the clicked file — first rows, lines, entries or pages — never the whole thing. The Raw metadata bottom toggle shows citation blocks plus a — Full JSON — dump (capped 12000 chars) from GET /api/datasets/:persistentId.

Every section header carries a Lucide (i) button: hover or click it for that section's explanation. The Automated checks tip also carries the status legend (✓ pass · ✕ issue · ○ SKIPPED · MISSING = optional library not installed), keeping the body for results.

Automated checks lists what the run found: the dataset checks with their full messages, then every per-file failure and skip — per-file passes live in the File checks tree (expand a file to see them). Its filter combo narrows the card to All / Errors / Warnings; the header counts always describe the whole run, not the filtered view, and All brings every row back. The same check skipped on many files (an optional library that is not installed, say) collapses into a single row carrying the count — hover it for the files it did not run on.

1. **Review metadata** — auto-loads on open; **Reload Metadata** in the
   Dataset checks header re-fetches fields and the file inventory without
   downloading. Change the profile (McMaster/Minimal/custom) to re-evaluate.
2. **Download** — **Download Dataset** in the File checks header quotes the
   count and size first (original size for tabular); approval guards large
   sets and a declared guestbook is rendered in the same window. Progress
   shows X.Y MB; tabular originals replace `.tab`. Cancel keeps staged files
   and removes the truncated bundle part.
3. **Run Automatic Checks** — stages the dataset first if needed, then runs
   every applicable check (per-file label, Cancel while running). Afterwards
   the button reads **Run File Checks** for a dataset-only pass or **Re-run
   Automatic Checks** for a full one.
4. **Inspect** — the File checks tree is folder › file › check (Clean /
   Warning / Error / Skipped / No automated check); files with issues
   auto-expand, and filters narrow by text and status. Per-file findings live
   only there; the Dataset checks card holds the dataset-level results.
5. **Respond** — the Response page assembles standard text per incomplete rule
   and failed check: uncheck to drop, edit freely (autosaved), then
   Regenerate / Copy / Export.

The dataset header keeps the three things a curator navigates to in a
**three-button rail — Dataset Checks → File Checks → Response**. The buttons
are plain navigation: they jump the Review page to that section's heading or
switch to the Response page, and never start a download, a check pass or a
save dialog. The old six-step rail, its CURATE(D) toggle and the separate
"Open in Dataverse" link under the title are gone.

The header itself is three bands. The **top band** carries the chips
(DOI link, publication status, "Submitted for Review" stage, curation label)
and the actions. The **middle band** puts the dataset title and depositor on
the left and a **compact status widget** on the right; the widget is hidden
while idle and shows a spinner, the count (e.g. 14/21), a progress bar and a
Cancel button while work runs. It switches to a green check and full bar when
checks complete, and to a red alert with a Retry button on failure. The
**bottom band** is the three-button rail with result pills (passed / warnings /
errors) at its right edge. All glyphs are bundled Lucide icons; buttons,
chips and text use the app's standard kit faces.
Header actions are now placed where they belong:

- The **DOI chip is the Dataverse link**. Click it to open the dataset's
  landing page in your browser (the DRAFT version opens when the dataset is a
  draft). The publication-status chip sits beside it, followed by the
  curation-label chip when Dataverse has assigned one.
- **Dataset checks** section header: **Reload Metadata** (or **Load metadata**
  before the first load) re-fetches the file inventory and metadata fields.
- **File checks** section header: **Download Dataset** stages every file for
  checking; once everything is staged the same button reads **Verify Files**.
- The primary button is **Run Automatic Checks** on a fresh dataset. Press it
  with nothing staged and it stages the dataset first (approval dialog
  included), then runs the checks. After a dataset-only pass it reads
  **Run File Checks**; after a full pass it reads **Re-run Automatic Checks**.
- **Export reports** is gone; **Export record** remains in the fixed header.

## Notes on checks

- Checks matching the file format run automatically; files with no applicable check (unknown extension) are listed but not inspected (no checks).
- One build covers everything the checks inspect: JPG/PNG/PDF/XML/XLSX/TIFF through Pillow, pypdf, lxml, openpyxl, tifffile and chardet, plus a stdlib image-header fallback, and SPSS/SAS/Stata/NetCDF/HDF5/MAT through pyreadstat, netCDF4 and h5py — there is no second download to run for heavy formats. Missing libs report Missing â€¦ in the Automated checks area as a warning CheckResult, never a failure.
- OCR (PDF text extraction) and deep exif are optional: without tesseract/exiftool they report “not executed”.
- Parity with the R inspectors is held by the test suite (engine port; uv run pytest --collect-only -q for the live count). Semantics: checks reference.
- Dispositions: every finding (a failed check or an incomplete metadata rule) can be marked Acknowledged / Fix requested / Won't fix / Blocked — set it on the Automated checks row's combo (with an optional Note…), or right-click the check row in the metadata tree / the manifest tree. Dispositions persist in state.db and re-attach when a re-run reproduces the same finding; the manifest tree shows the label next to the finding, the Automated checks header rolls up “N of M findings resolved”, and Won't fix findings drop out of the generated depositor response until you re-include them.
- Copy this finding: every finding row (metadata and Automated checks) carries a ⋯ button after the badge — one click copies a single line (e.g. Title — A study (McMaster — Required)) ready to paste into a curation note or the depositor letter.
- Variable-metadata coverage: for tabular files the app reads Dataverse's per-file DDI and reports how many variables carry a label (metadata.var_coverage — warning for a file with none or under half). The File checks's Scan column shows “N/M variables documented” on each tabular file, and Draft dictionary in the manifest's tool row writes a CSV draft (variable, label, type) for the selected file — hand it to the depositor to complete, then re-run checks.
- In-app preview: clicking a file in the File checks also paints a Preview card in the sidebar — the head of the file (first rows/lines/entries/pages), never the whole thing. CSV/TSV/XLSX show the first rows with column types; text/markdown and JSON show the head; images render a thumbnail (dimensions via stdlib header parse when Pillow is absent); PDFs show page count and first-page text (pypdf); ZIP/TAR list entries; SPSS/Stata show column metadata; NetCDF/HDF5 list structure. Files over 8 MiB get an Open folder fallback instead of a parse, and every optional-library gap degrades to the standard Missing: … notice — never a crash. Every preview is bounded (about 1–2 MB of head bytes) and lands in the dataset log as a preview_rendered action.
- README depth: beyond “is there a README?”, the checks score it against five standard sections — dataset & file overview, file inventory & naming, methodology, missing-data codes, sharing/access & licensing. The Automated checks row carries the per-section checklist (✓ found · ○ missing); a ruleset can override the list with section_rules, and the depositor template can list exactly what is missing with {readme_sections}. A missing README is still handled by the ruleset's README file presence rule.
- Why each check matters: every failed check now explains itself — the manifest and Automated checks tooltips carry Why this matters / How to fix, the Markdown report lists them under each failed check, and depositor-response templates can pull the fix text with a {remediation} placeholder. The full registry lives in checks reference.
- Readiness verdict: the Review page opens with a live banner — Ready / Revisions needed / Blocked / Not yet reviewed — computed from the checks report, the metadata completeness, and your dispositions (resolved findings stop counting). Each reason chip (“2 required metadata fields missing”, “1 error-level findings”) jumps to the card that owns it; headless runs print the same verdict line (Verdict: …) with exit codes unchanged.
- Depositor follow-up: a decision that asks for revisions puts the dataset into a waiting state. The Review page opens with a awaiting the depositor since  banner (above the verdict banner); the dashboard queue carries a Follow-up column with the same state. When the depositor updates the draft on Dataverse after your request, the state flips to depositor updated — re-run checks and the banner offers Re-run checks and a link to the Changes step. Any later decision closes the follow-up; open/close events are recorded in the dataset log.
- Sensitivity & ethics review (Response page): five judgment calls the automated PII/access scans cannot make — human subjects, consent/IRB documentation, small-cell risk, Indigenous data (CARE), restricted files under terms of access. The two machine-derivable answers prefill from the scans (“Suggested: …”); answers persist per dataset and every save lands in the dataset log. When the active ruleset carries "requires_sensitivity": true (requirements_profiles.json, beside config.json), Approve stays blocked until the questionnaire is complete.
- Export record (header): one click writes a dated curation-record// folder beside the dataset's workspace folder — checks report (JSON + Markdown), the depositor response, the curation timeline, per-finding dispositions with notes, the sensitivity questionnaire, the recorded decision + curation label, and a sha256sums.txt manifest of staged files, all bound by index.json. Re-running never clobbers an earlier record; headless runs add --export-record.

## Log and troubleshooting

The Log stack page (nav Log button or Ctrl+L) shows an in-memory ring buffer (applog.py) of every Dataverse request (GET → () ) plus worker messages, stamped in local time. INAV-style highlighting colors ERROR red, WARNING yellow, IPs, SQL keywords, XML tags, Java backtraces, and quoted strings (lines with ERROR/WARN get higher priority). The header carries the severity legend (ERROR/WARN/Expected chips in the highlighter's exact fills plus a muted INFO · DEBUG plain key, so colour never explains itself), a Search log… box (case-insensitive substring; the Live tooltip shows match counts), a ● Live toggle (pause to freeze — click again and buffered lines catch up), Clear, and hide. The panel polls every 800 ms (QTimer) while live; the full-page Log view and the Log dialog carry the same search box. All error dialogs (ui/dialogs.py) are selectable for pasting tracebacks.

| Symptom | Fix |
| --- | --- |
| 401 | Token expired/insufficient → regenerate in Dataverse → Settings. (A 401 on one dataset's draft is expected, not a token problem — see Expected above and the queue's Access column.) |
| ConnectionResetError 10054 | Transient — auto-retried 3×; check VPN/proxy, then retry |
| 400 invalid collection alias | Try empty (whole repo); dv is the Borealis root, not borealis |
| Empty dashboard | No datasets for that subtree; widen the collection; without a token only published return |
| Missing: pip install … | Optional lib absent — a shipped build carries every one, so reinstall; a dev venv can pip install it |
| Check “not executed” | Optional tool missing — install tesseract/exiftool and set the path in Settings |
| ContextualVersion 406 | Missing & before persistentId in versioned URL — fixed; re-pull if you saw this on an old build |
| Download interrupted | Re-download; previous stage is cleaned up, prior reports preserved |
| Download says “Guestbook response” required | The dataset collects a guestbook before download; the download window shows its fields (prefilled from your account) and submits them with the ZIP. Fill any required field the account left blank. If the form did not appear, reload the dataset metadata and try again |
| Checksum mismatch on .tab | Expected (server-regenerated ingest product): compare the UNF in the message, or fetch the original format. Other formats mismatching = real corruption — re-download |
| NameError: QWidget in Settings | Fixed in the 2026-08-26 build — update to the current Dataverse Docent release |

Expected lines are the server's documented answer for that request, not application failures — for example 401 on a draft your account may not read (Dataverse grants draft access only inside a dataset's curation scope), 404 for a dataset with no published version (deaccessioned versions are excluded by default), or 403 on a curation status that only exists for datasets under curation. The raw call and the raw response are kept verbatim; the line is tagged EXPECTED and painted in the muted tone, with the reason after the response. Anything the app cannot classify (a 500, a bad request) stays ERROR in red.

The queue's Access column carries the same facts per dataset: Draft not readable, Not readable, No published version or Curation state hidden — empty when everything could be read. Hover the cell for the reason and the server's own words. Opening such a dataset says the same thing where it matters: the file list is “not readable for this account”, not a failed load. The app also stops asking for what cannot exist: each dataset is read once (the read answers with the version your account may see — the draft for a dataset under curation, the published version otherwise), a deaccessioned dataset is never asked for a published version, and a dataset with no draft skips the curation status, the label history and the version comparison.

## Headless mode

```
python main.py --headless <staged_dir> --out report.json
python main.py --headless <staged_dir> --out report.json --persistent-id doi:10.5072/FK2/EXAMPLE
python main.py --headless <staged_dir> --out report.json --format both --persistent-id doi:10.5072/FK2/EXAMPLE
```

Same engine/runner.py:run_report without the GUI. --format json|md|both (default json) also writes the Markdown view. --dataverse/--config are GUI-only and rejected here. Exit codes: 0 clean, 1 error-level findings, 2 usage/IO failure.
