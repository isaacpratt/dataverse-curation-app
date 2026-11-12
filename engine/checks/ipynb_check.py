"""Jupyter notebook (.ipynb) archival inspection.

Port of CUR_Res_CurationTools Scripts/Inspect_ipynb_Script.R: valid notebook
schema, cell counts, output presence and unexecuted-code detection.
"""

import json
from pathlib import Path

from engine.checks.base import Check, CheckResult

# Same full-materialization cap as the JSON check (notebooks are JSON).
_MAX_FULL_PARSE_BYTES = 64 << 20


class IpynbCheck(Check):
    """Jupyter notebook check - port of the CUR_Res_CurationTools R inspector."""

    check_id = "format.ipynb"
    extensions = {".ipynb"}

    def run(self, files: list[Path]) -> list[CheckResult]:
        from engine.checks._util import run_per_file

        return run_per_file(self, files, self._run_one)

    def _run_one(self, path: Path) -> list[CheckResult]:
        from engine.checks._util import skipped as _skipped

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
                ),
                _skipped(
                    "format.ipynb.cells",
                    f"{name}: cell scan skipped (unreadable file)",
                ),
                _skipped(
                    "format.ipynb.executed",
                    f"{name}: execution scan skipped (unreadable file)",
                ),
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
                ),
                _skipped(
                    "format.ipynb.cells",
                    f"{name}: cell scan skipped (file too large)",
                ),
                _skipped(
                    "format.ipynb.executed",
                    f"{name}: execution scan skipped (file too large)",
                ),
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
                ),
                _skipped(
                    "format.ipynb.cells",
                    f"{name}: cell scan skipped (invalid JSON)",
                ),
                _skipped(
                    "format.ipynb.executed",
                    f"{name}: execution scan skipped (invalid JSON)",
                ),
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
                ),
                _skipped(
                    "format.ipynb.cells",
                    f"{name}: cell scan skipped (not a notebook)",
                ),
                _skipped(
                    "format.ipynb.executed",
                    f"{name}: execution scan skipped (not a notebook)",
                ),
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
                    details={"unexecuted": len(unexecuted), "code_cells": len(code_cells)},
                )
            )
        elif code_cells:
            results.append(
                CheckResult(
                    check_id="format.ipynb.executed",
                    level="info",
                    passed=True,
                    message=f"{name}: all code cells executed",
                    details={"code_cells": len(code_cells)},
                )
            )
        else:
            from engine.checks._util import skipped as _skipped2

            results.append(
                _skipped2(
                    "format.ipynb.executed",
                    f"{name}: execution scan not applicable (no code cells)",
                )
            )
        return results
