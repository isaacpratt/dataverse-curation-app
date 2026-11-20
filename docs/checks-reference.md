# Auto-checks reference

What the engine verifies when you press Run checks, what each badge means, and what each of the 22 checks can find. Checks are ports of the R inspectors in CUR_Res_CurationTools — see Engine port for the port matrix.

## How checks run
Compound names shed one outer layer first. Symlinks are skipped; each file runs in isolation so one crash can't sink the report. Results aggregate into the DatasetReport contract (JSON + Markdown). Secrets/PII scanners (hush-scan, piigex) are required and bundled — never “missing”. Structured PII uses regions=["intl"] + the Canadian postal/SIN pack; foreign national IDs are disabled by policy.

## What PASS means (two contexts)

| When | Badge | Meaning |
| --- | --- | --- |
| Before running (Dataset checks card) | PASS | Check is planned and applicable to this dataset's files |
| — | No matching files for this check |
| MISSING | Optional library absent in this build |
| After running | ✓ passed:true | Policy held (info results typically pass with details, e.g. “consistent 12 columns”) |
| ✕ FAIL | error-level finding — data integrity problem |
| ✕ warning | Finding to review with the researcher |
| ○ SKIPPED | Sub-check could not run (details.skipped: missing lib, encrypted PDF, legacy .xls, size caps) — distinct from a pass |

Always-emit: every module emits all owned IDs every run — passes like “No zero-byte files” and “no PII values detected” stay visible in the manifest tree and Markdown. Finding lists are capped (secret_max_listed=20, pii_max_samples=10); the message always states the truncation (showing first 10 of 47 sample(s)) and details.count carries the full total.

## Issue taxonomy

| Level | Meaning | Typical examples |
| --- | --- | --- |
| info | No action; confirms health | File parsed OK + encoding; extension census; NetCDF variable count; consistent CSV columns |
| warning | Review; likely needs a fix or a note to the researcher | Ragged CSV; duplicates; structured PII; secrets in code/text/config; non-ASCII filenames; executables; hidden sheets/macros; unexecuted notebook cells; scanned PDF; mixed line endings; TODO markers; external HDF5 links; system junk (Thumbs.db, __MACOSX) |
| error | Data integrity problem | 0-byte file; unparseable CSV/JSON/XML/notebook; corrupt zip/tar; unreadable SPSS/Stata/SAS; missing GeoPackage geometry; truncated image; checksum mismatch |

## Per-format checks (22 modules)

Scope is dataset or file, declared by each check class (Check.scope) and enforced at registration: dataset checks run once over the whole staged set and report under dataset_checks; file checks run once per matching file and report in that file's checks. Extensions say which files a check reads, not what its findings are about — the two are independent, so a cross-file check can read .csv and still be dataset-scoped (engine/tests/test_check_scope.py proves it). On the dataset page, Dataset checks shows dataset_checks (and the metadata completeness card), while File checks shows every files[].checks entry in its folder → file → check tree; a finding is never printed in both.

