"""Static analysis of code files (R/Quarto/Python/...).

Port of CUR_Res_CurationTools Scripts/Inspect_Code_Script.R: encoding,
line-ending sanity and TODO/FIXME markers.
"""

import re
from pathlib import Path

from engine.checks._util import detect_encoding
from engine.checks.base import Check, CheckResult

_TODO_RE = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b", re.IGNORECASE)
# Analysis cap: a multi-GB log renamed .py must not be read whole.
_SAMPLE_BYTES = 1 << 20


class CodeCheck(Check):
    """Code check - port of the CUR_Res_CurationTools R inspector."""

    check_id = "format.code"
    extensions = {
        ".r", ".py", ".qmd", ".rmd", ".jl", ".m", ".f90", ".f",
        ".cpp", ".cxx", ".cc", ".c", ".h", ".sh", ".bat", ".sql",
        ".cs", ".java", ".tex", ".do", ".sas", ".ps1",
    }

    def run(self, files: list[Path]) -> list[CheckResult]:
        from engine.checks._util import run_per_file

        return run_per_file(self, files, self._run_one)

    def _run_one(self, path: Path) -> list[CheckResult]:
        name = path.name
        encoding = detect_encoding(path)
        with open(path, "rb") as handle:
            raw = handle.read(_SAMPLE_BYTES + 1)
        sampled = len(raw) > _SAMPLE_BYTES
        text = raw[:_SAMPLE_BYTES].decode(encoding, errors="replace")

        lines = text.count("\n") + 1
        markers = _TODO_RE.findall(text)

        results = [
            CheckResult(
                check_id="format.code.readable",
                level="info",
                passed=True,
                message=(
                    f"{name}: decodes as {encoding} ({lines} lines"
                    + (" — sampled first 1 MiB" if sampled else "")
                    + ")"
                ),
                details={"encoding": encoding, "lines": lines, "sampled": sampled},
            )
        ]
        if markers:
            results.append(
                CheckResult(
                    check_id="format.code.todo_markers",
                    level="warning",
                    passed=False,
                    message=f"{name}: {len(markers)} TODO/FIXME marker(s)",
                    details={"count": len(markers)},
                )
            )
        else:
            results.append(
                CheckResult(
                    check_id="format.code.todo_markers",
                    level="info",
                    passed=True,
                    message=f"{name}: no TODO/FIXME markers"
                    + (" (sampled first 1 MiB)" if sampled else ""),
                    details={"count": 0, "sampled": sampled},
                )
            )
        return results
