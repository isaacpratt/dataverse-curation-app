# Auto-checks reference

What the engine verifies when you press **Run checks**, what each badge means,
and which problems each check can find. Checks are ports of the R inspectors in
`CUR_Res_CurationTools` — see `docs/engine-port.md` for the port matrix.

## How checks run

1. **Dispatch by file type** (`engine/dispatcher.py`): every staged file is routed
   to the check module(s) matching its extension. Compound names shed one
   outer compression layer first (`sample.fq.gz` → fastq, `archive.tar.gz` →
   tar inspection). Files with no applicable check (e.g. `.mat`) are listed
   under an `inventory.unchecked_types` dataset warning — manual review required.
2. **Dataset-level checks** run on the whole file set (`inventory.*`).
3. Each check emits one or more `CheckResult`s (`check_id`, `level`,
   `passed`, `message`, `details`) aggregated into the `DatasetReport`
   (`docs/report-contract.md`).

Heavy optional libraries (`pyreadstat`, `netCDF4`, `h5py`, `tifffile`, `Pillow`,
`pypdf`, `lxml`, `openpyxl`) are imported lazily: when one is missing
the check reports `level="warning"` + `passed=True` +
"Missing: pip install … — check not executed"
instead of failing (shown as `MISSING`/`WARN` in the Curation checks tab).
(`scipy`/`.mat` has no check module at all — see `unchecked_types` above.)
Secret and PII scanners (`hush-scan`, `piigex`) are **required** and bundled in
both lite and full builds — they never report as missing.

## What PASS means (two contexts)

- **Before running** (Curation checks tab): `PASS` = the check is planned and
  applicable to this dataset's files. `—` = no matching files.
  `MISSING` = the optional library isn't installed in this build.