| Module | Scope | Check IDs | Examines | Notable findings |
| --- | --- | --- | --- | --- |
| csv_check | file | format.csv.* | Encoding, delimiter sniff, ragged/missing/duplicate rows, PII (piigex + CA) on 1k-row sample; full parse capped 50k rows (truncated:true when sampled) | Ragged / duplicates / PII (warning) |
| xlsx_check | file | format.xlsx.* | Workbook opens, sheet list, hidden sheets, VBA macros, tabular shape, PII first 1k data rows/sheet | Hidden, macros, PII (warning) |
| sav_check | file | format.spss.* | SPSS opens (pyreadstat), variable dictionary, encoding, value labels | Unreadable (error) |
| dta_check | file | format.stata.* + pii | As SPSS + PII scan on character columns | Same family + PII |
| sas7bdat_check | file | format.sas.* | 128-byte SAS FILE magic, then as SPSS | Non-SAS with .sas7bdat extension |
| json_check | file | format.json.valid | Strict parse (over 64 MiB → too-large warning, no full parse) | Unparseable (error) |
| xml_check | file | format.xml.valid | Well-formedness (lxml) | Malformed (error) |
| ipynb_check | file | format.ipynb.* | Notebook JSON (64 MiB cap), cell inventory, execution counts | Invalid (error); unexecuted (warning) |
| sqlite_check | file | format.sqlite.* | Opens, full integrity_check, table inventory | Corrupt (error) |
| hdf5_check | file | format.hdf5.* | Opens, external links; walk capped 5k (truncated when partial) | Dangling links (warning) |
| nc_check | file | format.netcdf.* | Opens, vars/dims, CRS/georef, NaN sampling on capped per-dim slices | Missing CRS (warning); all-NaN variable |
| gpkg_check | file | format.gpkg.* | Pure-SQLite gpkg_* tables, layers, SRS (no GDAL) | Missing geometry (error) |
| tiff_check | file | format.tiff.valid | Header/pages parse (tifffile) | Corrupt (error) |
| images_check | file | format.images.valid | Raster opens, mode/size (Pillow; stdlib header fallback without it) | Unreadable/truncated (error) |
| pdf_check | file | format.pdf.* | Opens, page count, text sampled on first 3 pages | No extractable text — scanned, needs OCR (warning) |
| text_check | file | format.text.* | Encoding, line-ending mix, control chars, PII on 1 MiB sample | Mixed endings, control chars, PII (warning) |
| code_check | file | format.code.* | Readable text (first 1 MiB), TODO/FIXME scan | TODO markers (warning) |
| secret_check | file | format.secrets | hush-scan (regex + entropy) over first 5 MiB of code/text/config; capped at 20, explicit “showing first N of M” | API keys, tokens, private keys, high-entropy strings (warning) |
| containers_check | file | format.containers.* | Zip testzip, tar members, traversal (../absolute), encrypted entries; capped 10k members / 2 GiB | Corrupt (error); traversal + encrypted (warning) |
| fastq_check | file | format.fastq.* | Gzip-aware 4-line validation (header/+/seq-qual length), length/GC on capped sample | Malformed incl. length mismatch (warning); no valid reads (error) |
| extensions_check | dataset | inventory.* | Extension census, 0-byte files, executables, OS junk (nested __MACOSX incl.) | 0-byte (error); executables/junk (warning) |
| access_check | dataset | inventory.restricted_files, inventory.embargoed_files | Names restricted and embargoed files from the Dataverse inventory; each finding carries the embargo date and the dataset's terms of access | Restricted/embargoed file(s) (warning); skipped without an inventory (staged-only run) |
| varmeta_check | dataset | metadata.var_coverage | Per-file variable-metadata coverage from Dataverse's DDI: how many variables carry a label. Rides the per-file coverage map and the labels on its first result so the File Manifest annotates each tabular file and the dictionary draft works offline. | Tabular file with no variable labels (warning); under half labeled (warning); skipped without an inventory |
| readme_check | dataset | metadata.readme_sections | Scores the staged README against the five standard sections (overview, files, methods, missing-data codes, sharing/access) by scanning its heading lines; a ruleset may override the section list with section_rules. Details record which sections were found/missing; the depositor template can use {readme_sections}. | Missing required section(s) (warning); missing optional section only (info); skipped when no README is present (the presence rule still applies) |

MATLAB .mat (and any format without a module) is reported once per dataset as inventory.unchecked_types (warning) — manual review required. scipy stays optional by design.

## Why each check matters (dv-lfn guidance)

Every finding in the app and the Markdown report carries this guidance (Why this matters / How to fix) from the registry in engine/checks/guidance.py; response templates can pull the fix text with a {remediation} placeholder. Family rows (e.g. format.csv) are the always-emit parents for their module.

