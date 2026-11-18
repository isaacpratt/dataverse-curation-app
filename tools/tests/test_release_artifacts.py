"""Release artefacts: SPDX SBOM, NOTICE and the license inventory.

Covers the pure parts of tools/audit/make_sbom.py and tools/audit/make_notice.py - the
files a release attaches to a GitHub Release.
"""

from __future__ import annotations

import json

from tools.audit.make_notice import ATTRIBUTIONS, render_notice
from tools.audit.make_sbom import normalize_license, spdx_document

PACKAGES = [
    {
        "Name": "numpy",
        "Version": "2.1.0",
        "License": "MIT",
        "URL": "https://numpy.org",
    },
    {
        "Name": "PySide6",
        "Version": "6.12.0",
        "License": "LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only",
        "URL": "https://pyside.org",
    },
    {
        "Name": "legacy-thing",
        "Version": "0.1.0",
        "License": "BSD License",
        "URL": "",
    },
]


def test_normalize_license_maps_common_spellings() -> None:
    assert normalize_license("MIT") == "MIT"
    assert normalize_license("MIT License") == "MIT"
    assert normalize_license("Mozilla Public License 2.0 (MPL 2.0)") == "MPL-2.0"
    assert normalize_license("") == "NOASSERTION"
    assert normalize_license("Some Proprietary Terms") == "NOASSERTION"


def test_normalize_license_does_not_guess_the_bsd_clause_count() -> None:
    # "BSD License" does not say which clause count, so it stays unasserted.
    assert normalize_license("BSD License") == "NOASSERTION"


def test_spdx_document_shape() -> None:
    doc = spdx_document(PACKAGES, "0.2.0")
    assert doc["spdxVersion"] == "SPDX-2.3"
    assert doc["dataLicense"] == "CC0-1.0"
    assert doc["SPDXID"] == "SPDXRef-DOCUMENT"
    assert doc["name"] == "dataverse-curation-app-0.2.0"
    assert doc["documentNamespace"].startswith("https://spdx.org/spdxdocs/")
    assert len(doc["packages"]) == 3
    ids = {p["SPDXID"] for p in doc["packages"]}
    assert len(ids) == 3
    for pkg in doc["packages"]:
        assert pkg["filesAnalyzed"] is False
        assert pkg["externalRefs"][0]["referenceLocator"].startswith("pkg:pypi/")
        assert pkg["externalRefs"][0]["referenceCategory"] == "PACKAGE-MANAGER"
    described = {r["relatedSpdxElement"] for r in doc["relationships"]}
    assert described == ids
    assert all(r["relationshipType"] == "DESCRIBES" for r in doc["relationships"])


def test_spdx_document_keeps_unknown_license_as_comment() -> None:
    doc = spdx_document(PACKAGES, "0.2.0")
    legacy = next(p for p in doc["packages"] if p["name"] == "legacy-thing")
    assert legacy["licenseDeclared"] == "NOASSERTION"
    assert "BSD License" in legacy["licenseComments"]


def test_spdx_document_skips_incomplete_packages() -> None:
    doc = spdx_document(
        [*PACKAGES, {"Name": "", "Version": "1.0"}, {"Name": "no-version", "Version": ""}],
        "0.2.0",
    )
    assert len(doc["packages"]) == 3


def test_spdx_document_is_json_serialisable() -> None:
    doc = spdx_document(PACKAGES, "0.2.0")
    assert json.loads(json.dumps(doc))["spdxVersion"] == "SPDX-2.3"


def test_notice_lists_attributions_and_dependencies() -> None:
    text = render_notice(PACKAGES, "0.2.0")
    assert "Dataverse Docent - NOTICE" in text
    assert "CUR_Res_CurationTools" in text
    assert "PySide6" in text
    assert "numpy" in text
    assert "licenses.md" in text
    assert "sbom.spdx.json" in text
    for name, terms, _note in ATTRIBUTIONS:
        assert name in text
        assert terms in text


def test_notice_reports_the_package_count() -> None:
    text = render_notice(PACKAGES, "0.2.0")
    assert "3 Python packages are redistributed" in text
