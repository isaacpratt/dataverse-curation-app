# Engine port: R → Python

Self-contained re-implementation of the CUR_Res_CurationTools inspectors — no R runtime ships with the app.

Phase 1 complete22 modules ported969 testsMATLAB .mat deferred

## Why Python, not portable R

Bundling portable R was evaluated and rejected as a last resort: base R is ~100 MB and the required packages (tidyverse, haven, exiftoolr, …) push a portable install to ~400 MB. The Python engine ships at ~102 MB (portable zip, ~229 MB unpacked) with identical pass/fail semantics — verified by parity tests, not by inspection.

## Status

Phase 1 complete: 22 check modules ported and verified; 969 tests passing. Run pytest --collect-only -q for the live count (77 engine + 345 curation + 26 tools + 521 UI). MATLAB .mat (Scripts/Inspect_mat_Script.R → scipy.io) stays deferred to keep scipy optional — mat_check.py does not exist; .mat files surface via inventory.unchecked_types. If added, it would be lazy-imported like the other heavy libs.

## Notable divergences from the R scripts

| Format | Divergence |
| --- | --- |
| sas7bdat | SAS FILE magic sits at offset 80 → header detection reads 128 bytes |
| gpkg | Pure-SQLite via the gpkg_* standard tables — no GDAL/sf dependency |
| netcdf | First-variable NaN sampling uses per-dimension capped slices, not whole-variable reads |
| containers | R targets compressed archives (.zip/.tar/.7z), not container images; Python follows that scope + testzip + encrypted-member detection |
| fastq | Transparent gzip handling; structure + read length/GC on a capped sample (ShortRead parity) |
| csv | Delimiter sniffing with comma fallback; ragged/duplicate/email-PII mirrors the health-check report |
| xlsx | openpyxl in read_only mode with explicit close() |
| images / tiff | Synthetic fixtures (no raster samples in CUR data); tiff uses tifffile |
| Missing libs | level="warning" “check not executed — pip install …” (Auto-Checks tab: Missing: pip install …); a missing library is a warning, never a failure, and the shipped build carries all of them |

## Port matrix

The Status column notes a dataset-level check. That is now a declaration, not an inference: every check class carries scope = "dataset" or "file" (Check.scope), the registry refuses a class that does not, and the dispatcher routes on it — so extensions only says which files a check reads (docs/html/checks-reference.html lists each check's scope). A cross-file check may therefore keep its extensions and still report once for the dataset.

| R script (CUR repo) | Python module | Key library | Parity sample | Status |
| --- | --- | --- | --- | --- |
| Inspect_Extensions_Script.R | extensions_check.py | stdlib + optional exiftool | data/Inspect_Extensions/ | ported (dataset-level) |
| Inspect_csv_Script.R | csv_check.py | stdlib csv, chardet | data/Inspect_csv* | ported |
| Inspect_xlsx_Script.R | xlsx_check.py | openpyxl | data/Inspect_xlsx/ | ported |
| Inspect_sav_Script.R | sav_check.py | pyreadstat | data/Inspect_sav/ | ported |
| Inspect_sas7bdat_Script.R | sas7bdat_check.py | pyreadstat | data/Inspect_sas7bdat/ | ported |
| Inspect_dta_Script.R | dta_check.py | pyreadstat | data/Inspect_dta/ | ported |
| Inspect_json_Script.R | json_check.py | stdlib json | data/Inspect_json* | ported |
| Inspect_xml_Script.R | xml_check.py | lxml | data/Inspect_xml/ | ported |
| Inspect_ipynb_Script.R | ipynb_check.py | stdlib json | data/Inspect_ipynb/ | ported |
| Inspect_sqlite_Script.R | sqlite_check.py | stdlib sqlite3 | data/Inspect_sqlite/ | ported |
| Inspect_hdf5_Script.R | hdf5_check.py | h5py | data/Inspect_hdf5/ | ported |
| Inspect_nc_Script.R | nc_check.py | netCDF4 | data/Inspect_nc/, data/Inspect_xml/*.nc | ported |
| Inspect_gpkg_Script.R | gpkg_check.py | stdlib sqlite3 | data/Inspect_gpkg/ | ported |
| Inspect_Tiff_Script.R | tiff_check.py | tifffile | data/Inspect_tiff/ | ported |
| Inspect_Images_Script.R | images_check.py | Pillow | synthetic | ported |
| Inspect_PDF_Script.R | pdf_check.py | pypdf | data/Inspect_pdf/ | ported |
| Inspect_OCR_Script.R | pdf_check.py (OCR mode) | optional tesseract | — | stub (degrades to “not executed”) |
| Inspect_Text_Script.R | text_check.py | stdlib, chardet | data/Inspect_Text/ | ported |
| Inspect_Code_Script.R | code_check.py | stdlib | data/Inspect_rCode/ | ported |
| Inspect_Containers_Script.R | containers_check.py | stdlib zipfile/tarfile | data/Inspect_Containers/ | ported |
| check_fastq.R | fastq_check.py | stdlib gzip-aware | synthetic | ported |
| frdr_filename_check.R | — (covered by extensions_check) | stdlib | — | skipped |
| validate_schema.R | — | stdlib | — | skipped |
| Inspect_mat_Script.R | — (via inventory.unchecked_types) | scipy.io (deferred) | data/Inspect_mat/ | deferred |

Plus secret_check.py (format.secrets, hush-scan over code/text/config) and access_check.py (inventory.restricted_files / inventory.embargoed_files) — app-level additions with no single R counterpart. Runner: engine/runner.py:run_report aggregates into DatasetReport; list_planned_checks powers the Auto-Checks tab.

## Go / no-go criteria (spike — met)

Prototyped the three hardest formats first (sas7bdat, gpkg, nc/hdf5). Go when (1) every R check has a Python equivalent with the same pass/fail semantics, (2) both engines yield the same findings on the same data/ samples, (3) runtime on the largest sample stays within 2× of R. Single-format failure degrades to documented “not executed” instead of blocking; portable R fallback only if multiple formats fail — not needed.

## Maintenance

The R book stays the authoritative reference; the Python engine is the runtime. Parity tests (pytest -q, CI .github/workflows/ci.yml) are the contract keeping them in sync and must run in CI as the R scripts evolve.
