"""Shared helpers for format checks."""

import re
from pathlib import Path
from typing import List

from engine.checks.base import Check, CheckResult

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

EXECUTABLE_EXTS = {".exe", ".bat", ".sh", ".bin", ".jar", ".msi", ".com"}
JUNK_NAMES = {".ds_store", "thumbs.db", "__macosx"}


def missing_library(check_id: str, lib: str) -> CheckResult:
    # Contract (docs/report-contract.md): "not executed" is warning + passed
    # with details.skipped=True so the UI/Markdown renders an explicit
    # SKIPPED state instead of confusing it with a real pass.
    # "Missing: …" prefix matches the pre-run probe wording so the UI renders
    # the same amber MISSING/WARN style before and after the run.
    # Frozen (PyInstaller) builds cannot `pip install` into the bundle and
    # may be offline — point at the full build instead.
    import sys

    if getattr(sys, "frozen", False):
        message = (
            f"Missing: {lib} not in this lite build — "
            "use dist/curation-app-full/curation-app-full.exe "
            "for full format coverage"
        )
    else:
        message = f"Missing: pip install {lib} — check not executed"
    return CheckResult(
        check_id=check_id,
        level="warning",
        passed=True,
        message=message,
        details={"skipped": True, "required": lib},
    )


def skipped(check_id: str, reason: str) -> CheckResult:
    """Explicit skip for a sub-check that could not run (encrypted input,
    too-large cap, legacy format, upstream read failure, …).

    Wire-compatible with missing_library: warning + passed, with
    details.skipped=True so status.py classifies it as SKIPPED.
    """
    return CheckResult(
        check_id=check_id,
        level="warning",
        passed=True,
        message=reason,
        details={"skipped": True, "reason": reason},
    )


def detect_encoding(path: Path, sample_bytes: int = 65536) -> str:
    try:
        import chardet
    except ImportError:
        return "utf-8"

    try:
        with open(path, "rb") as handle:
            sample = handle.read(sample_bytes)
    except OSError:
        return "utf-8"
    try:
        guess = chardet.detect(sample)
    except Exception:
        return "utf-8"
    if not isinstance(guess, dict):
        return "utf-8"
    return str(guess.get("encoding") or "utf-8")


def find_emails(text: str) -> List[str]:
    return sorted(set(EMAIL_RE.findall(text)))


def sqlite_uri(path: Path) -> str:
    """Read-only `file:` URI for a path (quotes `?`/`#` so hostile or odd
    filenames cannot inject URI query/fragment parts)."""
    from urllib.parse import quote

    return f"file:{quote(path.as_posix(), safe='/:')}?mode=ro"


def quoted_ident(name: str) -> str:
    """Double-quote a SQLite identifier, escaping embedded quotes."""
    return '"' + str(name).replace('"', '""') + '"'


def run_per_file(
    check: Check, files: List[Path], handler
) -> List[CheckResult]:
    """Apply `handler(path) -> List[CheckResult]` to each file, converting
    unexpected exceptions into an error-level result instead of failing the
    whole check run."""
    results: List[CheckResult] = []
    for path in files:
        try:
            results.extend(handler(path))
        except Exception as exc:
            results.append(
                CheckResult(
                    check_id=f"{check.check_id}.openable",
                    level="error",
                    passed=False,
                    message=f"{path.name}: inspection failed ({exc})",
                )
            )
    return results