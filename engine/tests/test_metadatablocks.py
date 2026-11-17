"""Tests for metadatablocks parsing + field-catalog cache (dataverse_client)."""

from pathlib import Path
from typing import Any

import pytest

from dataverse_client import (
    get_cached_metadata_fields,
    parse_metadatablock_display_names,
    parse_metadatablock_fields,
    parse_metadatablock_names,
    read_metadata_fields_cache,
    set_cached_metadata_fields,
    write_metadata_fields_cache,
)


def test_parse_block_names() -> None:
    assert parse_metadatablock_names({"data": [{"name": "citation"}, {"name": "geospatial"}]}) == [
        "citation",
        "geospatial",
    ]
    assert parse_metadatablock_names({}) == []
    assert parse_metadatablock_names({"data": "nope"}) == []


def test_parse_block_fields_dict_shape() -> None:
    out = parse_metadatablock_fields(
        {
            "data": {
                "name": "citation",
                "metadataFields": {
                    "title": {"displayName": "Title"},
                    "author": {"displayName": "Author"},
                },
            }
        }
    )
    assert {"block": "citation", "field": "title", "label": "Title"} in out
    assert len(out) == 2


def test_parse_block_fields_list_shape() -> None:
    out = parse_metadatablock_fields(
        {
            "data": {
                "name": "citation",
                "metadataFields": [
                    {"name": "title", "displayName": "Title"},
                ],
            }
        }
    )
    assert out == [{"block": "citation", "field": "title", "label": "Title"}]


def test_parse_block_fields_newer_fields_shape() -> None:
    """Dataverse 6.8 answers data.fields (dict keyed by field name)."""
    out = parse_metadatablock_fields(
        {
            "data": {
                "name": "geospatial",
                "fields": {
                    "geographicCoverage": {
                        "name": "geographicCoverage",
                        "displayName": "Geographic Coverage",
                    },
                    "geographicUnit": {"name": "geographicUnit"},
                },
            }
        }
    )
    assert {
        "block": "geospatial",
        "field": "geographicCoverage",
        "label": "Geographic Coverage",
    } in out
    assert {"block": "geospatial", "field": "geographicUnit", "label": "geographicUnit"} in out
    assert len(out) == 2
    # metadataFields still wins when both keys are present
    out2 = parse_metadatablock_fields(
        {
            "data": {
                "name": "citation",
                "metadataFields": {"title": {"displayName": "Title"}},
                "fields": {"other": {"displayName": "Other"}},
            }
        }
    )
    assert out2 == [{"block": "citation", "field": "title", "label": "Title"}]


def test_fields_cache_roundtrip(tmp_path: Path) -> None:
    base = "https://example.invalid"
    fields = [{"block": "citation", "field": "title", "label": "Title"}]
    write_metadata_fields_cache(tmp_path, base, fields)
    assert read_metadata_fields_cache(tmp_path, base) == fields
    assert read_metadata_fields_cache(tmp_path, "https://other.invalid") is None


def test_memory_cache_roundtrip() -> None:
    set_cached_metadata_fields("https://mem.invalid", [{"block": "b", "field": "f", "label": "L"}])
    assert get_cached_metadata_fields("https://mem.invalid") == [
        {"block": "b", "field": "f", "label": "L"}
    ]


def test_parse_block_display_names() -> None:
    out = parse_metadatablock_display_names(
        {
            "data": [
                {"name": "citation", "displayName": "Citation Metadata"},
                {"name": "geospatial"},
                {"name": ""},
                "nope",
            ]
        }
    )
    assert out == {"citation": "Citation Metadata", "geospatial": "geospatial"}
    assert parse_metadatablock_display_names({}) == {}


def test_fetch_skips_empty_memory_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """[] in memory means 'fetch failed' — refetch, don't serve it."""
    import dataverse_client as _dc

    monkeypatch.setattr(_dc, "_METADATABLOCKS_MEMO", {})
    set_cached_metadata_fields("https://empty.invalid", [])
    calls: list[str] = []

    def fake_json(self: Any, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        calls.append(path)
        if path == "/api/metadatablocks":
            return {"data": [{"name": "citation", "displayName": "Citation Metadata"}]}
        return {"data": {"name": "citation", "fields": {"title": {"displayName": "Title"}}}}

    monkeypatch.setattr(_dc.DataverseClient, "_get_json", fake_json)
    client = _dc.DataverseClient("https://empty.invalid", "tok")
    fields = client.fetch_metadata_field_catalog()
    assert calls, "empty memory cache must trigger a refetch"
    assert fields == [
        {
            "block": "citation",
            "field": "title",
            "label": "Title",
            "block_label": "Citation Metadata",
        }
    ]


def test_fetch_attaches_block_labels(monkeypatch: pytest.MonkeyPatch) -> None:
    import dataverse_client as _dc

    monkeypatch.setattr(_dc, "_METADATABLOCKS_MEMO", {})

    def fake_json(self: Any, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if path == "/api/metadatablocks":
            return {"data": [{"name": "citation", "displayName": "Citation Metadata"}]}
        return {"data": {"name": "citation", "metadataFields": {"title": {"displayName": "Title"}}}}

    monkeypatch.setattr(_dc.DataverseClient, "_get_json", fake_json)
    client = _dc.DataverseClient("https://lbl.invalid", "tok")
    fields = client.fetch_metadata_field_catalog()
    assert fields[0]["block_label"] == "Citation Metadata"
