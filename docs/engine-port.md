# Engine port: R -> Python

The check engine re-implements the inspectors from [CUR_Res_CurationTools](../CUR_Res_CurationTools) in Python so the desktop app ships self-contained. Bundling portable R was rejected as a fallback of last resort: base R is ~100 MB and the required packages (tidyverse, haven, exiftoolr, …) push a portable installation to ~400 MB. Python covers every format with much smaller footprint (~70 MB lite zip, ~158 MB unpacked).

## Status

Phase 1 complete: **20 check modules (19 R inspectors + dataset-level extensions/fastq) ported** and verified. The suite is **53 tests passing** (`engine/tests/test_port_spike.py`, `engine/tests/test_formats.py`, `engine/tests/test_dataverse.py`, `engine/tests/test_runner.py`; one `RuntimeWarning` from numpy binary is expected). MATLAB `.mat` (`Scripts/Inspect_mat_Script.R` → `scipy.io`) remains **deferred** to keep `scipy` optional — `mat_check.py` does not exist; if added, it would be lazy-imported like the other heavy libs.

Notable findings and divergences from the R scripts:

- **sas7bdat**: the `SAS FILE` magic sits at offset 80, so header detection reads 128 bytes.
- **gpkg**: pure-SQLite implementation via the `gpkg_*` standard tables — no GDAL/sf dependency.
- **netcdf**: first-variable NaN sampling uses per-dimension capped slices instead of reading the whole variable.
- **containers**: the R script targets compressed archives (.zip/.tar/.7z), not container images; the Python check follows that scope and adds zip integrity (`testzip`) plus encrypted-member detection.
- **fastq**: transparently handles gzip-compressed files; validates record structure and computes read length/GC on a capped sample (ShortRead parity).
- **csv**: delimiter sniffing with comma fallback; ragged-row, duplicate-row and email-PII scans mirror the health-check report.
- **xlsx**: `openpyxl` in `read_only` mode with explicit `close()`.
- **images**: synthetic fixtures (no raster samples in CUR data); `tiff` uses `tifffile`.
- Optional libraries degrade gracefully: a missing dependency yields a `level="warning"` “check not executed — pip install …” result (surfaced in the **Curation checks** tab as `Missing: pip install …`) rather than an error, enabling the lite build.

## Port matrix

| R script (CUR repo) | Python module | Key library | Sample data for parity tests | Status |
| --- | --- | --- | --- | --- |
| `Scripts/Inspect_Extensions_Script.R` | `extensions_check.py` | stdlib + optional exiftool | `data/Inspect_Extensions/` | **ported** (dataset-level) |
| `Scripts/Inspect_csv_Script.R` | `csv_check.py` | stdlib `csv`, `chardet` | `data/Inspect_csv*` | **ported** |
| `Scripts/Inspect_xlsx_Script.R` | `xlsx_check.py` | `openpyxl` | `data/Inspect_xlsx/` | **ported** |
| `Scripts/Inspect_sav_Script.R` | `sav_check.py` | `pyreadstat` | `data/Inspect_sav/` | **ported** |
| `Scripts/Inspect_sas7bdat_Script.R` | `sas7bdat_check.py` | `pyreadstat` | `data/Inspect_sas7bdat/` | **ported** |
| `Scripts/Inspect_dta_Script.R` | `dta_check.py` | `pyreadstat` | `data/Inspect_dta/` | **ported** |
| `Scripts/Inspect_json_Script.R` | `json_check.py` | stdlib `json` | `data/Inspect_json*` | **ported** |
| `Scripts/Inspect_xml_Script.R` | `xml_check.py` | `lxml` | `data/Inspect_xml/` | **ported** |
| `Scripts/Inspect_ipynb_Script.R` | `ipynb_check.py` | stdlib `json` | `data/Inspect_ipynb/` | **ported** |
| `Scripts/Inspect_sqlite_Script.R` | `sqlite_check.py` | stdlib `sqlite3` | `data/Inspect_sqlite/` | **ported** |
| `Scripts/Inspect_hdf5_Script.R` | `hdf5_check.py` | `h5py` | `data/Inspect_hdf5/` | **ported** |
| `Scripts/Inspect_nc_Script.R` | `nc_check.py` | `netCDF4` | `data/Inspect_nc/`, `data/Inspect_xml/*.nc` | **ported** |
| `Scripts/Inspect_gpkg_Script.R` | `gpkg_check.py` | stdlib `sqlite3` (GeoPackage is SQLite) | `data/Inspect_gpkg/` | **ported** |
| `Scripts/Inspect_Tiff_Script.R` | `tiff_check.py` | `tifffile` | `data/Inspect_tiff/` | **ported** |
| `Scripts/Inspect_Images_Script.R` | `images_check.py` | `Pillow` | synthetic (no raster samples in CUR data) | **ported** |
| `Scripts/Inspect_PDF_Script.R` | `pdf_check.py` | `pypdf` | `data/Inspect_pdf/` | **ported** |
| `Scripts/Inspect_OCR_Script.R` | `pdf_check.py` (OCR mode) | optional tesseract | — | stub (degrades to “not executed”) |
| `Scripts/Inspect_Text_Script.R` | `text_check.py` | stdlib, `chardet` | `data/Inspect_Text/` | **ported** |
| `Scripts/Inspect_Code_Script.R` | `code_check.py` | stdlib parsing | `data/Inspect_rCode/` | **ported** |
| `Scripts/Inspect_Containers_Script.R` | `containers_check.py` | stdlib `zipfile`/`tarfile` | `data/Inspect_Containers/` | **ported** |
| `Scripts/check_fastq.R` | `fastq_check.py` | stdlib text parsing (gzip-aware) | synthetic fixtures | **ported** |
| `R/functions/frdr_filename_check.R` | — (not ported; executables/junk covered by `extensions_check`) | stdlib | — | skipped |
| `R/functions/validate_schema.R` | — (not ported) | stdlib | — | skipped |
| `Scripts/Inspect_mat_Script.R` | — (no module; `.mat` surfaces via `inventory.unchecked_types`) | `scipy.io` (deferred) | `data/Inspect_mat/` | **deferred** — not included in lite build |

Runner: `engine/runner.py:run_report` walks a staged dir and aggregates into `DatasetReport`; `list_planned_checks` enumerates which checks apply to a file list (used by the **Curation checks** tab).

## Go/no-go criteria (Phase 1 spike — met)

Prototype the three hardest formats first: `sas7bdat`, `gpkg`, `nc`/`hdf5`. A port is a **go** when:

1. Every check in the R script has a Python equivalent with the same pass/fail semantics.
2. Running both engines on the same `data/` sample directory yields the same findings (module CSV output vs. `DatasetReport` JSON) for the covered checks.
3. Runtime on the largest sample stays within 2x the R runtime.

If parity cannot be reached for a specific format, that check degrades to a documented “not executed” state rather than blocking the app; the fallback option (portable R bundle, ~400 MB) applies only if multiple formats fail — not needed.

## Maintenance note

The R book remains the authoritative R reference; the Python engine is the app runtime. Parity tests (`pytest -q` — 53 tests) are the contract that keeps the two in sync — they must run in CI as the R scripts evolve.
