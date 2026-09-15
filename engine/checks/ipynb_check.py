"""Jupyter notebook (.ipynb) archival inspection.

Port of CUR_Res_CurationTools Scripts/Inspect_ipynb_Script.R: valid notebook
schema, cell counts, output presence and unexecuted-code detection.
"""

import json
from pathlib import Path
from typing import List

from engine.checks.base import Check, CheckResult

# Same full-materialization cap as the JSON check (notebooks are JSON).
_MAX_FULL_PARSE_BYTES = 64 << 20


class IpynbCheck(Check):
    """Jupyter notebook check - port of the CUR_Res_CurationTools R inspector."""

    check_id = "format.ipynb"
    extensions = {".ipynb"}

    def run(self, files: List[Path]) -> List[CheckResult]:
        from engine.checks._util import run_per_file

        return run_per_file(self, files, self._run_one)

    def _run_one(self, path: Path) -> List[CheckResult]:
        name = path.name
        try:
            size = path.stat().st_size
        except OSError as exc:
            return [
                CheckResult(
                    check_id="format.ipynb.valid",
                    level="error",
                    passed=False,
                    message=f"{name}: unreadable ({exc})",
                )
            ]
        if size > _MAX_FULL_PARSE_BYTES:
            return [
                CheckResult(
                    check_id="format.ipynb.valid",
                    level="warning",
                    passed=False,
                    message=(
                        f"{name}: too large ({size} bytes) to fully parse — "
                        "manual verification required"
                    ),
                    details={"size_bytes": size},
                )
            ]
        try:
            notebook = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return [
                CheckResult(
                    check_id="format.ipynb.valid",
                    level="error",
                    passed=False,
                    message=f"{name}: invalid notebook JSON ({exc})",
                )
            ]

        cells = notebook.get("cells")
        nbformat = notebook.get("nbformat")
        if not isinstance(cells, list) or not nbformat:
            return [
                CheckResult(
                    check_id="format.ipynb.valid",
                    level="error",
                    passed=False,
                    message=f"{name}: missing cells/nbformat - not a notebook",
                )
            ]

        code_cells = [c for c in cells if c.get("cell_type") == "code"]
        markdown_cells = len(cells) - len(code_cells)
        with_outputs = sum(1 for c in code_cells if c.get("outputs"))

        results = [
            CheckResult(
                check_id="format.ipynb.valid",
                level="info",
                passed=True,
                message=f"{name}: valid notebook (nbformat {nbformat})",
            ),
            CheckResult(
                check_id="format.ipynb.cells",
                level="info",
                passed=True,
                message=(
                    f"{name}: {len(cells)} cells "
                    f"({len(code_cells)} code, {markdown_cells} markdown)"
                ),
                details={
                    "code": len(code_cells),
                    "markdown": markdown_cells,
                    "with_outputs": with_outputs,
                },
            ),
        ]

        unexecuted = [
            c for c in code_cells if c.get("execution_count") is None
        ]
        if unexecuted:
            results.append(
                CheckResult(
                    check_id="format.ipynb.executed",
                    level="warning",
                    passed=False,
                    message=(
                        f"{name}: {len(unexecuted)} code cell(s) never executed"
                    ),
                )
            )
        elif code_cells:
            results.append(
                CheckResult(
                    check_id="format.ipynb.executed",
                    level="info",
                    passed=True,
                    message=f"{name}: all code cells executed",
                )
            )
        return results