"""CSV/TSV health check.

Port of CUR_Res_CurationTools Scripts/Inspect_csv_Script.R: encoding guess,
parse with delimiter sniffing, ragged-row detection, missing-cell share,
duplicate rows and a structured-PII scan on a sample (piigex + CA pack).
"""

import csv
from pathlib import Path

from engine.checks._util import detect_encoding, find_pii, pii_result
from engine.checks.base import Check, CheckResult

try:
    from engine.constants import CAPS as _CAPS

    _SAMPLE_BYTES = _CAPS.sample_bytes
    _PII_SAMPLE_ROWS = _CAPS.pii_sample_rows
    # Upper bound for the full-parse pass: beyond this the file is sampled and
    # the content result carries truncated=True (a 5 GB "csv" must not OOM us).
    _MAX_ROWS_SCANNED = _CAPS.max_rows_scanned
    # Duplicate tracking is capped too: retain at most this many distinct row
    # hashes instead of every row tuple.
    _MAX_SEEN_ROWS = _CAPS.max_seen_rows
    _SNIFF_BYTES = _CAPS.sniff_bytes
except Exception:  # pragma: no cover - constants import must never break checks
    _SAMPLE_BYTES = 1 << 20
    _PII_SAMPLE_ROWS = 1000
    _MAX_ROWS_SCANNED = 50000
    _MAX_SEEN_ROWS = 20000
    _SNIFF_BYTES = 32 << 10


class CsvCheck(Check):
    """CSV/TSV check - port of the CUR_Res_CurationTools R inspector."""

    check_id = "format.csv"
    extensions = {".csv", ".tsv"}

    def run(self, files: list[Path]) -> list[CheckResult]:
        from engine.checks._util import run_per_file

        return run_per_file(self, files, self._run_one)

    def _run_one(self, path: Path) -> list[CheckResult]:
        from engine.checks._util import skipped as _skipped

        name = path.name
        size = path.stat().st_size
        if size == 0:
            return [
                CheckResult(
                    check_id="format.csv.openable",
                    level="error",
                    passed=False,
                    message=f"{name}: file is empty",
                ),
                _skipped(
                    "format.csv.structure",
                    f"{name}: structure skipped (empty file)",
                ),
                _skipped(
                    "format.csv.content",
                    f"{name}: content skipped (empty file)",
                ),
                _skipped(
                    "format.csv.pii",
                    f"{name}: PII scan skipped (empty file)",
                ),
            ]

        encoding = detect_encoding(path)
        delimiter = "\t" if path.suffix.lower() == ".tsv" else None

        openable = CheckResult(
            check_id="format.csv.openable",
            level="info",
            passed=True,
            message=f"{name}: parsed ({encoding})",
            details={"encoding": encoding},
        )

        # Single open: sniff on a 32KB prefix, then seek(0) for the full
        # parse (was: two full opens + 1MB sniff). Module constants are used
        # (not CAPS directly) so tests can monkeypatch caps.
        with open(path, newline="", encoding=encoding, errors="replace") as handle:
            sample = handle.read(_SNIFF_BYTES)
            if delimiter is None:
                try:
                    delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
                except csv.Error:
                    delimiter = ","
            handle.seek(0)
            reader = csv.reader(handle, delimiter=delimiter)
            rows = 0
            widths = set()
            duplicates = 0
            seen_rows: set[int] = set()
            truncated = False
            pii_findings = []
            for row in reader:
                rows += 1
                if rows > _MAX_ROWS_SCANNED:
                    truncated = True
                    break
                widths.add(len(row))
                key = hash(tuple(row))
                if key in seen_rows:
                    duplicates += 1
                elif len(seen_rows) < _MAX_SEEN_ROWS:
                    seen_rows.add(key)
                if rows <= _PII_SAMPLE_ROWS:
                    pii_findings.extend(find_pii(" ".join(row)))
        # Single-pass above already populated rows/widths/duplicates.

        width = next(iter(widths), 0)
        if not widths:
            structure = CheckResult(
                check_id="format.csv.structure",
                level="warning",
                passed=False,
                message=f"{name}: no data rows found",
            )
        else:
            structure = CheckResult(
                check_id="format.csv.structure",
                level="warning" if len(widths) > 1 else "info",
                passed=len(widths) <= 1,
                message=(
                    f"{name}: ragged rows detected "
                    f"(row widths: {sorted(widths)})"
                    if len(widths) > 1
                    else f"{name}: consistent {width} columns"
                ),
            )

        content = CheckResult(
            check_id="format.csv.content",
            level="info",
            passed=True,
            message=(
                f"{name}: {rows}{'+' if truncated else ''} rows, "
                f"{duplicates} duplicate row(s)"
                + (" (sampled — file exceeds scan cap)" if truncated else "")
            ),
            details={"rows": rows, "duplicates": duplicates, "truncated": truncated},
        )

        results = [openable, structure, content]

        # Dedupe across rows (same value in many rows → one sample entry).
        seen_pii = set()
        unique_pii = []
        for item in pii_findings:
            pii_key = (item["type"], item["value"])
            if pii_key not in seen_pii:
                seen_pii.add(pii_key)
                unique_pii.append(item)

        results.append(
            pii_result(
                "format.csv.pii",
                name,
                unique_pii,
                scope=f"in first {_PII_SAMPLE_ROWS} rows",
            )
        )
        return results
