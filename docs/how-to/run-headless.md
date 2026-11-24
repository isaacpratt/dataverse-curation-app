---
page_type: how-to
tgdp_template: How-to
audience: all
---

# Run checks from the command line

Headless mode runs the check engine on a staged directory — a local folder that holds the dataset's files — without opening the GUI or contacting a Dataverse instance. Replace `<staged_dir>` in the commands below with the path to that folder. For the full list of flags, see the [CLI reference](../reference/cli.md).

## Steps

1. Open PowerShell in the repository root. If you are using a source checkout, make sure you have run `uv sync` once.

2. Run the checks and write a JSON report:

   ```powershell
   uv run python main.py --headless <staged_dir> --out report.json
   ```

3. Add a persistent ID — the permanent identifier for the dataset, such as a DOI — to label the report:

   ```powershell
   uv run python main.py --headless <staged_dir> --out report.json --persistent-id doi:10.5072/FK2/EXAMPLE
   ```

4. Write both the JSON report and its Markdown view. Use `--format json`, `--format md`, or `--format both` (the default is `json`):

   ```powershell
   uv run python main.py --headless <staged_dir> --out report.json --format both --persistent-id doi:10.5072/FK2/EXAMPLE
   ```

   With `--format both`, the Markdown file is written beside the JSON file using the same base name.

5. Add `--export-record` to write a curation-record folder beside the report:

   ```powershell
   uv run python main.py --headless <staged_dir> --out report.json --format json --persistent-id doi:10.5072/FK2/EXAMPLE --export-record
   ```

6. Read the exit code to decide what to do next.

   | Exit code | Meaning |
   | --- | --- |
   | `0` | No error-level findings. |
   | `1` | At least one error-level finding; warnings alone do not fail the run. |
   | `2` | Usage or I/O failure (for example a missing directory). |

7. The `--config` and `--dataverse` flags are GUI-only. Headless runs reject them and use only the local staged directory.

For a frozen release, replace `uv run python main.py` with `DataverseDocent.exe` in these commands; the flags and exit codes are the same.
