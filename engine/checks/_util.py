"""Shared helpers for format checks."""

import re
from pathlib import Path
from typing import List

from engine.checks.base import Check, CheckResult

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

EXECUTABLE_EXTS = {".exe", ".bat", ".sh", ".bin", ".jar", ".msi", ".com"}
JUNK_NAMES = {".ds_store", "thumbs.db", "__macosx"}


def missing_library(check_id: str, lib: str) -> CheckResult:
    # Contract (docs/report-contract.md): "not executed" is warning + passed.
    # "Missing: …" prefix matches the pre-run probe wording so the UI renders
    # the same amber MISSING/WARN style before and after the run.
    return CheckResult(
        check_id=check_id,
        level="warning",
        passed=True,
        message=f"Missing: pip install {lib} — check not executed",
    )


def detect_encoding(path: Path, sample_bytes: int = 65536) -> str:
    try:
        import chardet
    except ImportError:
        return "utf-8"

    with open(path, "rb") as handle:
        sample = handle.read(sample_bytes)
    guess = chardet.detect(sample)
    return guess.get("encoding") or "utf-8"


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