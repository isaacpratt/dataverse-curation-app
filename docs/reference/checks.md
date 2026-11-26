---
page_type: reference
tgdp_template: Reference     # Reference | Glossary
audience: all                # curator | developer | contributor | all
---
# Checks reference

Each check owns one **family ID** (for example `format.csv`) and declares a scope; a run emits more specific check IDs beneath that family (for example `format.csv.structure`). Results are carried by the [DatasetReport contract](report-contract.md).

## How checks run

Compound file extensions (for example `.fq.gz` or `.tar.gz`) shed one outer layer before dispatch. Symlinks are skipped; each file runs in isolation so one crash cannot sink the report. Results aggregate into the DatasetReport contract (JSON + Markdown). Secrets/PII scanners are required and bundled — never "missing".

## Badge meanings

| Context | Badge / marker | Meaning |
| --- | --- | --- |
| Before running — Dataset checks card | PASS | Check is planned and applicable to this dataset's files |
| Before running — Dataset checks card | (no badge) | No matching files for this check |
| Before running — Dataset checks card | MISSING | Optional library absent in this build |
| After running | ✓ passed:true | Policy held; info results typically pass with details, e.g. "consistent 12 columns" |
| After running | ✕ FAIL | error-level finding — data integrity problem |
| After running | ✕ warning | Finding to review with the researcher |
| After running | ○ SKIPPED | Sub-check could not run (`details.skipped`: missing lib, encrypted PDF, legacy `.xls`, size caps) — distinct from a pass |

## Always-emit and list caps

Every module emits all owned IDs every run — passes such as "No zero-byte files" and "no PII values detected" stay visible in the manifest tree and Markdown. Finding lists are capped (`secret_max_listed=20`, `pii_max_samples=10`); the message always states the truncation ("showing first 10 of 47 sample(s)") and `details.count` carries the full total.

### Result aggregation

`status.summarize()` aggregates passed / failed-error / failed-warning / skipped / total; `file_status()` rolls a file row up to one label.

## Issue taxonomy

| Level | Meaning | Typical examples |
| --- | --- | --- |
| info | No action; confirms health | File parsed OK + encoding; extension census; NetCDF variable count; consistent CSV columns |
| warning | Review; likely needs a fix or a note to the researcher | Ragged CSV; duplicates; structured PII; secrets in code/text/config; non-ASCII filenames; executables; hidden sheets/macros; unexecuted notebook cells; scanned PDF; mixed line endings; TODO markers; external HDF5 links; system junk (`Thumbs.db`, `__MACOSX`) |
| error | Data integrity problem | 0-byte file; unparseable CSV/JSON/XML/notebook; corrupt zip/tar; unreadable SPSS/Stata/SAS; missing GeoPackage geometry; truncated image; checksum mismatch |

## Check ID index

The family IDs, each with its declared scope. A report can also contain more specific IDs under these families, plus the hint `inventory.unchecked_types`:

<!-- BEGIN GENERATED CHECK ID INDEX -->
| Check ID | Module | Scope |
| --- | --- | --- |
| `format.code` | `code_check` | `file` |
| `format.containers` | `containers_check` | `file` |
| `format.csv` | `csv_check` | `file` |
| `format.fastq` | `fastq_check` | `file` |
| `format.gpkg` | `gpkg_check` | `file` |
| `format.hdf5` | `hdf5_check` | `file` |
| `format.images` | `images_check` | `file` |
| `format.ipynb` | `ipynb_check` | `file` |
| `format.json` | `json_check` | `file` |
| `format.netcdf` | `nc_check` | `file` |
| `format.pdf` | `pdf_check` | `file` |
| `format.sas` | `sas7bdat_check` | `file` |
| `format.secrets` | `secret_check` | `file` |
| `format.spss` | `sav_check` | `file` |
| `format.sqlite` | `sqlite_check` | `file` |
| `format.stata` | `dta_check` | `file` |
| `format.text` | `text_check` | `file` |
| `format.tiff` | `tiff_check` | `file` |
| `format.xlsx` | `xlsx_check` | `file` |
| `format.xml` | `xml_check` | `file` |
| `inventory.access` | `access_check` | `dataset` |
| `inventory.extensions` | `extensions_check` | `dataset` |
| `metadata.readme_sections` | `readme_check` | `dataset` |
| `metadata.var_coverage` | `varmeta_check` | `dataset` |
<!-- END GENERATED CHECK ID INDEX -->

