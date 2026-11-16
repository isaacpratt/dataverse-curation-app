"""Generate dist/sbom.cdx.json (CycloneDX) for the locked project environment.

Invoked as `uv run python tools/make_sbom.py` (poe sbom). sys.executable is
the project venv, so the SBOM describes exactly what `uv sync` installed -
the same set that ships in the lite/full artefacts.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"


def main() -> int:
    """Write dist/sbom.cdx.json from the project venv; exit 0 on success."""
    DIST.mkdir(exist_ok=True)
    rc = subprocess.run(
        [
            "uvx",
            "--from",
            "cyclonedx-bom",
            "cyclonedx-py",
            "environment",
            sys.executable,
            "--pyproject",
            str(ROOT / "pyproject.toml"),
            "--mc-type",
            "application",
            "--of",
            "json",
            "-o",
            str(DIST / "sbom.cdx.json"),
        ],
        cwd=ROOT,
        check=False,
    ).returncode
    if rc == 0:
        print(f"sbom written to {DIST / 'sbom.cdx.json'}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
