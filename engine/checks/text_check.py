"""Text/markdown file inspection.

Port of CUR_Res_CurationTools Scripts/Inspect_Text_Script.R: encoding
detection, mixed line endings and non-printable control characters.
"""

from pathlib import Path
from typing import List

from engine.checks._util import detect_encoding
from engine.checks.base import Check, CheckResult

_SAMPLE_BYTES = 1 << 20

# Whitelisted control bytes: tab, LF, CR. Everything else below 0x20
# (including VT/FF) plus DEL counts as non-printable.
_ALLOWED_CONTROLS = frozenset({9, 10, 13})


class TextCheck(Check):
    """Text check - port of the CUR_Res_CurationTools R inspector."""

    check_id = "format.text"
    extensions = {".txt", ".md", ".rst", ".log"}

    def run(self, files: List[Path]) -> List[CheckResult]:
        from engine.checks._util import run_per_file

        return run_per_file(self, files, self._run_one)

    def _run_one(self, path: Path) -> List[CheckResult]:
        name = path.name
        if path.stat().st_size == 0:
            return [
                CheckResult(
                    check_id="format.text.readable",
                    level="error",
                    passed=False,
                    message=f"{name}: file is empty",
                )
            ]

        encoding = detect_encoding(path)
        with open(path, "rb") as handle:
            raw = handle.read(_SAMPLE_BYTES)

        crlf = raw.count(b"\r\n")
        lone_lf = raw.count(b"\n") - crlf
        lone_cr = raw.count(b"\r") - crlf
        mixed = (crlf > 0) + (lone_lf > 0) + (lone_cr > 0) > 1

        control_chars = sum(
            1 for byte in raw
            if (byte < 32 and byte not in _ALLOWED_CONTROLS) or byte == 127
        )

        results = [
            CheckResult(
                check_id="format.text.readable",
                level="info",
                passed=True,
                message=f"{name}: decodes as {encoding}",
                details={"encoding": encoding},
            )
        ]
        if mixed:
            results.append(
                CheckResult(
                    check_id="format.text.line_endings",
                    level="warning",
                    passed=False,
                    message=(
                        f"{name}: mixed line endings "
                        f"(CRLF={crlf}, LF={lone_lf}, CR={lone_cr})"
                    ),
                )
            )
        if control_chars:
            results.append(
                CheckResult(
                    check_id="format.text.control_chars",
                    level="warning",
                    passed=False,
                    message=f"{name}: {control_chars} non-printable control byte(s)",
                )
            )
        return results