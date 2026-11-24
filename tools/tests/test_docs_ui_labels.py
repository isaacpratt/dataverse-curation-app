"""Documentation ↔ interface-text consistency checks.

The structural docs tests prove that pages link to each other; they cannot
prove that a button described in a how-to actually exists. These tests pin the
labels and messages the published pages quote against the app's string
catalogue, so a UI rename or a docs typo fails the normal pytest run instead
of sending a curator looking for a control that is not there.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from curation.config import PRESETS

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
CATALOGUE = ROOT / "ui" / "assets" / "strings.json"

# Every label below is quoted verbatim in a published page. The key is the
# catalogue entry the UI actually renders; a drift in either direction fails.
DOCUMENTED_LABELS: dict[str, str] = {
    "Dataverse preset": "settings.fields.preset",
    "Revert": "common.revert",
    "Configure Rules": "main.nav.rules",
    "Review configuration": "review.title",
    "Approve & Publish": "detail.decision.option_approve",
    "Contact Author (Revisions Required)": "detail.decision.option_revisions",
    "Download Dataset": "detail.header.download_all",
    "Verify Files": "detail.header.verify_files",
    "Reload Metadata": "detail.header.reload_metadata",
    "Automated checks": "detail.sections.auto_checks",
    "Test connection": "settings.fields.test_connection",
    "Dataset checks": "detail.sections.dataset_checks",
    "File checks": "detail.sections.file_manifest",
    "Response": "detail.header.response_tab",
    "Export record": "detail.header.export_record",
    "Sensitivity & ethics review": "detail.sensitivity.title",
    "The Dataverse URL or collection looks wrong (404). "
    "Check the Base URL and collection alias in Settings (Ctrl+,).": "dialogs.network.not_found",
}

# Labels and claims retired during the 2026-11-23 accuracy pass. If one of
# these comes back, a page has regressed to describing an interface or an API
# that does not exist.
RETIRED_CLAIMS = (
    "Download All",
    "Auto-Checks card",
    "Requirements and Log",
    "Collection not found",
    "/api/files/:id/ingestStatus",
    "curation-record/<pid>-",
    "a left bar",
    "parity tests run in CI",
)


def _catalogue() -> dict[str, Any]:
    result: dict[str, Any] = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    return result


def _value(data: dict[str, Any], key: str) -> str:
    node: Any = data
    for part in key.split("."):
        assert isinstance(node, dict), f"{key}: not an object at {part}"
        assert part in node, f"{key}: missing catalogue entry"
        node = node[part]
    assert isinstance(node, str), f"{key}: expected a string"
    return node


def _published_pages() -> list[Path]:
    pages = []
    for path in DOCS.rglob("*.md"):
        rel = path.relative_to(DOCS).as_posix()
        if rel.startswith(("adr/", "reports/", "proposals/")):
            continue
        pages.append(path)
    return pages


def _published_text() -> Iterator[tuple[str, str]]:
    for page in _published_pages():
        yield page.relative_to(DOCS).as_posix(), page.read_text(encoding="utf-8")


@pytest.mark.parametrize(("label", "key"), sorted(DOCUMENTED_LABELS.items()))
def test_documented_label_matches_catalogue(label: str, key: str) -> None:
    """A label quoted by the docs is the exact text the UI renders."""
    assert _value(_catalogue(), key) == label, (
        f"docs quote {label!r}; UI says {_value(_catalogue(), key)!r}"
    )


def test_documented_preset_is_a_real_preset() -> None:
    """The tutorial's preset label is one the Settings combo can actually offer."""
    assert "Borealis Demo — demo.borealisdata.ca" in PRESETS
    assert PRESETS["Borealis Demo — demo.borealisdata.ca"] == "https://demo.borealisdata.ca"


@pytest.mark.parametrize("claim", RETIRED_CLAIMS)
def test_retired_claims_are_absent_from_published_pages(claim: str) -> None:
    """Regression guard for the specific inaccuracies fixed in dv-3us."""
    offenders = [name for name, text in _published_text() if claim.lower() in text.lower()]
    assert not offenders, f"retired claim {claim!r} found in: {offenders}"


def test_documented_labels_are_quoted_by_a_page() -> None:
    """Keep the mapping honest: every key in it must support a real doc claim."""
    pages = list(_published_text())
    unused = [
        label for label in DOCUMENTED_LABELS if not any(label in text for _name, text in pages)
    ]
    assert not unused, f"catalogue labels with no documented use: {unused}"