- **After running**: `✓`/`passed: true` = the policy held — no violation found
  (an `info` result is typically `passed: true` with details, e.g. "consistent
  12 columns"). `✕`/`passed: false` = a finding the curator should review.
  `FAIL` badge = an `error`-level finding. `○ SKIPPED` = the sub-check could
  not run (`details.skipped`, e.g. missing lib, encrypted PDF, legacy `.xls`,
  size caps) — distinct from a pass. Every module emits all owned IDs every
  run, so passes like "No zero-byte files" and "no PII values detected" are
  visible in the manifest tree and the Markdown report. Findings lists in
  `details` are capped (`secret_max_listed` / `pii_max_samples`); the message
  says explicitly e.g. `showing first 10 of 47 sample(s)` and `details.count`
  always carries the full total.

## Issue taxonomy by level

| Level | Meaning | Typical examples |
|---|---|---|
| `info` | No action expected; confirms health | File parsed OK + encoding; extension census; NetCDF variable count; consistent CSV columns |
| `warning` | Curator should review; likely needs a fix or a note to the researcher | Ragged CSV rows; duplicate rows; structured PII (email, SSN/SIN, cards, postal codes, …) in tabular/text; potential secrets in code/text/config (`format.secrets`); non-ASCII filenames; executables (`.exe/.bat`); hidden Excel sheets or macros; notebook with unexecuted cells; PDF without extractable text; mixed line endings; TODO markers in code; external HDF5 links; system junk (`Thumbs.db`, `__MACOSX`) |
| `error` | Data integrity problem | Empty (0-byte) file; unparseable CSV/JSON/XML/notebook; corrupt zip/tar; unreadable SPSS/Stata/SAS; missing GeoPackage geometry tables; truncated image; checksum mismatch on download |

## Per-format checks

| Module | Check IDs | What it examines | Notable findings |
|---|---|---|---|
| `csv_check` | `format.csv.openable/structure/content/pii` | Encoding, delimiter sniffing, ragged rows, missing cells, duplicate rows, structured-PII scan (piigex + CA postal/SIN) on a 1k-row sample; full parse capped at 50k rows (`truncated: true` when sampled) | Ragged rows (warning), duplicates (warning), PII values = possible personal data (warning) |
| `xlsx_check` | `format.xlsx.openable/sheets/hidden/macros/tabular/pii` | Workbook opens, sheet list, hidden sheets, VBA macros, tabular shape, structured-PII sample (first 1k data rows per sheet) | Hidden sheets, macros (warning — preservation risk), PII values (warning) |
| `sav_check` (`pyreadstat`) | `format.spss.openable/dictionary/encoding/labels` | SPSS opens, variable dictionary, encoding, value labels | Unreadable file (error), missing labels |
| `dta_check` (`pyreadstat`) | `format.stata.*` (also `pii`) | As SPSS plus structured-PII scan (piigex + CA pack) on character columns | Same family + PII |
| `sas7bdat_check` (`pyreadstat`) | `format.sas.format_detected/openable/dictionary/encoding/labels` | 128-byte `SAS FILE` magic, then as SPSS | Non-SAS file with `.sas7bdat` extension |
| `json_check` | `format.json.valid` | Strict parse (files over 64 MiB get a too-large warning instead of a full parse) | Unparseable JSON (error) |
| `xml_check` (`lxml`) | `format.xml.valid` | Well-formedness | Malformed XML (error) |
| `ipynb_check` | `format.ipynb.valid/cells/executed` | Notebook JSON (same 64 MiB cap), cell inventory, execution counts | Invalid notebook (error), unexecuted cells (warning) |
| `sqlite_check` | `format.sqlite.valid/manifest` | DB opens, full `integrity_check` (all rows), table inventory | Corrupt DB (error) |
| `hdf5_check` (`h5py`) | `format.hdf5.openable/external_links` | File opens, external links; object walk capped at 5k (`truncated` when partial) | Dangling external links (warning) |
| `nc_check` (`netCDF4`) | `format.netcdf.openable/metadata/spatial/data_health` | Opens, variables/dimensions, CRS/georeferencing, NaN sampling on capped per-dimension slices | Missing CRS (warning), all-NaN variable |
| `gpkg_check` | `format.gpkg.valid/layers/crs` | Pure-SQLite `gpkg_*` tables, layers, SRS | Missing geometry tables (error) |
| `tiff_check` (`tifffile`) | `format.tiff.valid` | Header/pages parse | Corrupt TIFF (error) |
| `images_check` (`Pillow`) | `format.images.valid` | Raster opens, mode/size | Unreadable/truncated image (error) |
| `pdf_check` (`pypdf`) | `format.pdf.openable/text` | Opens, page count, extractable text sampled on the first 3 pages | No extractable text on sampled pages — scanned PDF needing OCR (warning) |
| `text_check` | `format.text.readable/line_endings/control_chars/pii` | Encoding, line-ending mix, control characters, structured-PII scan on the 1 MiB sample | Mixed endings, control chars, PII values (warning) |
| `code_check` | `format.code.readable/todo_markers` | Readable text (first 1 MiB), TODO/FIXME scan | TODO markers (warning) |
| `secret_check` | `format.secrets` | hush-scan (regex + entropy) over the first **5 MiB** of code/text/config files (`.py .r .do .md .yml .env …`) | Potential secrets: API keys, tokens, private keys, high-entropy strings (warning); findings list capped at 20 with explicit “showing first N of M” copy |
| `containers_check` | `format.containers.valid/unsafe_entry/encrypted` | Zip integrity (`testzip`), tar members, traversal (`..`/absolute) entries, encrypted entries; inspection capped at 10k members / 2 GiB uncompressed | Corrupt archive (error), traversal entries + encrypted members (warning) |
| `fastq_check` | `format.fastq.valid/metadata` | Gzip-aware 4-line record validation (header/`+`/seq-qual length agreement), read length/GC on capped sample | Malformed records incl. length mismatches (warning), no valid reads (error) |
| `extensions_check` (dataset) | `inventory.extensions/zero_byte/executables/system_junk` | Extension census, 0-byte files, executables, OS junk (nested `__MACOSX` dirs included) | 0-byte (error), executables/junk (warning) |

MATLAB `.mat` (and any other format without a check module) is reported once per
dataset as `inventory.unchecked_types` (warning) — manual review required.

## Download verification (not a check, a gate)

Before checks run, `DownloadManager.verify()` rehashes every staged file against
the Dataverse-recorded checksum (`md5`/`sha1`). Mismatches block silently —
they are shown as `checksum mismatch: <path>` with expected/actual hashes, and
for tabular `.tab` derivatives (server-regenerated ingest products) the message
includes the file's UNF for manual comparison — see "Checksum problems" in
`docs/user-guide.md`.
