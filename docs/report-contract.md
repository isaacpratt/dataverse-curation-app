# Report contract

One JSON structure — DatasetReport (engine/report.py) — shared by the engine, the GUI, and headless export. The GUI renders it directly and never learns individual checks.

## Shape of a report
engine/checks/base.py:CheckResult serializes with to_dict()/from_dict() (identity round-trip). FileEntry validates on load (path, size_bytes required).
```
{
"persistent_id": "doi:10.5072/FK2/EXAMPLE",
"label": "Example dataset title",
"engine_version": "0.1.0",
"timestamp": "2026-08-26T12:00:00+00:00",
"dataset_checks": [
    {"check_id": "inventory.extensions", "level": "info", "passed": true,
     "message": "3 files; .csv: 2, .xlsx: 1", "details": {"counts": {".csv": 2, ".xlsx": 1}}},
    {"check_id": "inventory.unchecked_types", "level": "warning", "passed": false,
     "message": "1 file(s) with no automated check (.mat) — manual review required",
     "details": {"extensions": [".mat"]}}
],
"files": [
    {"path": "data/raw.csv", "size_bytes": 12345, "mime_type": "text/csv",
     "checks": [
       {"check_id": "format.csv.structure", "level": "warning", "passed": false,
        "message": "Mixed line endings detected", "details": {"line_endings": {"LF": 900, "CRLF": 3}}},
       {"check_id": "format.xlsx.openable", "level": "warning", "passed": true,
        "message": "Missing: pip install openpyxl — check not executed", "details": {"skipped": true}}
     ]},
    {"path": "DataDictionary.xlsx", "size_bytes": 100203,
     "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "checks": []}
]
}
```

## Field semantics

| Field | Semantics |
| --- | --- |
| persistent_id, label | Dataset identity, from the inventory / detail header |
| engine_version | Schema version; the GUI guards incompatible payloads |
| timestamp | ISO-8601 UTC production time (datetime.now(timezone.utc).isoformat()) |
| dataset_checks | Whole-dataset findings: extension census (inventory.extensions + zero_byte/executables/system_junk), access restrictions (inventory.restricted_files/inventory.embargoed_files — file names, embargo dates, terms of access) and the no-automated-check hint (inventory.unchecked_types) |
| files[] | One entry per staged file (path relative POSIX, size_bytes, mime_type). Empty checks = no check applied or file skipped. Which list a finding lands in follows the check's declared scope ("dataset" → dataset_checks, "file" → that file's checks), never its extensions. files[] feeds the File checks section (folder → file → check tree); dataset_checks feeds Dataset checks. The two sections never repeat a finding, and each summary counts its own list only. |
| checks[] | One CheckResult per check that ran on the file (or dataset): check_id, level, passed, message, details |

## Levels and badges

| Badge | Level | Meaning | GUI |
| --- | --- | --- | --- |
| PASS | info + passed:true | Informational; no action (e.g. “NetCDF variables: 12”) | blue badge |
| WARN | warning | Review; likely a fix or a note to the researcher (incl. “check not executed”) | amber badge |
| FAIL | error + passed:false | Integrity problem (unparseable, corrupt, checksum mismatch) | red badge |
| ○ SKIPPED | warning + passed:true + details.skipped | Could not run (missing lib, encrypted, size caps, legacy, unreadable) via _util.skipped(); classified by engine/status.py:classify | muted badge |

Always-emit: when a module runs, it emits exactly one CheckResult per owned check_id — passes included. Absent IDs mean “never ran”, never a silent pass. status.summarize() aggregates passed / failed-error / failed-warning / skipped / total; file_status() rolls a file row up to one label.

## Finding-list caps

details may cap long lists while details.count keeps the full total; the message always discloses it — e.g. analysis.py: 115 potential secret(s) — showing first 20 of 115, data.csv: 47 possible PII value(s) — showing first 10 of 47 sample(s).

## Check-ID namespaces

| Namespace | Examples | Scope |
| --- | --- | --- |
| inventory.* | inventory.extensions, inventory.zero_byte, inventory.executables, inventory.system_junk, inventory.restricted_files, inventory.embargoed_files, inventory.unchecked_types | dataset-level (22 registered modules in engine/checks/__init__.py:registry) |
| format.<format>.* | format.csv.structure, format.gpkg.layers, format.pdf.text, format.secrets | per-file |

Registered checks live in engine/checks/__init__.py:registry (22 modules) — see Engine port for the R→Python matrix and Checks reference for semantics. engine/runner.py:list_planned_checks enumerates IDs before execution — shown in the Auto-Checks card as planned badges, then as results.

## Serialization and export

- DatasetReport.to_dict()/from_dict(), FileEntry likewise; save(path)/load(path) pretty-printed JSON (atomic temp-file + replace).
- to_markdown()/save_markdown(path) via engine/report_md.py — header, Summary, Dataset-checks table, Files grouped by directory, Skipped (missing libraries) section.
- GUI export (ui/dataset/actions_section.py:_on_export) → save dialog defaulting to workspace/downloads//reports/ → JSON + Markdown side-by-side (JSON canonical, Markdown derived). Export is logged to curation_actions; the manifest tree (ui/checks_tree.py: folder › file › check) renders from report.files[].checks.
- Headless mirrors it: engine/runner.py:run_report_to_file(dir, out, pid, fmt) with --format json|md|both (default json).
