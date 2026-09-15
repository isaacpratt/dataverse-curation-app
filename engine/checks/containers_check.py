"""Compressed archive inspection.

Port of CUR_Res_CurationTools Scripts/Inspect_Containers_Script.R, which
targets compressed archives (.zip, .tar, .7z, ...): validity, integrity and
a content listing. Formats without a native Python reader are reported as
'manual verification required'.
"""

import tarfile
import zipfile
from pathlib import Path
from typing import List

from engine.checks.base import Check, CheckResult

_NATIVE = {".zip", ".tar", ".tgz", ".tbz2"}
_MAX_ENTRIES_LISTED = 50
# Enumeration/decompression caps: beyond these the archive is reported as
# too large to fully inspect instead of stalling or OOMing the run.
_MAX_MEMBERS = 10000
_MAX_UNCOMPRESSED_BYTES = 2 << 30


def _unsafe_entry(name: str) -> bool:
    """Zip-slip style traversal: absolute path or `..` segment."""
    parts = Path(name).parts
    return Path(name).is_absolute() or any(p == ".." for p in parts)


class ContainersCheck(Check):
    """Archive check - port of the CUR_Res_CurationTools R inspector."""

    check_id = "format.containers"
    extensions = {".zip", ".tar", ".tgz", ".tbz2", ".7z", ".rar", ".gz"}

    def run(self, files: List[Path]) -> List[CheckResult]:
        from engine.checks._util import run_per_file

        return run_per_file(self, files, self._run_one)

    def _run_one(self, path: Path) -> List[CheckResult]:
        name = path.name
        suffixes = [s.lower() for s in path.suffixes]
        suffix = suffixes[-1] if suffixes else ""

        if suffix == ".zip":
            return self._inspect_zip(path)
        # tarfile opens "r:*", so .tar.gz / .tar.bz2 inspect as tar.
        if suffix in {".tar", ".tgz", ".tbz2"} or ".tar" in suffixes:
            return self._inspect_tar(path)

        return [
            CheckResult(
                check_id="format.containers.valid",
                level="warning",
                passed=False,
                message=(
                    f"{name}: no native reader for '{suffix}' - "
                    "manual verification required"
                ),
            )
        ]

    def _inspect_zip(self, path: Path) -> List[CheckResult]:
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
                    )
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
                    )
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
        if encrypted:
            results.append(
                CheckResult(
                    check_id="format.containers.encrypted",
                    level="warning",
                    passed=False,
                    message=f"{name}: zip contains encrypted members",
                )
            )
        return results

    def _inspect_tar(self, path: Path) -> List[CheckResult]:
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
                )
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
                )
            ]
        names = [m.name for m in members]
        unsafe = sorted({n for n in names if _unsafe_entry(n)})
        results = [
            CheckResult(
                check_id="format.containers.valid",
                level="info",
                passed=True,
                message=f"{name}: tar readable ({len(members)} members)",
                details={
                    "entries": [m.name for m in members[:_MAX_ENTRIES_LISTED]]
                },
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
        return results