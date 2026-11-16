"""Write dist/licenses.md - the license inventory of the locked environment.

Invoked as `uv run python tools/make_licenses.py` (poe license-report).
Runs pip-licenses inside `uv run --with pip-licenses` over the project
venv (the locked set) and keeps the markdown report in dist/.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"


def main() -> int:
    DIST.mkdir(exist_ok=True)
    rc = subprocess.run(
        [
            "uv",
            "run",
            "--with",
            "pip-licenses",
            "pip-licenses",
            "--format=markdown",
            f"--output-file={DIST / 'licenses.md'}",
        ],
        cwd=ROOT,
        check=False,
    ).returncode
    if rc == 0:
        print(f"licenses written to {DIST / 'licenses.md'}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
