---
page_type: explanation
tgdp_template: Concept       # Concept | Explanation
audience: developer          # curator | developer | contributor | all
---
# Why the engine is a Python port

The check engine re-implements the inspectors from `CUR_Res_CurationTools` in Python. No R runtime ships with the app. This page records why that choice was made, how parity is established, where the port deliberately differs from the R scripts, and what had to be true before the project could proceed. It is a design record; the current list of checks and what each examines belongs in the [checks reference](../reference/checks.md).

## Why Python rather than portable R

Bundling portable R was evaluated as a last resort. Base R is roughly 100 MB on its own, and the required packages — tidyverse, haven, exiftoolr and others — push a portable install toward 400 MB. The Python engine ships inside a release zip of about 102 MB (the unpacked onedir folder is roughly 160 MB) with parity established by the opt-in sample tests, not by inspection.

Size was not the only argument. Python checks are pure functions of local files: they import lazily, run headlessly, and share a report contract with the GUI. That shape lets the same code power the desktop app and `main.py --headless`, and it keeps the engine importable in tests without a window. R was retained only during the port as the oracle for parity verification. The R book remains the authoritative description of what a check means; the Python engine is the runtime.

## How parity is established

The port does not assume equivalence from reading two implementations. For each format, the process was to run the R inspector on a sample from `CUR_Res_CurationTools/data/`, run the matching Python check on the same directory, dump the `DatasetReport` JSON, and assert equivalent findings. Differences that were understood and accepted were encoded as fixtures so the comparison stays honest as the R scripts evolve.

The hardest formats — `sas7bdat`, `gpkg` and `nc`/`hdf5` — were prototyped first. That ordering is the point of a spike: if the difficult cases cannot reach parity, the simpler ones cannot rescue the decision. The sample-based parity tests are opt-in (`uv run poe samples`) because CI has no sibling `CUR_Res_CurationTools` clone; a gate whose result depends on a developer's disk is not a gate. The comparison is maintained by whoever runs that task after changing a check, not by CI.

## Notable divergences

Exact equivalence of pass/fail semantics does not mean identical implementation. These differences are intentional and recorded:

| Format | Why the implementation differs |
| --- | --- |
| `sas7bdat` | The SAS FILE magic sits at offset 80, so header detection reads 128 bytes. |
| `gpkg` | Read through the standard `gpkg_*` tables in pure SQLite; no GDAL or `sf` dependency. |
| `netcdf` | First-variable NaN sampling uses per-dimension capped slices rather than whole-variable reads. |
| archives (`containers_check`) | The R targets compressed archives (`.zip`, `.tar`, `.7z`), not container images; Python follows that scope and adds archive integrity and encrypted-member detection. |
| `fastq` | Transparent gzip handling with structure and read-length/GC checks on a capped sample, matching the ShortRead intent. |
| `csv` | Delimiter sniffing with a comma fallback; ragged rows, duplicates and email PII mirror the health-check report. |
| `xlsx` | `openpyxl` in read-only mode with an explicit close. |
| images / tiff | Synthetic fixtures, because the source sample set has no raster files; TIFF uses `tifffile`. |
| missing libraries | A missing optional library yields a warning level with "check not executed — pip install …", never a failure; the shipped build carries all of them. |

Two checks, `secret_check.py` and `access_check.py`, are app-level additions with no single R counterpart. They follow the same engine contract. One capability remains deferred: MATLAB `.mat` inspection would need `scipy.io`, and keeping `scipy` out of the dependency set was worth more than covering that format. `.mat` files surface through the inventory's unchecked-types hint, and adding the check later would use the same lazy-import pattern as the other heavy libraries.

## Scope is a declaration

The original matrix inferred a dataset-level check from an empty extension set, which made a cross-file check that reads `.csv` impossible to express without hand-dispatch. Every check now declares `scope = "dataset"` or `"file"`; the registry refuses a class that omits it, and the dispatcher routes on the declaration. Extensions only say which files a check reads. The two axes are independent, so a cross-file check may keep its extensions and still report once for the dataset. The report JSON is unchanged by this, which matters because saved dispositions depend on stable finding keys.

## Go / no-go criteria

The spike defined the decision before the work began, so the result would be a decision rather than a retrospective justification. The port could proceed when three conditions held: every R check had a Python equivalent with the same pass/fail semantics; both engines produced the same findings on the same sample data; and runtime on the largest sample stayed within twice the R runtime.

A single failing format was acceptable — it degrades to a documented "not executed" result rather than blocking a review. Multiple failures would have triggered the portable-R fallback. That fallback was not needed. The criteria were met at the end of the port; maintenance now consists of re-running `uv run poe samples` when the R scripts or the Python checks change, since CI cannot run those sample-based tests.

## The port as a design record

The R-script-to-module mapping — keyed by R script, Python module, library, parity sample and status — was a historical design record kept alongside the original R scripts; it documented a completed port rather than telling anyone how to do anything. That matrix was retired with the original hand-authored HTML pages: the repository no longer publishes it. What remains is the rationale on this page, the divergences and go/no-go criteria recorded here, and the current behaviour in the [checks reference](../reference/checks.md). The decision log in [Architecture](architecture.md#decision-log) records when the port was accepted.
