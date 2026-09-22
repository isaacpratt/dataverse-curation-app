"""Text/markdown file inspection.

Port of CUR_Res_CurationTools Scripts/Inspect_Text_Script.R: encoding
detection, mixed line endings and non-printable control characters.
"""

from pathlib import Path

from engine.checks._util import detect_encoding, find_pii, pii_result
from engine.checks.base import Check, CheckResult

_SAMPLE_BYTES = 1 << 20

# Whitelisted control bytes: tab, LF, CR. Everything else below 0x20
# (including VT/FF) plus DEL counts as non-printable.
_ALLOWED_CONTROLS = frozenset({9, 10, 13})


class TextCheck(Check):
    """Text check - port of the CUR_Res_CurationTools R inspector."""

    check_id = "format.text"
    extensions = {".txt", ".md", ".rst", ".log"}

    def run(self, files: list[Path]) -> list[CheckResult]:
        from engine.checks._util import run_per_file

        return run_per_file(self, files, self._run_one)

    def _run_one(self, path: Path) -> list[CheckResult]:
        from engine.checks._util import skipped as _skipped

        name = path.name
        if path.stat().st_size == 0:
            return [
                CheckResult(
                    check_id="format.text.readable",
                    level="error",
                    passed=False,
                    message=f"{name}: file is empty",
                ),
                _skipped(
                    "format.text.line_endings",
                    f"{name}: line-ending scan skipped (empty file)",
                ),
                _skipped(
                    "format.text.control_chars",
                    f"{name}: control-char scan skipped (empty file)",
                ),
                _skipped(
                    "format.text.pii",
                    f"{name}: PII scan skipped (empty file)",
                ),
            ]

        encoding = detect_encoding(path)
        with open(path, "rb") as handle:
            raw = handle.read(_SAMPLE_BYTES)
        sampled = path.stat().st_size > _SAMPLE_BYTES
        text = raw.decode(encoding, errors="replace")

        crlf = raw.count(b"\r\n")
        lone_lf = raw.count(b"\n") - crlf
        lone_cr = raw.count(b"\r") - crlf
        mixed = (crlf > 0) + (lone_lf > 0) + (lone_cr > 0) > 1

        control_chars = sum(
            1 for byte in raw
            if (byte < 32 and byte not in _ALLOWED_CONTROLS) or byte == 127
        )

        pii_findings = find_pii(text)

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
                    details={"CRLF": crlf, "LF": lone_lf, "CR": lone_cr},
                )
            )
        else:
            dominant = "CRLF" if crlf else ("CR" if lone_cr and not lone_lf else "LF")
            results.append(
                CheckResult(
                    check_id="format.text.line_endings",
                    level="info",
                    passed=True,
                    message=f"{name}: consistent {dominant} line endings",
                    details={"CRLF": crlf, "LF": lone_lf, "CR": lone_cr},
                )
            )
        if control_chars:
            results.append(
                CheckResult(
                    check_id="format.text.control_chars",
                    level="warning",
                    passed=False,
                    message=f"{name}: {control_chars} non-printable control byte(s)",
                    details={"count": control_chars},
                )
            )
        else:
            results.append(
                CheckResult(
                    check_id="format.text.control_chars",
                    level="info",
                    passed=True,
                    message=f"{name}: no control characters (1 MiB sample)",
                    details={"count": 0},
                )
            )
        results.append(
            pii_result(
                "format.text.pii",
                name,
                pii_findings,
                scope=(
                    "(sampled first 1 MiB)" if sampled else "(full file)"
                ),
                extra_details={"sampled": sampled},
            )
        )
        return results