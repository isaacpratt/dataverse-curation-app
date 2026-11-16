"""Generate the release SBOMs for the locked project environment.

Two formats, both describing exactly what `uv sync` installed (the same set
that ships in the lite/full artefacts):

- ``dist/sbom.cdx.json`` — CycloneDX, produced by ``cyclonedx-bom``
  (``cyclonedx-py environment``).
- ``dist/sbom.spdx.json`` — SPDX 2.3, written here from the same package
  inventory ``pip-licenses`` reports. Written in-repo rather than by an
  external binary so the release build needs nothing beyond the Python
  toolchain and stays reproducible offline.

Invoked as ``uv run python tools/make_sbom.py`` (poe sbom).
"""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"

# pip-licenses reports the raw license string from the package metadata.
# These are the spellings that are not SPDX identifiers; everything else is
# passed through as an SPDX expression.
_LICENSE_ALIASES = {
    "mit license": "MIT",
    "apache software license": "Apache-2.0",
    "apache software license; gnu general public license v2 (gplv2)": "Apache-2.0 OR GPL-2.0-only",
    "apache-2.0": "Apache-2.0",
    "mozilla public license 2.0 (mpl 2.0)": "MPL-2.0",
    "gnu general public license v2 (gplv2)": "GPL-2.0-only",
    "gnu lesser general public license v2 or later (lgplv2+)": "LGPL-2.0-or-later",
    "psf-2.0": "PSF-2.0",
}
# "BSD License" is deliberately absent: the metadata does not say which
# clause count, so guessing would misstate a license. It stays NOASSERTION
# with the raw string in licenseComments.


def normalize_license(raw: str) -> str:
    """Map a package's license string onto an SPDX expression.

    Returns ``NOASSERTION`` when the string is empty or is not a usable
    SPDX expression; the raw value is kept separately by the caller.
    """
    text = (raw or "").strip()
    if not text:
        return "NOASSERTION"
    aliased = _LICENSE_ALIASES.get(text.lower())
    if aliased:
        return aliased
    if " " in text and " OR " not in text and " AND " not in text:
        # A prose license name we do not have an identifier for.
        return "NOASSERTION"
    return text


def _spdx_id(name: str, version: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "-." else "-" for ch in f"{name}-{version}")
    return f"SPDXRef-Package-{safe}"


def spdx_document(packages: list[dict[str, Any]], version: str) -> dict[str, Any]:
    """Build an SPDX 2.3 document for a package inventory.

    ``packages`` is the pip-licenses JSON shape: Name, Version, License, URL.
    """
    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    doc_name = f"dataverse-curation-app-{version}"
    spdx_packages: list[dict[str, Any]] = []
    relationships: list[dict[str, str]] = []
    for pkg in packages:
        name = str(pkg.get("Name") or "").strip()
        pkg_version = str(pkg.get("Version") or "").strip()
        if not name or not pkg_version:
            continue
        raw_license = str(pkg.get("License") or "").strip()
        declared = normalize_license(raw_license)
        entry: dict[str, Any] = {
            "SPDXID": _spdx_id(name, pkg_version),
            "name": name,
            "versionInfo": pkg_version,
            "downloadLocation": str(pkg.get("URL") or "NOASSERTION"),
            "filesAnalyzed": False,
            "licenseConcluded": declared,
            "licenseDeclared": declared,
            "copyrightText": "NOASSERTION",
            "externalRefs": [
                {
                    "referenceCategory": "PACKAGE-MANAGER",
                    "referenceType": "purl",
                    "referenceLocator": f"pkg:pypi/{name}@{pkg_version}",
                }
            ],
        }
        if declared == "NOASSERTION" and raw_license:
            entry["licenseComments"] = f"Reported as: {raw_license}"
        spdx_packages.append(entry)
        relationships.append(
            {
                "spdxElementId": "SPDXRef-DOCUMENT",
                "relationshipType": "DESCRIBES",
                "relatedSpdxElement": entry["SPDXID"],
            }
        )
    return {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": doc_name,
        "documentNamespace": f"https://spdx.org/spdxdocs/{doc_name}-{uuid.uuid4()}",
        "creationInfo": {
            "created": now,
            "creators": ["Tool: make_sbom.py - Dataverse Docent"],
        },
        "packages": spdx_packages,
        "relationships": relationships,
    }


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
    try:
        data = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _project_version() -> str:
    pyproject = ROOT / "pyproject.toml"
    for line in pyproject.read_text(encoding="utf-8").splitlines():
        if line.startswith("version = "):
            return line.split("=", 1)[1].strip().strip('"')
    return "0.0.0"


def write_spdx(path: Path) -> bool:
    """Write an SPDX 2.3 SBOM; returns True when the file was produced."""
    packages = _pip_licenses_json()
    if not packages:
        return False
    document = spdx_document(packages, _project_version())
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(f"spdx sbom written to {path} ({len(document['packages'])} packages)")
    return True


def write_cyclonedx(path: Path) -> bool:
    """Write a CycloneDX SBOM via cyclonedx-bom; returns True on success."""
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
            str(path),
        ],
        cwd=ROOT,
        check=False,
    ).returncode
    if rc == 0:
        print(f"cyclonedx sbom written to {path}")
    return rc == 0


def main() -> int:
    """Write dist/sbom.cdx.json and dist/sbom.spdx.json; exit 0 on success."""
    DIST.mkdir(exist_ok=True)
    ok = write_cyclonedx(DIST / "sbom.cdx.json")
    if not write_spdx(DIST / "sbom.spdx.json"):
        ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
