"""Write dist/NOTICE - the attribution file that ships with a release.

The NOTICE carries the attributions a redistributor must reproduce (the app
itself, the MIT-licensed R engine the checks were ported from, the design
patterns the UI borrowed, and Qt/PySide6's LGPL terms) plus the dependency
inventory as a table. The full per-dependency license texts live in
``dist/licenses.md`` next to it.

Invoked as ``uv run python tools/audit/make_notice.py`` (poe notice).
"""

from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / "dist"

# Attributions that cannot be derived from the dependency inventory.
ATTRIBUTIONS = [
    (
        "Dataverse Docent (this application)",
        "MIT License, Copyright (c) 2026 Isaac Pratt and McMaster",
        "The application itself; see LICENSE in the source distribution.",
    ),
    (
        "CUR_Res_CurationTools (the R engine the checks were ported from)",
        "MIT License, Copyright (c) 2026 Curation Services Team, Digital Research Alliance of Canada",
        "The engine checks in engine/checks/ are Python ports of the R inspectors; "
        "the port is distributed under the same MIT terms.",
    ),
    (
        "rdm-review-dashboard (design patterns)",
        "Apache License 2.0",
        "Interaction patterns the UI borrows; no code is copied verbatim.",
    ),
    (
        "Qt for Python / PySide6",
        "LGPL-3.0-only (also offered under GPL-2.0-only / GPL-3.0-only)",
        "Dynamically linked. Qt is used as an unmodified external library; the LGPL "
        "permits use of the shipped binaries provided the user can replace them "
        "(relinking is not required for this desktop application).",
    ),
]


def _pip_licenses_json() -> list[dict[str, Any]]:
    """Return the locked environment as a pip-licenses inventory (empty on failure)."""
    proc = subprocess.run(
        [
            "uv",
            "run",
            "--with",
            "pip-licenses",
            "pip-licenses",
            "--format=json",
            "--with-urls",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        print(f"pip-licenses failed: {proc.stderr.strip()[-500:]}", file=sys.stderr)
        return []
    import json

    try:
        data = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _project_version() -> str:
    for line in (ROOT / "pyproject.toml").read_text(encoding="utf-8").splitlines():
        if line.startswith("version = "):
            return line.split("=", 1)[1].strip().strip('"')
    return "0.0.0"


def render_notice(packages: list[dict[str, Any]], version: str) -> str:
    """Render the NOTICE text for a package inventory."""
    stamp = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    lines = [
        "Dataverse Docent - NOTICE",
        "========================",
        "",
        f"Version: {version}",
        f"Generated: {stamp}",
        "",
        "This product includes software developed by third parties. The list below",
        "covers the attributions that apply to redistributed source and binaries;",
        "the complete per-dependency license inventory (with upstream URLs) is in",
        "licenses.md, shipped alongside this file.",
        "",
        "Attributions",
        "------------",
        "",
    ]
    for name, terms, note in ATTRIBUTIONS:
        lines.append(f"* {name}")
        lines.append(f"  License: {terms}")
        lines.append(f"  {note}")
        lines.append("")
    lines += [
        "Bundled dependencies",
        "--------------------",
        "",
        f"{len(packages)} Python packages are redistributed with this release:",
        "",
        "| Package | Version | License |",
        "|---|---|---|",
    ]
    for pkg in sorted(packages, key=lambda p: str(p.get("Name") or "").lower()):
        name = str(pkg.get("Name") or "").strip()
        pkg_version = str(pkg.get("Version") or "").strip()
        license_name = str(pkg.get("License") or "NOASSERTION").strip() or "NOASSERTION"
        if not name:
            continue
        lines.append(f"| {name} | {pkg_version} | {license_name} |")
    lines += [
        "",
        "SBOMs: sbom.cdx.json (CycloneDX) and sbom.spdx.json (SPDX 2.3) describe the",
        "same locked dependency set.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    """Write dist/NOTICE from the locked environment; exit 0 on success."""
    DIST.mkdir(exist_ok=True)
    packages = _pip_licenses_json()
    if not packages:
        print("notice: no package inventory available", file=sys.stderr)
        return 1
    notice = render_notice(packages, _project_version())
    (DIST / "NOTICE").write_text(notice, encoding="utf-8")
    print(f"notice written to {DIST / 'NOTICE'} ({len(packages)} packages)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
