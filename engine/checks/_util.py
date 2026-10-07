"""Shared helpers for format checks."""

import re
from pathlib import Path
from typing import Any

from engine.checks.base import Check, CheckResult

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

# Canadian pack — piigex has no CA region; these live beside it, not in a fork.
# Postal: valid FSAs/LTAs exclude D,F,I,O,Q,U and the first position of
# Newfoundland (A) is fine as-is; second char 0 is invalid in new FSAs.
_CA_POSTAL_RE = re.compile(
    r"\b([ABCEGHJ-NPRSTVXY]\d[ABCEGHJ-NPRSTV-Z][ -]?\d[ABCEGHJ-NPRSTV-Z]\d)\b"
)
_CA_SIN_RE = re.compile(r"\b(\d{3}[ -]?\d{3}[ -]?\d{3})\b")

EXECUTABLE_EXTS = {".exe", ".bat", ".sh", ".bin", ".jar", ".msi", ".com"}
JUNK_NAMES = {".ds_store", "thumbs.db", "__macosx"}

# piigex types that are shape-only (no checksum) — always kept when matched.
# Only intl detectors can fire (regions=["intl"] scrubber below); regional
# phone/ID names are omitted on purpose.
_PIIGEX_SHAPE_TYPES = frozenset(
    {
        "intl_email",
        "intl_ipv4",
        "intl_ipv6",
        "intl_mac",
        "intl_bic",
        "intl_phone_e164",
    }
)

# Cached piigex Scrubber: intl detectors only (email, cards, IBAN, IP, …).
# Region-specific national IDs (be_eid, es_nss, us_ssn, …) are off by policy —
# Canadian postal/SIN live in the local pack below. Built once; regexes are
# recompiled per Scrubber(), so never construct per-row.
_PII_SCRUBBER = None


def missing_library(check_id: str, lib: str) -> CheckResult:
    # Contract (docs/html/report-contract.html): "not executed" is warning + passed
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
    """Explicit skip for a sub-check that could not run.

    Covers encrypted input, too-large cap, legacy format, upstream read
    failure, ….

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


def find_emails(text: str) -> list[str]:
    return sorted(set(EMAIL_RE.findall(text)))


def _luhn_ok(value: str) -> bool:
    digits = [int(c) for c in value if c.isdigit()]
    if len(digits) < 12 or len(digits) > 19:
        return False
    checksum = 0
    parity = len(digits) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def _ca_sin_luhn_ok(value: str) -> bool:
    digits = [int(c) for c in value if c.isdigit()]
    if len(digits) != 9:
        return False
    # SIN Luhn: double every second digit from the right (standard Luhn on
    # the 9-digit string; leading 0 is kept so parity matches the printed form).
    checksum = 0
    for i, d in enumerate(digits):
        # index from the right: position 1 = rightmost
        pos = len(digits) - i
        if pos % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def _get_pii_scrubber():
    """Return the cached piigex Scrubber (intl detectors only)."""
    global _PII_SCRUBBER
    if _PII_SCRUBBER is None:
        from piigex import Scrubber

        _PII_SCRUBBER = Scrubber(regions=["intl"])
    return _PII_SCRUBBER


def _find_pii_row(text: str) -> list[dict[str, Any]]:
    """One string cell/line → list of {"type", "value"} dicts (raw values).

    piigex is required (bundled in every build) — import failures propagate
    to run_per_file as a per-file finding rather than degrading coverage.
    """
    out: list[dict[str, Any]] = []
    for match in _get_pii_scrubber().scan(text):
        if match.valid or match.name in _PIIGEX_SHAPE_TYPES:
            out.append({"type": match.name, "value": match.value})

    # Canadian pack (piigex has no CA region).
    for m in _CA_POSTAL_RE.finditer(text):
        out.append({"type": "ca_postal_code", "value": m.group(1)})
    for m in _CA_SIN_RE.finditer(text):
        raw = m.group(1)
        if _ca_sin_luhn_ok(raw):
            out.append({"type": "ca_sin", "value": raw})

    # Dedupe by (type, value) preserving order
    seen = set()
    uniq: list[dict[str, Any]] = []
    for item in out:
        key = (item["type"], item["value"])
        if key not in seen:
            seen.add(key)
            uniq.append(item)
    return uniq


def find_pii(text: str) -> list[dict[str, Any]]:
    """Structured PII matches: piigex intl detectors + Canadian pack.

    Foreign national IDs (be_eid, es_nss, us_ssn, …) are disabled — only
    region="intl" piigex detectors run. Returns [{"type", "value"}, ...]
    with raw values (report contract).
    """
    return _find_pii_row(text)


def pii_result(
    check_id: str,
    name: str,
    findings: list[dict[str, Any]],
    *,
    scope: str = "",
    extra_details: dict[str, Any] | None = None,
    max_samples: int | None = None,
) -> CheckResult:
    """Build the always-emit PII CheckResult with explicit truncation copy."""
    if max_samples is None:
        try:
            from engine.constants import CAPS as _CAPS

            max_samples = _CAPS.pii_max_samples
        except Exception:  # pragma: no cover
            max_samples = 10

    count = len(findings)
    types: dict[str, int] = {}
    for item in findings:
        types[item["type"]] = types.get(item["type"], 0) + 1

    scope_note = f" {scope}" if scope else ""
    details: dict[str, Any] = {
        "count": count,
        "types": types,
    }
    if count:
        samples = findings[:max_samples]
        details["samples"] = samples
        details["samples_listed"] = len(samples)
        trunc = (
            f" — showing first {len(samples)} of {count} sample(s)"
            if len(samples) < count
            else ""
        )
        message = f"{name}: {count} possible PII value(s){trunc}{scope_note}"
        level, passed = "warning", False
    else:
        message = f"{name}: no PII values detected{scope_note}"
        level, passed = "info", True
        details["samples"] = []
        details["samples_listed"] = 0

    if extra_details:
        details.update(extra_details)
    return CheckResult(
        check_id=check_id,
        level=level,
        passed=passed,
        message=message,
        details=details,
    )


def sqlite_uri(path: Path) -> str:
    """Build a read-only `file:` URI for a path.

    Quotes `?`/`#` so hostile or odd filenames cannot inject URI
    query/fragment parts.
    """
    from urllib.parse import quote

    return f"file:{quote(path.as_posix(), safe='/:')}?mode=ro"


def quoted_ident(name: str) -> str:
    """Double-quote a SQLite identifier, escaping embedded quotes."""
    return '"' + str(name).replace('"', '""') + '"'


def run_per_file(
    check: Check, files: list[Path], handler
) -> list[CheckResult]:
    """Apply `handler(path) -> List[CheckResult]` to each file.

    Unexpected exceptions become an error-level result instead of failing
    the whole check run.
    """
    results: list[CheckResult] = []
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