## Per-module checks

A check is either dataset-scoped or file-scoped. Dataset checks run once over the staged set and report under `dataset_checks`; file checks run once per matching file and report in that file's `checks`. On the dataset page, Dataset checks shows `dataset_checks` (and the metadata completeness card), while File checks shows every `files[].checks` entry in its folder → file → check tree; a finding is never printed in both.

| Module | Scope | Check IDs | Examines | Notable findings |
| --- | --- | --- | --- | --- |
| csv_check | file | format.csv.* | Encoding, delimiter sniff, ragged/missing/duplicate rows, PII (piigex + CA) on 1k-row sample; full parse capped 50k rows (`truncated:true` when sampled) | Ragged / duplicates / PII (warning) |
| xlsx_check | file | format.xlsx.* | Workbook opens, sheet list, hidden sheets, VBA macros, tabular shape, PII first 1k data rows/sheet | Hidden, macros, PII (warning) |
| sav_check | file | format.spss.* | SPSS opens (pyreadstat), variable dictionary, encoding, value labels | Unreadable (error) |
| dta_check | file | format.stata.* + pii | As SPSS + PII scan on character columns | Same family + PII |
| sas7bdat_check | file | format.sas.* | 128-byte SAS FILE magic, then as SPSS | Non-SAS with `.sas7bdat` extension |
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
| secret_check | file | format.secrets | hush-scan (regex + entropy) over first 5 MiB of code/text/config; capped at 20, explicit "showing first N of M" | API keys, tokens, private keys, high-entropy strings (warning) |
| containers_check | file | format.containers.* | Zip testzip, tar members, traversal (../absolute), encrypted entries; capped 10k members / 2 GiB | Corrupt (error); traversal + encrypted (warning) |
| fastq_check | file | format.fastq.* | Gzip-aware 4-line validation (header/+/seq-qual length), length/GC on capped sample | Malformed incl. length mismatch (warning); no valid reads (error) |
| extensions_check | dataset | inventory.* | Extension census, 0-byte files, executables, OS junk (nested `__MACOSX` incl.) | 0-byte (error); executables/junk (warning) |
| access_check | dataset | inventory.restricted_files, inventory.embargoed_files | Names restricted and embargoed files from the Dataverse inventory. Both findings carry file names and the dataset's terms of access; only the embargoed finding carries embargo dates | Restricted/embargoed file(s) (warning); skipped without an inventory (staged-only run) |
| varmeta_check | dataset | metadata.var_coverage | Per-file variable-metadata coverage from Dataverse's DDI: how many variables carry a label. Rides the per-file coverage map and the labels on its first result so the File Manifest annotates each tabular file and the dictionary draft works offline. | Tabular file with no variable labels (warning); under half labeled (warning); skipped without an inventory |
| readme_check | dataset | metadata.readme_sections | Scores the staged README against the five standard sections (overview, files, methods, missing-data codes, sharing/access) by scanning its heading lines; a ruleset may override the section list with `section_rules`. Details record which sections were found/missing; the depositor template can use `{readme_sections}`. | Missing required section(s) (warning); missing optional section only (info); skipped when no README is present (the presence rule still applies) |

MATLAB `.mat` (and any format without a module) is reported once per dataset as `inventory.unchecked_types` (warning) — manual review required.

## Registry guidance

Every finding carries guidance from `engine/checks/guidance.py`: a "Why this matters" field and a "How to fix" field. Response templates pull the fix text with a `{remediation}` placeholder. A family row (for example `format.csv`) is the parent check a module always emits, even when its sub-checks produce no findings; specific IDs such as `format.csv.structure` carry the sub-check results.

## Download verification (a gate, not a check)

Before checks run, `DownloadManager.verify()` checks staged files against the checksum recorded in the Dataverse inventory. The algorithm comes from the inventory's `checksum_type` (default `md5`); original-format tabular files are checked **by size**, not rehashed, because their original bytes are fetched separately. Mismatches surface as "checksum mismatch" with expected/actual hashes. `.tab` derivatives are server-regenerated, so their message includes the file's UNF for manual comparison instead of failing byte-exact.

## See also

- [Report contract](report-contract.md)
- [Entry-correctness rules](entry-checks.md)
- [Dataverse API](dataverse-api.md)
- [Glossary](glossary.md)
