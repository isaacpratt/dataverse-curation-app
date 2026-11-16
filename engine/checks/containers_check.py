"""Compressed archive inspection.

Port of CUR_Res_CurationTools Scripts/Inspect_Containers_Script.R, which
targets compressed archives (.zip, .tar, .7z, ...): validity, integrity and
a content listing. Formats without a native Python reader are reported as
'manual verification required'.
"""

import tarfile
import zipfile
from pathlib import Path
from typing import ClassVar

from engine.checks.base import Check, CheckResult

_NATIVE = {".zip", ".tar", ".tgz", ".tbz2"}
_MAX_ENTRIES_LISTED = 50
# Enumeration/decompression caps: beyond these the archive is reported as
# too large to fully inspect instead of stalling or OOMing the run.
_MAX_MEMBERS = 10000
_MAX_UNCOMPRESSED_BYTES = 2 << 30


def _unsafe_entry(name: str) -> bool:
    r"""Zip-slip style traversal: absolute path or `..` segment.

    Covers POSIX + Windows forms: drive-absolute (C:\\…), backslash
    separators, and leading ~/.
    """
    if not name:
        return True
    # Normalize backslashes so Windows traversal is caught on any OS.
    normalized = name.replace("\\", "/")
    # Drive-absolute (C:/…) or UNC (//…).
    if len(normalized) >= 2 and normalized[1] == ":":
        return True
    parts = normalized.split("/")
    if any(p == ".." for p in parts):
        return True
    return Path(name).is_absolute() or Path(normalized).is_absolute()


