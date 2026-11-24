# tools/

Operational helpers. None of these are imported by the app at runtime; the
one timing module that is (`startup_probe`) lives in `curation/`. Every
script is run directly or through a `poe` task from the repository root.

| Path | poe task | What it does |
| --- | --- | --- |
| `build/build_app.py` | `poe build` | PyInstaller onedir build into `dist/DataverseDocent/`; the flags live here and nowhere else |
| `build/pack_app.py` | `poe pack` | Packs that folder into `dist/releases/` with Velopack (Setup.exe, portable zip, nupkg, feed) |
| `build/check_pack.py` | `poe check-pack` | Verifies an existing `dist/releases/` (names, versions, nuspec, feed) without rebuilding |
| `build/check_version.py` | — | Fails when a release tag disagrees with `engine.__version__`; the release workflow runs it |
| `build/smoke_app.py` | `poe smoke` | Runs the frozen exe: `--headless --help` plus a CSV/PII probe |
| `build/clean_tree.py` | `poe clean` | Removes `build/`, `dist/`, `.pyi-cache/` and stray `*.spec` files |
| `audit/audit_deps.py` | `poe audit` | Vulnerability scan of the locked dependency set (pip-audit/OSV) |
| `audit/make_licenses.py` | `poe license-report` | Writes `dist/licenses.md`, the license inventory |
| `audit/make_sbom.py` | `poe sbom` | Writes the CycloneDX and SPDX SBOMs |
| `audit/make_notice.py` | `poe notice` | Writes `dist/NOTICE`, the attribution file |
| `audit/complexity_report.py` | `poe complexity` | Advisory radon report into `reports/complexity.md` (the gate is ruff C901) |
| `docs/check_doc_links.py` | `poe docs-links` | Offline relative-link and anchor check for the Markdown docs tree |
| `docs/check_external_links.py` | weekly `docs-links` workflow | External HTTP link check (scheduled, not part of the per-PR gate) |
| `docs/gen_checks_reference.py` | `poe docs-gen-checks` | Regenerate the Check ID index from the engine registry; `--check` verifies it |
| `docs/gen_cli_reference.py` | `poe docs-gen-cli` | Regenerate the CLI help and flag table from `main.build_parser()`; `--check` verifies it |
| `perf/bench_paint_window.py` | — | Measures the queue's paint window (25k synthetic rows); `--markdown` for the docs |
| `perf/bench_enrichment_cap.py` | — | Measures the enrichment cap (5k synthetic collection, simulated latency) |
| `probes/` | `poe probes` | Offscreen UI probes; see `probes/README.md` |
| `tests/` | `pytest` | Tests for these scripts (they run in the app gate) |

`poe release-artefacts` chains `license-report`, `notice` and `sbom`. The
build is one artefact; see `AGENTS.md` for the packaging workflow.
