"""Dataset-level file inventory: extension distribution and risk flags.

Port of CUR_Res_CurationTools Scripts/Inspect_Extensions_Script.R (triage
phase): extension census plus zero-byte, executable and system-junk flags.
This is a dataset-level check - it runs on the whole file set.
"""

from collections import Counter
from pathlib import Path

from engine.checks._util import EXECUTABLE_EXTS, JUNK_NAMES
from engine.checks.base import Check, CheckResult

_MAX_EXTENSIONS_LISTED = 30


class ExtensionsCheck(Check):
    """Inventory check - port of the CUR_Res_CurationTools R inspector."""

    check_id = "inventory.extensions"
    extensions = set()

    def run(self, files: list[Path]) -> list[CheckResult]:
        if not files:
            return [
                CheckResult(
                    check_id="inventory.extensions",
                    level="warning",
                    passed=False,
                    message="no files staged for this dataset",
                )
            ]

        extensions = Counter(
            path.suffix.lower() or "(no extension)" for path in files
        )
        distribution = ", ".join(
            f"{ext}: {count}"
            for ext, count in extensions.most_common(_MAX_EXTENSIONS_LISTED)
        )

        def _size_or_none(p: Path) -> int | None:
            try:
                return p.stat().st_size if p.is_file() else None
            except OSError:
                return None

        zero_byte = [p.name for p in files if _size_or_none(p) == 0]
        executables = [
            p.name
            for p in files
            if p.suffix.lower() in EXECUTABLE_EXTS
        ]
        # A file is junk when its own name matches, or when ANY path
        # component is __MACOSX (nested AppleDouble dirs, not just the
        # immediate parent) — and .parts is safe on single-component paths.
        junk = [
            p.name
            for p in files
            if p.name.lower() in JUNK_NAMES
            or any(part.lower() == "__macosx" for part in p.parts)
        ]

        results = [
            CheckResult(
                check_id="inventory.extensions",
                level="info",
                passed=True,
                message=f"{len(files)} files; {distribution}",
                details={"counts": dict(extensions), "files_checked": len(files)},
            )
        ]

        if zero_byte:
            results.append(
                CheckResult(
                    check_id="inventory.zero_byte",
                    level="error",
                    passed=False,
                    message=f"{len(zero_byte)} zero-byte file(s): "
                    + ", ".join(zero_byte[:10]),
                    details={"count": len(zero_byte), "files": zero_byte[:10]},
                )
            )
        else:
            results.append(
                CheckResult(
                    check_id="inventory.zero_byte",
                    level="info",
                    passed=True,
                    message=f"No zero-byte files ({len(files)} files checked)",
                    details={"count": 0, "files_checked": len(files)},
                )
            )
        if executables:
            results.append(
                CheckResult(
                    check_id="inventory.executables",
                    level="warning",
                    passed=False,
                    message="executable file(s): " + ", ".join(executables[:10]),
                    details={"count": len(executables), "files": executables[:10]},
                )
            )
        else:
            results.append(
                CheckResult(
                    check_id="inventory.executables",
                    level="info",
                    passed=True,
                    message="No executables (.exe/.bat/.sh/.bin/.jar/.msi/.com)",
                    details={"count": 0, "files_checked": len(files)},
                )
            )
        if junk:
            results.append(
                CheckResult(
                    check_id="inventory.system_junk",
                    level="warning",
                    passed=False,
                    message="system junk file(s): " + ", ".join(junk[:10]),
                    details={"count": len(junk), "files": junk[:10]},
                )
            )
        else:
            results.append(
                CheckResult(
                    check_id="inventory.system_junk",
                    level="info",
                    passed=True,
                    message="No system junk (.DS_Store/Thumbs.db/__MACOSX)",
                    details={"count": 0, "files_checked": len(files)},
                )
            )
        return results