class ContainersCheck(Check):
    """Archive check - port of the CUR_Res_CurationTools R inspector."""

    check_id = "format.containers"
    extensions: ClassVar[set[str]] = {
        ".zip",
        ".tar",
        ".tgz",
        ".tbz2",
        ".7z",
        ".rar",
        ".gz",
        ".bz2",
        ".xz",
    }

    def run(self, files: list[Path]) -> list[CheckResult]:
        from engine.checks._util import run_per_file

        return run_per_file(self, files, self._run_one)

    def _run_one(self, path: Path) -> list[CheckResult]:
        name = path.name
        suffixes = [s.lower() for s in path.suffixes]
        suffix = suffixes[-1] if suffixes else ""

        if suffix == ".zip":
            return self._inspect_zip(path)
        # tarfile opens "r:*", so .tar.gz / .tar.bz2 inspect as tar.
        if suffix in {".tar", ".tgz", ".tbz2"} or ".tar" in suffixes:
            return self._inspect_tar(path)

        from engine.checks._util import skipped as _skipped

        return [
            CheckResult(
                check_id="format.containers.valid",
                level="warning",
                passed=False,
                message=(f"{name}: no native reader for '{suffix}' - manual verification required"),
            ),
            _skipped(
                "format.containers.unsafe_entry",
                f"{name}: entry scan skipped (no native reader)",
            ),
            _skipped(
                "format.containers.encrypted",
                f"{name}: encryption scan skipped (no native reader)",
            ),
        ]

    def _inspect_zip(self, path: Path) -> list[CheckResult]:
        from engine.checks._util import skipped as _skipped

        name = path.name
        with zipfile.ZipFile(str(path)) as archive:
            infos = archive.infolist()
            if len(infos) > _MAX_MEMBERS:
                return [
                    CheckResult(
                        check_id="format.containers.valid",
                        level="warning",
                        passed=False,
                        message=(
                            f"{name}: too many entries ({len(infos)}) to fully "
                            "inspect — manual verification required"
                        ),
                        details={"members": len(infos)},
                    ),
                    _skipped(
                        "format.containers.unsafe_entry",
                        f"{name}: entry scan skipped (member cap exceeded)",
                    ),
                    _skipped(
                        "format.containers.encrypted",
                        f"{name}: encryption scan skipped (member cap exceeded)",
                    ),
                ]
            total = sum(info.file_size for info in infos)
            if total > _MAX_UNCOMPRESSED_BYTES:
                return [
                    CheckResult(
                        check_id="format.containers.valid",
                        level="warning",
                        passed=False,
                        message=(
                            f"{name}: uncompressed size ({total} bytes) exceeds "
                            "inspection cap — manual verification required"
                        ),
                        details={"uncompressed_bytes": total},
                    ),
                    _skipped(
                        "format.containers.unsafe_entry",
                        f"{name}: entry scan skipped (size cap exceeded)",
                    ),
                    _skipped(
                        "format.containers.encrypted",
                        f"{name}: encryption scan skipped (size cap exceeded)",
                    ),
                ]
            entries = [info.filename for info in infos]
            unsafe = sorted({e for e in entries if _unsafe_entry(e)})
            # CRC verification decompresses every member: only after the caps.
            bad_file = archive.testzip()
            encrypted = any(info.flag_bits & 0x1 for info in infos)

        results = [
            CheckResult(
                check_id="format.containers.valid",
                level="info" if bad_file is None else "error",
                passed=bad_file is None,
                message=(
                    f"{name}: zip OK ({len(entries)} entries)"
                    if bad_file is None
                    else f"{name}: corrupt member '{bad_file}'"
                ),
                details={"entries": entries[:_MAX_ENTRIES_LISTED]},
            )
        ]
        if unsafe:
            results.append(
                CheckResult(
                    check_id="format.containers.unsafe_entry",
                    level="warning",
                    passed=False,
                    message=(
                        f"{name}: {len(unsafe)} entr{'y' if len(unsafe) == 1 else 'ies'} "
                        "escape the archive directory (.., absolute path)"
                    ),
                    details={"entries": unsafe[:_MAX_ENTRIES_LISTED]},
                )
            )
        else:
            results.append(
                CheckResult(
                    check_id="format.containers.unsafe_entry",
                    level="info",
                    passed=True,
                    message=f"{name}: no traversal entries ({len(entries)} entries checked)",
                    details={"members_checked": len(entries)},
                )
            )
        if encrypted:
            results.append(
                CheckResult(
                    check_id="format.containers.encrypted",
                    level="warning",
                    passed=False,
                    message=f"{name}: zip contains encrypted members",
                )
            )
        else:
            results.append(
                CheckResult(
                    check_id="format.containers.encrypted",
                    level="info",
                    passed=True,
                    message=f"{name}: no encrypted members",
                    details={"members_checked": len(entries)},
                )
            )
        return results

    def _inspect_tar(self, path: Path) -> list[CheckResult]:
        from engine.checks._util import skipped as _skipped

        name = path.name
        with tarfile.open(str(path), "r:*") as archive:
            members = archive.getmembers()
        if len(members) > _MAX_MEMBERS:
            return [
                CheckResult(
                    check_id="format.containers.valid",
                    level="warning",
                    passed=False,
                    message=(
                        f"{name}: too many members ({len(members)}) to fully "
                        "inspect — manual verification required"
                    ),
                    details={"members": len(members)},
                ),
                _skipped(
                    "format.containers.unsafe_entry",
                    f"{name}: entry scan skipped (member cap exceeded)",
                ),
                _skipped(
                    "format.containers.encrypted",
                    f"{name}: encryption scan skipped (tar has no encryption flag)",
                ),
            ]
        total = sum(m.size for m in members)
        if total > _MAX_UNCOMPRESSED_BYTES:
            return [
                CheckResult(
                    check_id="format.containers.valid",
                    level="warning",
                    passed=False,
                    message=(
                        f"{name}: uncompressed size ({total} bytes) exceeds "
                        "inspection cap — manual verification required"
                    ),
                    details={"uncompressed_bytes": total},
                ),
                _skipped(
                    "format.containers.unsafe_entry",
                    f"{name}: entry scan skipped (size cap exceeded)",
                ),
                _skipped(
                    "format.containers.encrypted",
                    f"{name}: encryption scan skipped (tar has no encryption flag)",
                ),
            ]
        names = [m.name for m in members]
        unsafe = sorted({n for n in names if _unsafe_entry(n)})
        # Symlink / hardlink members can redirect extraction outside dest
        # even when the name itself looks safe.
        try:
            link_names = sorted({m.name for m in members if m.issym() or m.islnk()})
        except Exception:
            link_names = []
        if link_names:
            unsafe = sorted(set(unsafe) | set(link_names))
        results = [
            CheckResult(
                check_id="format.containers.valid",
                level="info",
                passed=True,
                message=f"{name}: tar readable ({len(members)} members)",
                details={"entries": [m.name for m in members[:_MAX_ENTRIES_LISTED]]},
            )
        ]
        if unsafe:
            results.append(
                CheckResult(
                    check_id="format.containers.unsafe_entry",
                    level="warning",
                    passed=False,
                    message=(
                        f"{name}: {len(unsafe)} entr{'y' if len(unsafe) == 1 else 'ies'} "
                        "escape the archive directory (.., absolute path)"
                    ),
                    details={"entries": unsafe[:_MAX_ENTRIES_LISTED]},
                )
            )
        else:
            results.append(
                CheckResult(
                    check_id="format.containers.unsafe_entry",
                    level="info",
                    passed=True,
                    message=f"{name}: no traversal entries ({len(members)} members checked)",
                    details={"members_checked": len(members)},
                )
            )
        results.append(
            CheckResult(
                check_id="format.containers.encrypted",
                level="info",
                passed=True,
                message=f"{name}: tar has no encryption flag — nothing to check",
                details={"members_checked": len(members)},
            )
        )
        return results
