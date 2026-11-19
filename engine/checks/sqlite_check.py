"""SQLite database inspection.

Port of CUR_Res_CurationTools Scripts/Inspect_sqlite_Script.R: integrity
check plus a manifest of tables with row counts.
"""

import sqlite3
from pathlib import Path
from typing import ClassVar

from engine.checks.base import Check, CheckResult

_MAX_TABLES_LISTED = 100


class SqliteCheck(Check):
    """SQLite check - port of the CUR_Res_CurationTools R inspector."""

    check_id = "format.sqlite"
    scope: ClassVar[str] = "file"
    extensions: ClassVar[set[str]] = {".sqlite", ".sqlite3", ".db"}

    def run(self, files: list[Path]) -> list[CheckResult]:
        from engine.checks._util import run_per_file

        return run_per_file(self, files, self._run_one)

    def _run_one(self, path: Path) -> list[CheckResult]:
        from engine.checks._util import quoted_ident, sqlite_uri

        name = path.name
        with open(path, "rb") as handle:
            magic = handle.read(16)
        if magic != b"SQLite format 3\x00":
            from engine.checks._util import skipped as _skipped

            return [
                CheckResult(
                    check_id="format.sqlite.valid",
                    level="error",
                    passed=False,
                    message=f"{name}: not an SQLite database (bad magic)",
                ),
                _skipped(
                    "format.sqlite.manifest",
                    f"{name}: table scan skipped (not an SQLite database)",
                ),
            ]

        conn = sqlite3.connect(sqlite_uri(path), uri=True)
        try:
            # integrity_check returns one row per problem ('ok' alone when
            # clean) — read ALL rows, not just the first.
            problems = [row[0] for row in conn.execute("PRAGMA integrity_check").fetchall()]
            ok = problems == ["ok"]
            tables = [
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            ]
            _max_count_scan = 100_000
            counts = {}
            truncated = len(tables) > _MAX_TABLES_LISTED
            for table in tables[:_MAX_TABLES_LISTED]:
                try:
                    try:
                        conn.execute("PRAGMA query_only=ON")
                    except sqlite3.Error:
                        pass
                    # Bounded count: full COUNT(*) scans 100M-row tables for
                    # minutes. Cap the scan — report ">N" when truncated.
                    n = conn.execute(
                        f"SELECT COUNT(*) FROM "
                        f"(SELECT 1 FROM {quoted_ident(table)} LIMIT {_max_count_scan + 1})"
                    ).fetchone()[0]
                    counts[table] = n if n <= _max_count_scan else f">{_max_count_scan}"
                except sqlite3.Error:
                    counts[table] = None
        finally:
            conn.close()

        first_problem = next((p for p in problems if p != "ok"), "ok")
        valid = CheckResult(
            check_id="format.sqlite.valid",
            level="info" if ok else "error",
            passed=ok,
            message=(
                f"{name}: integrity ok" if ok else f"{name}: integrity problems ({first_problem})"
            ),
        )
        manifest = CheckResult(
            check_id="format.sqlite.manifest",
            level="info",
            passed=True,
            message=(
                f"{name}: {len(tables)} table(s)"
                + (" (list truncated)" if truncated else "")
                + (
                    "; counts capped at 100k"
                    if any(isinstance(v, str) for v in counts.values())
                    else ""
                )
            ),
            details={"tables": counts, "truncated": truncated},
        )
        return [valid, manifest]