| Check | Why this matters | How to fix |
| --- | --- | --- |
| format.code | Code files are inspected so computational workflows can be rerun by reviewers. | No action needed when it passes; address the code-specific findings otherwise. |
| format.code.readable | Unreadable or mis-encoded scripts cannot be rerun by reviewers — the most common reason code deposits fail reuse. | Re-save the file as UTF-8 (or ASCII) and avoid machine-generated dumps without a text layer. |
| format.code.todo_markers | Leftover TODO/FIXME markers suggest unfinished work or local notes reviewers were not meant to see. | Finish or remove the marked lines, or explain them in the README before release. |
| format.containers | Archives are tested so a corrupt upload never reaches users silently. | When it fails, re-create the archive locally and upload it again. |
| format.containers.encrypted | Password-protected archives cannot be opened by the repository, reviewers, or future users without the key. | Remove the password and re-upload, or deposit the password through a restricted channel documented in the terms of access. |
| format.containers.unsafe_entry | Absolute paths or parent-directory entries in an archive can escape the extraction folder (zip-slip) and are blocked by many systems. | Re-pack the archive with relative paths only (files at or under the archive root). |
| format.containers.valid | A broken archive (bad CRC, truncated) loses data silently — the most damaging deposit defect. | Re-extract and re-zip the archive locally, verify it opens, and replace the uploaded file. |
| format.csv | CSV files are parsed end to end: structure, encoding, duplicate rows, and PII on a sample. | Address the CSV-specific findings below. |
| format.csv.content | Duplicate rows and empty columns mislead analysis and inflate the file; reviewers flag them in almost every tabular deposit. | Remove exact duplicate rows in a spreadsheet or script, and drop or document empty columns. |
| format.csv.openable | A CSV that cannot be parsed cannot be ingested, previewed, or converted — it fails for every downstream user. | Open the file in a spreadsheet or text editor, fix truncation or binary junk, and re-upload. |
| format.csv.pii | Direct identifiers (emails, phone numbers, government IDs) in an open deposit are a privacy incident, not a formatting issue. | Remove or de-identify the values (codes, ranges, or aggregate), or move the file behind restricted access with documented terms. |
| format.csv.structure | Mixed delimiters or ragged rows break machine parsing — the most common cause of ingest failure and silent column misalignment. | Re-export with a single consistent delimiter, quoting on, and one header row with identical column counts. |
| format.fastq | FASTQ reads are validated so sequencing data is usable without silent truncation. | Address the FASTQ-specific findings below. |
| format.fastq.metadata | Missing per-read quality lines or identifiers make reads impossible to align or verify. | Re-export with full quality lines and unique read identifiers. |
| format.fastq.valid | Malformed FASTQ records (unequal lengths, bad headers) break every downstream bioinformatics tool. | Re-export the reads with a validated tool and replace the file. |
| format.gpkg | GeoPackage files are checked so spatial layers open with geometry and CRS intact. | Address the GeoPackage-specific findings below. |
| format.gpkg.crs | Without a declared coordinate reference system, spatial data cannot be aligned with anything else. | Assign the correct CRS (for example EPSG:4326) in your GIS and re-export. |
| format.gpkg.layers | Empty or unreadable layers waste deposit space and mislead reuse. | Remove empty layers or repair them at the source, then re-export. |
| format.gpkg.valid | An invalid GeoPackage cannot be opened by GIS software — the layer is effectively lost. | Re-export from QGIS/ArcGIS as a new GeoPackage and verify it opens before re-uploading. |
| format.hdf5 | HDF5 files are opened and their internal structure sanity-checked. | Address the HDF5-specific findings below. |
| format.hdf5.external_links | External links point outside the file and break when the file moves — the linked data is lost to other users. | Flatten external links into the file, or remove them and document the sources in the README. |
| format.hdf5.openable | A corrupt HDF5 file silently loses every dataset inside it. | Re-export the file (h5py/netCDF) and validate it before re-uploading. |
| format.images | Images are validated so figures open and render for every reader. | Address the image-specific findings below. |
| format.images.valid | Corrupt or truncated images fail for every reader even when the thumbnail looks fine to the depositor. | Re-export or re-save the image from the original and re-upload. |
| format.ipynb | Notebooks are inspected so the computational workflow they document can be followed. | Address the notebook-specific findings below. |
| format.ipynb.cells | Notebooks with missing outputs or broken cell structure cannot demonstrate the workflow they document. | Restart and run all cells, then save so outputs are embedded. |
| format.ipynb.executed | An unexecuted notebook shows no results — reviewers cannot verify the analysis ran. | Run all cells (Restart & Run All) and save the executed notebook. |
| format.ipynb.valid | A notebook that fails JSON parsing cannot be rendered on the dataset page or rerun. | Re-save the notebook from Jupyter so the JSON is valid, then re-upload. |
| format.json | JSON files are parsed to catch truncation and syntax drift. | Address the JSON-specific findings below. |
| format.json.valid | Invalid JSON cannot be consumed by any tool — typically a truncated or hand-edited file. | Validate with a JSON linter, fix the syntax, and re-upload. |
| format.netcdf | NetCDF files are opened and their metadata and data health inspected (CF-style checks). | Address the NetCDF-specific findings below. |
| format.netcdf.data_health | Fill-value or range problems in the data grid silently corrupt analysis. | Re-check the export pipeline's masking and fill values, then re-export. |
| format.netcdf.metadata | Missing variable units, long names, or global attributes make the data uninterpretable outside the original team. | Add units, long_name, and standard_name attributes plus a global title/history in the source script, then re-export. |
| format.netcdf.openable | A corrupt NetCDF file loses every variable it holds for downstream users. | Re-export with ncdump/ncgen validation and replace the file. |
| format.netcdf.spatial | Missing or inconsistent coordinate variables make the grid impossible to geolocate. | Include monotonic lat/lon coordinate variables matching the data dimensions, then re-export. |
| format.pdf | PDFs are opened and checked for a usable text layer. | Address the PDF-specific findings below. |
| format.pdf.openable | A corrupt PDF cannot be opened by readers or preserved by the archive. | Re-export or re-print the PDF from the source document and re-upload. |
| format.pdf.text | Scanned-image PDFs have no text layer: they are invisible to search, screen readers, and text mining. | Run OCR on the document (or deposit a born-digital export) so the text is selectable. |
| format.sas | SAS transport files are opened and their dictionaries and encodings read. | Address the SAS-specific findings below. |
| format.sas.dictionary | Missing variable metadata makes the dataset uninterpretable without the original codebook. | Export variable labels and formats with the file (or add a codebook) so values are documented. |
| format.sas.encoding | Wrong encoding garbles non-ASCII text (names, places) permanently. | Re-export with the session encoding declared (UTF-8 recommended). |
| format.sas.format_detected | The file did not match the expected SAS transport signature — it may be misnamed or corrupted in transfer. | Confirm the export type (XPORT v5/v8/v9) matches the extension and re-upload. |
| format.sas.labels | Value labels carry the meaning of coded columns; without them, analysis misreads the codes. | Attach value labels in the source dataset or document the code meanings in the README/data dictionary. |
| format.sas.openable | An unreadable SAS file cannot be converted or ingested by the repository. | Re-export via PROC EXPORT or XPORT and verify with a fresh readstat pass. |
| format.secrets | API keys, tokens, and passwords in a deposit are a security incident: they must be treated as compromised. | Revoke and rotate the credentials, remove them from the files (use environment variables), and re-upload. |
| format.spss | SPSS files are opened and their dictionaries, labels, and encoding read. | Address the SPSS-specific findings below. |
| format.spss.dictionary | Missing variable metadata makes the dataset uninterpretable without the original codebook. | Export variable labels with the file (or add a codebook) so values are documented. |
| format.spss.encoding | Wrong encoding garbles non-ASCII text (names, places) permanently. | Re-save with the session encoding declared (UTF-8 recommended). |
| format.spss.labels | Value labels carry the meaning of coded columns; without them, analysis misreads the codes. | Attach value labels in the source dataset or document the code meanings in the README/data dictionary. |
| format.spss.openable | An unreadable SPSS file cannot be converted or ingested by the repository. | Re-save the file in SPSS (or export to .sav via readstat) and verify it reopens. |
| format.sqlite | SQLite databases are opened and their tables enumerated. | Address the SQLite-specific findings below. |
| format.sqlite.manifest | Users need to know which tables hold data before they can reuse the database. | List the tables and row counts in the README (the check output can be pasted). |
| format.sqlite.valid | A corrupt database loses all tables for every user. | Run an integrity check at the source, re-export, and re-upload. |
| format.stata | Stata files are opened and their dictionaries, labels, and encoding read. | Address the Stata-specific findings below. |
| format.stata.dictionary | Missing variable metadata makes the dataset uninterpretable without the original codebook. | Export variable labels with the file (or add a codebook) so values are documented. |
| format.stata.encoding | Wrong encoding garbles non-ASCII text (names, places) permanently. | Re-save with the session encoding declared (UTF-8 recommended). |
| format.stata.labels | Value labels carry the meaning of coded columns; without them, analysis misreads the codes. | Attach value labels in the source dataset or document the code meanings in the README/data dictionary. |
| format.stata.openable | An unreadable Stata file cannot be converted or ingested by the repository. | Re-save the file in Stata and verify it reopens before re-uploading. |
| format.stata.pii | Direct identifiers in character columns of an open deposit are a privacy incident, not a formatting issue. | De-identify the flagged columns or restrict the file; the check output lists the flagged values. |
| format.text | Text files are scanned for encoding and control-character problems. | Address the text-specific findings below. |
| format.text.control_chars | Control characters (NUL, bell, escape) usually indicate binary contamination or a broken export. | Re-export as clean text; if the content is binary, deposit it in its real format instead. |
| format.text.line_endings | Mixed line endings break line-based tools and diffing, and bloat the file. | Normalize the file to one line-ending style (LF or CRLF) with an editor or dos2unix and re-upload. |
| format.text.pii | Direct identifiers (emails, phone numbers, government IDs) in an open deposit are a privacy incident, not a formatting issue. | Remove or de-identify the flagged values (the check output lists them), or restrict the file. |
| format.text.readable | Text saved in a non-UTF-8 codepage garbles accents and symbols for every future reader. | Re-save the file as UTF-8 (most editors have an encoding option) and re-upload. |
| format.tiff | TIFF images are validated page by page. | Address the TIFF-specific findings below. |
| format.tiff.valid | A corrupt multi-page TIFF loses pages silently. | Re-export the TIFF from the imaging software and verify the page count before re-uploading. |
| format.xlsx | Workbooks are parsed: sheets, hidden data, macros, and tabular structure. | Address the workbook-specific findings below. |
| format.xlsx.hidden | Hidden sheets, rows, or columns carry content reviewers and reusers cannot see. | Unhide and review the content; delete what is not needed and re-save. |
| format.xlsx.macros | Macro-enabled workbooks are blocked by many systems and can carry active content. | Save as .xlsx without macros; deposit the macro code separately as a code file if needed. |
| format.xlsx.openable | A corrupt workbook cannot be opened by the repository's ingest or any reader. | Open and re-save the workbook in Excel/LibreOffice, then re-upload. |
| format.xlsx.pii | Direct identifiers (emails, phone numbers, government IDs) in an open deposit are a privacy incident, not a formatting issue. | Remove or de-identify the values (codes, ranges, or aggregate), or move the file behind restricted access with documented terms. |
| format.xlsx.sheets | Many or vaguely named sheets hide the real data table from reusers. | Keep one sheet per table with a clear name; move notes to a README. |
| format.xlsx.tabular | Merged cells, title rows above headers, or multiple tables per sheet break machine parsing. | Restructure: one header row in row 1, one rectangular table per sheet, no merged cells. |
| format.xml | XML files are parsed for well-formedness. | Address the XML-specific findings below. |
| format.xml.valid | Malformed XML cannot be parsed by any consumer — usually truncation or an unescaped character. | Validate with an XML tool, fix the error, and re-upload. |
| inventory.access | Access restrictions and embargoes from the inventory are surfaced for the review. | Address the access findings below. |
| inventory.embargoed_files | Embargoed files unlock on a date; the deposit page should explain when and why. | State the embargo reason and end date in the dataset description or terms. |
| inventory.executables | Executables (.exe/.bat/…) are blocked by repositories and are a malware vector. | Remove the executables, or deposit their source code as text instead. |
| inventory.extensions | The extension census shows the deposit's shape; unrecognized formats need a preservation-risk review. | Review the listed formats; convert to open formats where practical and document the rest. |
| inventory.restricted_files | Restricted files are invisible to the public; reuse depends on the terms of access being complete. | Confirm the terms of access explain how to request the restricted files. |
| inventory.system_junk | OS junk (.DS_Store, Thumbs.db, __MACOSX) is noise that clutters the deposit and leaks local paths. | Delete the junk files and re-upload a clean folder. |
| inventory.zero_byte | Zero-byte files are failed uploads or empty placeholders — they carry no data and fail ingest. | Delete them or replace them with the real files; explain any intentional placeholder in the README. |
| metadata.var_coverage | A tabular file without variable labels is a spreadsheet of unexplained column names — no one can reuse it without asking the depositor. | Use “Draft dictionary” in the File Manifest to write a CSV draft (variable, label, type) and ask the depositor to fill the labels; re-run checks once they do. |
| metadata.readme_sections | A README that skips overview, files, methods, missing-data codes or access leaves reusers guessing — the deposit is technically open but practically undocumented. | Add the missing sections (each as a heading) so the README answers what the data is, what each file holds, how it was produced, how missing values are coded, and how it may be reused. |

## Download verification (a gate, not a check)

Before checks run, DownloadManager.verify() rehashes every staged file against the Dataverse checksum (md5/sha1). Mismatches surface as checksum mismatch:  with expected/actual hashes. Tabular .tab derivatives are server-regenerated, so their message includes the file's UNF for manual comparison instead of failing byte-exact — see “Checksum problems” in the User guide.
