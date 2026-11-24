---
page_type: reference
tgdp_template: Reference     # Reference | Glossary
audience: all                # curator | developer | contributor | all
---
# Command-line reference

Argument parser: `main.py:main()` (`argparse`, description from `t("app.cli.description")` = "Dataverse Docent"). Verbatim help from `uv run python main.py --headless --help`:

```text
usage: main.py [-h] [--headless] [--gallery] [--out OUT]
               [--format {json,md,both}] [--persistent-id PERSISTENT_ID]
               [--export-record] [--config CONFIG] [--dataverse DATAVERSE]
               [dataset_dir]

Dataverse Docent

positional arguments:
  dataset_dir           staged dataset directory (headless mode)

options:
  -h, --help            show this help message and exit
  --headless            run checks on a local directory and write a JSON
                        report
  --gallery             open the component gallery (every kit component on one
                        page)
  --out OUT             output report path
  --format {json,md,both}
                        report format: json, md, or both (default: json)
  --persistent-id PERSISTENT_ID
                        dataset persistent ID
  --export-record       also write a dated curation-record folder beside the
                        report
  --config CONFIG       path to config.json (default: ./config.json)
  --dataverse DATAVERSE
                        override dataverse base URL (e.g.
                        https://demo.borealisdata.ca)
```

## Arguments and flags

| Argument | Form | Default | Exact help text | Notes |
| --- | --- | --- | --- | --- |
| `-h`, `--help` | flag | — | show this help message and exit | Built-in argparse action; exits before any work |
| `dataset_dir` | optional positional | none | staged dataset directory (headless mode) | Required when `--headless` is set; must exist and be a directory |
| `--headless` | store_true | `False` | run checks on a local directory and write a JSON report | Selects the headless path; no Qt, config or network |
| `--gallery` | store_true | `False` | open the component gallery (every kit component on one page) | GUI-only; needs no server, token or workspace |
| `--out` | value | `curation_report.json` | output report path | Parent directories are created; output-format write failures return exit 2 |
| `--format` | choice | `json` | report format: json, md, or both (default: json) | Choices: `json`, `md`, `both`; headless only |
| `--persistent-id` | value | `""` | dataset persistent ID | Recorded in the DatasetReport; headless only |
| `--export-record` | store_true | `False` | also write a dated curation-record folder beside the report | Headless only; writes a dated `curation-record/<YYYYMMDD-HHMMSS>/` folder |
| `--config` | value | `config.json` | path to config.json (default: ./config.json) | GUI-only; rejected under `--headless` when non-default |
| `--dataverse` | value | `None` | override dataverse base URL (e.g. https://demo.borealisdata.ca) | GUI-only; overrides the configured base URL; rejected under `--headless` |

## Headless mode

Headless mode runs the check engine on a local staged directory and writes the [DatasetReport](report-contract.md). It performs no network calls and uses no API token.

| Rule | Behaviour |
| --- | --- |
| Directory required | Missing `dataset_dir` is an argparse error |
| GUI-only flags | Passing `--dataverse` or a non-default `--config` under `--headless` is an argparse error |
| Directory validation | A missing path or a path that is not a directory is an argparse error |
| Output directory | Created before the run; an `OSError` is an argparse error |
| Run failure | Any exception in `run_report_to_file`, or in the optional curation-record export, prints to stderr and returns exit 2 |
| Output summary | Prints a report-written line (written paths, file count, warning count), a synthesized verdict line, and, with `--export-record`, the record folder path |
| Format `both` | Writes JSON and Markdown side-by-side; the second path has the opposite suffix of `--out` |

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Clean — no error-level findings |
| 1 | One or more error-level findings (`level == "error"` with `passed: false`) in `dataset_checks` or any `files[].checks`; warnings alone do not fail the run |
| 2 | Usage or IO failure — invalid/missing directory, GUI-only flag under headless, uncreatable output directory, or a run/export exception |

## See also

- [Report contract](report-contract.md)
- [Configuration reference](configuration.md)
- [Glossary](glossary.md)
