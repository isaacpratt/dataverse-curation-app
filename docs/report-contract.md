# Report contract

The check engine and the GUI communicate through one JSON structure, `DatasetReport` (implemented in `engine/report.py:DatasetReport` + `FileEntry`, with `engine/checks/base.py:CheckResult`). The GUI renders this structure directly and does not know about individual checks. The same contract is used for headless export (`python main.py --headless <dir> --out report.json`).

## Structure

```json
{
  "persistent_id": "doi:10.5072/FK2/EXAMPLE",
  "label": "Example dataset title",
  "engine_version": "0.1.0",
  "timestamp": "2026-08-26T12:00:00+00:00",
  "dataset_checks": [
    {
      "check_id": "inventory.extensions",
      "level": "info",
      "passed": true,
      "message": "3 files; .csv: 2, .xlsx: 1",
      "details": { "counts": { ".csv": 2, ".xlsx": 1 } }
    },
    {
      "check_id": "inventory.unchecked_types",
      "level": "warning",
      "passed": false,
      "message": "1 file(s) with no automated check (.mat) — manual review required",
      "details": { "extensions": [".mat"] }
    }
  ],
  "files": [
    {
      "path": "data/raw.csv",
      "size_bytes": 12345,
      "mime_type": "text/csv",
      "checks": [
        {
          "check_id": "format.csv.structure",
          "level": "warning",
          "passed": false,
          "message": "Mixed line endings detected",
          "details": { "line_endings": { "LF": 900, "CRLF": 3 } }
        },
        {
          "check_id": "format.xlsx.openable",
          "level": "warning",
          "passed": true,
          "message": "Missing: pip install openpyxl — check not executed",
          "details": {}
        }
      ]
    },
    {
      "path": "DataDictionary.xlsx",
      "size_bytes": 100203,
      "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "checks": []
    }
  ]
}
```

## Field semantics

| Field | Semantics |
| --- | --- |
| `persistent_id`, `label` | Identity of the dataset, from the Dataverse inventory / detail header (`engine/report.py:DatasetReport.persistent_id/label`) |
| `engine_version` | Engine schema version; GUI uses it to guard incompatible payloads |
| `timestamp` | ISO-8601 UTC time the report was produced (`datetime.now(timezone.utc).isoformat()`) |
| `dataset_checks` | Findings that apply to the dataset as a whole: extension distribution (`inventory.extensions` + `zero_byte`/`executables`/`system_junk` flags) and the no-automated-check hint (`inventory.unchecked_types`) |
| `files[]` | One entry per staged file (`FileEntry: path` relative POSIX, `size_bytes`, `mime_type`); empty `checks` means no check applied to that format or file skipped |
| `checks[]` (`CheckResult`) | One entry per check that ran on this file (or at dataset level): `check_id`, `level`, `passed`, `message`, `details` dict |

### `CheckResult`

```python
@dataclass
class CheckResult:
    check_id: str          # e.g. "format.csv.structure"
    level: str             # "info" | "warning" | "error"
    passed: bool
    message: str           # human-readable, shown in UI + report
    details: Dict[str,Any] # structured payload (shown in tooltip)
```

Serialization: `CheckResult.to_dict()` / `from_dict()` (identity).

### `level` values

| Level | Meaning | GUI |
| --- | --- | --- |
| `info` | Informational finding; no action expected (e.g. "NetCDF variables: 12") | blue badge |
| `warning` | Curator should review; likely needs a fix or a note back to the researcher (e.g. non-ASCII filename, “check not executed”) | amber badge |
| `error` | Data integrity problem (e.g. CSV cannot be parsed, checksum mismatch) | red badge |

`passed` is always present: `true` = the check succeeded / policy met; `false` = the check found a violation. An `info` check is typically `passed: true` with details. A “check not executed” for a missing optional lib is `level="warning"` + `passed=True` with `message` noting `pip install …` plus `details.skipped=True` (explicit SKIPPED state — see `engine/status.py:classify`). Sub-checks that cannot run (encrypted input, size caps, legacy formats, unreadable files) use the same `warning`+`passed`+`details.skipped` shape via `_util.skipped()`.

Always-emit contract: when a module runs on a file (or dataset), it emits exactly one `CheckResult` per owned `check_id` — passes included (e.g. `inventory.zero_byte` reports "No zero-byte files", `format.csv.pii` reports "no PII values detected"). Absent IDs mean the module never ran, not a silent pass.

### Finding-list caps (secrets / PII)

`details` may cap long finding lists while `details.count` keeps the full total. The human-readable `message` always says when truncation happened, e.g. `analysis.py: 115 potential secret(s) — showing first 20 of 115` or `data.csv: 47 possible PII value(s) — showing first 10 of 47 sample(s)`.

## Check ID namespaces

| Namespace | Examples | Scope |
| --- | --- | --- |
| `inventory.*` | `inventory.extensions`, `inventory.zero_byte`, `inventory.executables`, `inventory.system_junk` | dataset-level |
| `format.<format>.*` | `format.csv.structure`, `format.gpkg.layers`, `format.pdf.text`, `format.secrets` | per-file |

Registered checks live in `engine/checks/__init__.py:registry` (21 modules); see `docs/engine-port.md` and `docs/checks-reference.md`. `engine/runner.py:list_planned_checks` enumerates which IDs will run for a file list before execution — displayed in the **Auto-Checks** card as planned badges, then as results.

## Serialization

- `DatasetReport.to_dict()` / `from_dict()` (pure Python objects), `FileEntry` likewise.
- `DatasetReport.save(path)` / `load(path)` write/read pretty-printed JSON.
- The GUI exports reports via `ui/dataset_detail.py:_on_export` → save dialog defaulting to `workspace/downloads/<id>/reports/` → `DatasetReport.save` + `save_markdown` (JSON + Markdown side-by-side; JSON is canonical, Markdown is a derived view via `engine/report_md.py`). The detail view renders the manifest tree (`ui/checks_tree.py`: folder > file > check) from `report.files[].checks` and dataset-level rows from `report.dataset_checks`. Headless `--format json|md|both` mirrors the same outputs (`engine/runner.py:run_report_to_file`).
- The detail view holds the in-memory `_report` after `CheckWorker.finished`; `storage.py:curation_actions` records the export event.
