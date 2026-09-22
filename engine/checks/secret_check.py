"""Secret/credential scan of code, text and config files.

Uses hush-scan (regex rules + Shannon entropy) over a bounded sample so a
multi-GB blob renamed .py/.md is never read whole. Bundled in lite and full
PyInstaller builds — not an optional/excluded dependency.
"""

from pathlib import Path

from hush import Scanner

from engine.checks._util import detect_encoding
from engine.checks.base import Check, CheckResult

try:
    from engine.constants import CAPS as _CAPS

    _SAMPLE_BYTES = _CAPS.secret_sample_bytes
    _MAX_LISTED = _CAPS.secret_max_listed
except Exception:  # pragma: no cover - constants import must never break checks
    _SAMPLE_BYTES = 5 << 20
    _MAX_LISTED = 20


class SecretCheck(Check):
    """Secret/credential scan (API keys, tokens, private keys, high-entropy)."""

    check_id = "format.secrets"
    extensions = {
        # code
        ".r", ".py", ".qmd", ".rmd", ".jl", ".m", ".f90", ".f",
        ".cpp", ".cxx", ".cc", ".c", ".h", ".sh", ".bat", ".sql",
        ".cs", ".java", ".tex", ".do", ".sas", ".ps1", ".pl",
        ".rb", ".go", ".js", ".ts", ".css", ".html",
        # text
        ".txt", ".md", ".rst", ".log",
        # config
        ".yml", ".yaml", ".json", ".toml", ".ini",
        ".cfg", ".conf", ".env", ".properties",
        # xml: also matches xml_check; both may run on the same file
        ".xml",
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

        scanner = Scanner(use_entropy=True, min_severity="medium")
        findings = scanner.scan_text(text, source=name)
        count = len(findings)
        sample_note = (
            f" (sampled first {_SAMPLE_BYTES // (1 << 20)} MiB)" if sampled else ""
        )

        if not findings:
            return [
                CheckResult(
                    check_id="format.secrets",
                    level="info",
                    passed=True,
                    message=f"{name}: no secrets detected{sample_note}",
                    details={
                        "count": 0,
                        "sampled": sampled,
                        "sample_bytes": min(len(raw), _SAMPLE_BYTES),
                    },
                )
            ]

        listed = findings[:_MAX_LISTED]
        shown = len(listed)
        trunc = f" — showing first {shown} of {count}" if shown < count else ""
        return [
            CheckResult(
                check_id="format.secrets",
                level="warning",
                passed=False,
                message=f"{name}: {count} potential secret(s){trunc}{sample_note}",
                details={
                    "count": count,
                    "findings_listed": shown,
                    "sampled": sampled,
                    "findings": [
                        {
                            "rule_id": f.rule_id,
                            "description": f.description,
                            "severity": f.severity,
                            "line": f.line,
                            "secret": f.secret,
                        }
                        for f in listed
                    ],
                },
            )
        ]
