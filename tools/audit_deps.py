"""Vulnerability scan of the locked dependency set (CI + poe audit).

Exports the exact locked resolution (uv.lock, dev group included) to a
throwaway requirements file and runs pip-audit against OSV. Exits with
pip-audit's status, so CI fails when an advisory exists. Deliberately
local/OSV-based: no telemetry, no PyPI JSON round trip.

Policy: fail on any known advisory. The queue is empty today; when it
grows, switch to a severity gate or an explicit allowlist file rather
than silencing findings.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, check=False, **kw)


def main() -> int:
    export = run(
        ["uv", "export", "--locked", "--all-groups", "--format", "requirements-txt",
         "--no-emit-project", "--no-hashes"],
        cwd=ROOT,
    )
    if export.returncode != 0:
        print(export.stdout)
        print(export.stderr, file=sys.stderr)
        print("audit: uv export failed", file=sys.stderr)
        return 2

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", prefix="requirements-audit-", delete=False, encoding="utf-8"
    ) as fh:
        fh.write(export.stdout)
        req = Path(fh.name)

    audit = run(
        ["uvx", "--from", "pip-audit", "pip-audit", "-s", "osv",
         "--progress-spinner", "off", "-r", str(req)],
        cwd=ROOT,
    )
    print(audit.stdout.rstrip())
    if audit.stderr:
        print(audit.stderr, file=sys.stderr)
    try:
        req.unlink()
    except OSError:
        pass
    return audit.returncode


if __name__ == "__main__":
    sys.exit(main())
