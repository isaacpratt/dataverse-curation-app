"""Excel workbook inspection.

Port of CUR_Res_CurationTools Scripts/Inspect_xlsx_Script.R: structure scan
(hidden sheets, macros, legacy binary format) plus per-sheet dimensions,
header preview and a 'likely non-tabular' heuristic.
"""

from pathlib import Path
from typing import List

from engine.checks.base import Check, CheckResult


def _sheet_headers(workbook, sheet_name: str, max_cols: int = 5) -> tuple[List[str], bool]:
    worksheet = workbook[sheet_name]
    headers: List[str] = []
    for row in worksheet.iter_rows(min_row=1, max_row=1, max_col=max_cols, values_only=True):
        headers = [str(c) if c is not None else "" for c in row]
    messy = len(headers) <= 1 or any(
        h == "" or h.startswith("Unnamed") for h in headers
    )
    return headers, messy


class XlsxCheck(Check):
    """Excel check - port of the CUR_Res_CurationTools R inspector."""

    check_id = "format.xlsx"
    extensions = {".xlsx", ".xlsm", ".xls"}

    def run(self, files: List[Path]) -> List[CheckResult]:
        from engine.checks._util import run_per_file

        return run_per_file(self, files, self._run_one)

    def _run_one(self, path: Path) -> List[CheckResult]:
        from engine.checks._util import skipped as _skipped

        name = path.name
        suffix = path.suffix.lower()
        is_macro = suffix == ".xlsm"
        is_legacy = suffix == ".xls"

        if is_legacy:
            return [
                CheckResult(
                    check_id="format.xlsx.openable",
                    level="warning",
                    passed=False,
                    message=(
                        f"{name}: legacy binary .xls - convert to .xlsx "
                        "for long-term preservation"
                    ),
                ),
                _skipped(
                    "format.xlsx.sheets",
                    f"{name}: sheet scan skipped (legacy .xls)",
                ),
                _skipped(
                    "format.xlsx.hidden",
                    f"{name}: hidden-sheet scan skipped (legacy .xls)",
                ),
                _skipped(
                    "format.xlsx.macros",
                    f"{name}: macro scan skipped (legacy .xls)",
                ),
                _skipped(
                    "format.xlsx.tabular",
                    f"{name}: tabular scan skipped (legacy .xls)",
                ),
            ]

        try:
            import openpyxl
        except ImportError:
            from engine.checks._util import missing_library

            return [
                missing_library("format.xlsx.openable", "openpyxl"),
                _skipped(
                    "format.xlsx.sheets",
                    f"{name}: sheet scan skipped (openpyxl not installed)",
                ),
                _skipped(
                    "format.xlsx.hidden",
                    f"{name}: hidden-sheet scan skipped (openpyxl not installed)",
                ),
                _skipped(
                    "format.xlsx.macros",
                    f"{name}: macro scan skipped (openpyxl not installed)",
                ),
                _skipped(
                    "format.xlsx.tabular",
                    f"{name}: tabular scan skipped (openpyxl not installed)",
                ),
            ]

        workbook = openpyxl.load_workbook(str(path), read_only=True, keep_links=False)
        try:
            sheet_names = workbook.sheetnames
            hidden = [s for s in sheet_names if workbook[s].sheet_state != "visible"]

            sheets = []
            messy_sheets = []
            for sheet_name in sheet_names:
                # Cache worksheet handle (was: 3x workbook[s] lookups per sheet).
                ws = workbook[sheet_name]
                headers, messy = _sheet_headers(workbook, sheet_name)
                try:
                    dims = ws.calculate_dimension()
                except Exception:
                    dims = ""
                sheets.append({"name": sheet_name, "dimensions": dims})
                if messy:
                    messy_sheets.append(sheet_name)
        finally:
            workbook.close()

        openable = CheckResult(
            check_id="format.xlsx.openable",
            level="info",
            passed=True,
            message=f"{name}: opened ({len(sheet_names)} sheet(s))",
        )
        sheets_result = CheckResult(
            check_id="format.xlsx.sheets",
            level="info",
            passed=True,
            message=f"{name}: sheets: {', '.join(sheet_names)}",
            details={"sheets": sheets},
        )
        results = [openable, sheets_result]

        if hidden:
            results.append(
                CheckResult(
                    check_id="format.xlsx.hidden",
                    level="warning",
                    passed=False,
                    message=f"{name}: {len(hidden)} hidden sheet(s): {', '.join(hidden)}",
                    details={"hidden": hidden},
                )
            )
        else:
            results.append(
                CheckResult(
                    check_id="format.xlsx.hidden",
                    level="info",
                    passed=True,
                    message=f"{name}: no hidden sheets",
                    details={"hidden": []},
                )
            )
        if is_macro:
            results.append(
                CheckResult(
                    check_id="format.xlsx.macros",
                    level="warning",
                    passed=False,
                    message=f"{name}: macro-enabled workbook (.xlsm)",
                )
            )
        else:
            from engine.checks._util import skipped as _skipped2

            if suffix == ".xlsm":
                results.append(
                    CheckResult(
                        check_id="format.xlsx.macros",
                        level="info",
                        passed=True,
                        message=f"{name}: no macros detected",
                    )
                )
            else:
                results.append(
                    _skipped2(
                        "format.xlsx.macros",
                        f"{name}: macro scan not applicable (not .xlsm)",
                    )
                )
        if messy_sheets:
            results.append(
                CheckResult(
                    check_id="format.xlsx.tabular",
                    level="warning",
                    passed=False,
                    message=f"{name}: sheet(s) may be non-tabular: {', '.join(messy_sheets)}",
                    details={"messy_sheets": messy_sheets},
                )
            )
        else:
            results.append(
                CheckResult(
                    check_id="format.xlsx.tabular",
                    level="info",
                    passed=True,
                    message=f"{name}: all sheets look tabular",
                    details={"sheets_checked": len(sheet_names)},
                )
            )
        return results