"""Parsed metadatablocks → rule catalog rows: composite children included.

Live-schema source for engine/tests/fixtures/metadatablocks_citation.json:
Borealis demo, GET https://demo.borealisdata.ca/api/metadatablocks/citation,
fetched 2026-11-12, trimmed to the citation author + dsDescription blocks.
"""

import json
from pathlib import Path
from typing import Any

import pytest

_FIXTURE = Path(__file__).parent / "fixtures" / "metadatablocks_citation.json"


def _load() -> dict[str, Any]:
    raw = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return raw


def test_childfields_surface_as_dotted_rows() -> None:
    from curation.client import parse_metadatablock_fields

    rows = parse_metadatablock_fields(_load())
    by = {r["field"]: r for r in rows}
    # Top-level entries preserved, author shows as "Author".
    assert by["author"]["label"] == "Author"
    assert by["dsDescription"]["label"] == "Description"
    # Children listed exactly as Borealis shows them, nested via parent.
    assert by["author.authorName"]["label"] == "Name"
    assert by["author.authorAffiliation"]["label"] == "Affiliation"
    assert by["author.authorIdentifierScheme"]["label"] == "Identifier Type"
    assert by["author.authorIdentifier"]["label"] == "Identifier"
    for row in (
        "author.authorName",
        "author.authorAffiliation",
        "author.authorIdentifierScheme",
        "author.authorIdentifier",
    ):
        assert by[row]["parent"] == "author"
        assert by[row]["block"] == "citation"
    # dsDescription children follow the same pattern.
    assert "dsDescription.dsDescriptionValue" in by
    assert "dsDescription.dsDescriptionDate" in by


def test_childfields_order_is_borealis_display_order() -> None:
    from curation.client import parse_metadatablock_fields

    rows = parse_metadatablock_fields(_load())
    author_children = [r for r in rows if r.get("parent") == "author"]
    # displayOrder: Name 8, Affiliation 9, Identifier Type 10, Identifier 11.
    assert [r["label"] for r in author_children] == [
        "Name",
        "Affiliation",
        "Identifier Type",
        "Identifier",
    ]


def test_subfield_rows_survive_the_review_config_union(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rule-config union must keep parent-linked rows after save/load."""
    import curation.review_rules as rr

    normalized = rr._normalize_ruleset(
        "x",
        {
            "field_rules": [
                {
                    "block": "citation",
                    "field": "author.authorIdentifier",
                    "label": "Identifier",
                    "handler": "nonempty",
                    "level": "optional",
                    "requirement": "",
                    "response_template": "",
                },
            ]
        },
    )
    assert normalized is not None
    assert normalized["field_rules"][0]["field"] == "author.authorIdentifier"
