"""The displayed title is part of the metadata check (dv-be4m).

A version can change its title; the check must use the title on screen,
not only the title in the metadata blob that happened to be loaded.
"""

from typing import Any

from curation.metadata_check import check_metadata_completeness, check_with_ruleset


def _metadata(title: str) -> dict[str, Any]:
    return {
        "latestVersion": {
            "metadataBlocks": {"citation": {"fields": [{"typeName": "title", "value": title}]}}
        }
    }


def test_ruleset_check_uses_the_supplied_title():
    meta = _metadata("Old title")
    rows, _ruleset = check_with_ruleset(
        meta,
        "mcmaster-default",
        title="Title from the reviewed version",
    )
    title_row = next(r for r in rows if r.get("name") == "title")
    assert title_row["value"] == "Title from the reviewed version"
    assert title_row["status"] == "complete"


def test_legacy_check_uses_the_supplied_title():
    rows = check_metadata_completeness(
        _metadata("Old title"), profile="Minimal", title="New version title"
    )
    title_row = next(r for r in rows if r.get("field", "").lower() == "title")
    assert title_row["value"] == "New version title"
    assert title_row["status"] == "complete"
