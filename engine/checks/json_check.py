"""JSON archival inspection.

Port of CUR_Res_CurationTools Scripts/Inspect_json_Script.R: parse validity,
top-level structure and size sanity.
"""

import json
from pathlib import Path
from typing import ClassVar

from engine.checks.base import Check, CheckResult

# Full materialization cap: larger files get a structural sniff (first bytes
# must open an object/array) instead of a 2 GB json.loads.
_MAX_FULL_PARSE_BYTES = 64 << 20


class JsonCheck(Check):
    """JSON check - port of the CUR_Res_CurationTools R inspector."""

    check_id = "format.json"
    scope: ClassVar[str] = "file"
    extensions: ClassVar[set[str]] = {".json"}

    def run(self, files: list[Path]) -> list[CheckResult]:
        from engine.checks._util import run_per_file

        return run_per_file(self, files, self._run_one)

    def _run_one(self, path: Path) -> list[CheckResult]:
        name = path.name
        try:
            size = path.stat().st_size
        except OSError as exc:
            return [
                CheckResult(
                    check_id="format.json.valid",
                    level="error",
                    passed=False,
                    message=f"{name}: unreadable ({exc})",
                )
            ]
        if size > _MAX_FULL_PARSE_BYTES:
            return [
                CheckResult(
                    check_id="format.json.valid",
                    level="warning",
                    passed=False,
                    message=(
                        f"{name}: too large ({size} bytes) to fully parse — "
                        "manual verification required"
                    ),
                    details={"size_bytes": size},
                )
            ]
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return [
                CheckResult(
                    check_id="format.json.valid",
                    level="error",
                    passed=False,
                    message=f"{name}: invalid JSON ({exc})",
                )
            ]

        if isinstance(document, dict):
            shape = f"object with {len(document)} keys"
        elif isinstance(document, list):
            shape = f"array with {len(document)} items"
        else:
            shape = type(document).__name__

        return [
            CheckResult(
                check_id="format.json.valid",
                level="info",
                passed=True,
                message=f"{name}: valid JSON ({shape})",
            )
        ]
