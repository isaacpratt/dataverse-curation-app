"""Dashboard enrichment: bulk inventory sums without dvmeta (no network).

Covers W-01 (enrich_datasets_with_inventory: sums/patches, drafts-first
cap, per-item isolation, auth abort, cancellation, discovery cap),
W-03 (progressive merge helper) and W-04 (cache round-trip preserves
enriched fields; size-only changes stay out of the diff fingerprint).
"""

from pathlib import Path
from typing import Any

import pytest
import requests

from curation.client import DataverseClient
from curation.dashboard_cache import (
    diff_dashboard_datasets,
    load_dashboard_cache,
    merge_enriched_rows,
    save_dashboard_cache,
)


def _version_doc(files: list[Any], depositor: str = "", state: str = "DRAFT") -> dict[str, Any]:
    return {
        "datasetVersion": {
            "versionState": state,
            "metadataBlocks": {
                "citation": {
                    "fields": [
                        {"typeName": "title", "value": "T"},
                        {"typeName": "depositor", "value": depositor},
                    ]
                }
            },
            "files": files,
        }
    }


def _entry(name: str, size: int) -> dict[str, Any]:
    return {
        "filename": name,
        "dataFile": {
            "id": 1,
            "filesize": size,
            "contentType": "text/csv",
            "checksum": {"type": "MD5", "value": "d" * 32},
        },
    }


def _thin(pid: str, draft: bool = True) -> dict[str, Any]:
    return {
        "persistent_id": pid,
        "title": f"Title {pid}",
        "contact": "Contact Person",
        "depositor": "Contact Person",  # search fallback: contact as depositor
        "state": "DRAFT" if draft else "RELEASED",
        "has_draft": draft,
        "file_count": 0,
        "total_size_bytes": None,
    }


class _StubClient(DataverseClient):
    """DataverseClient with canned version docs (no network)."""

    def __init__(self, docs: Any) -> None:
        super().__init__("https://example.invalid", "token")
        self._docs = docs

    def _fetch_version_data(
        self, identifier: str, version: Any = "draft", fall_back_on_auth: bool = False
    ) -> tuple[Any, str, list[Any]]:
        doc = self._docs.get(identifier)
        if isinstance(doc, BaseException):
            raise doc
        return doc, ":draft", []


def _http_error(status: int) -> requests.HTTPError:
    resp = requests.Response()
    resp.status_code = status
    exc = requests.HTTPError(f"HTTP {status}")
    exc.response = resp
    return exc


def test_enrich_sums_and_patches() -> None:
    pid = "doi:10.5072/FK2/A"
    docs = {pid: _version_doc([_entry("a.csv", 100), _entry("b.csv", 50)], depositor="Carol C.")}
    client = _StubClient(docs)
    rows = [_thin(pid)]
    stats = client.enrich_datasets_with_inventory(rows, max_workers=1)
    assert stats == {"attempted": 1, "enriched": 1, "pending": 0, "auth_failed": 0}
    row = rows[0]
    assert row["total_size_bytes"] == 150
    assert row["size_enriched"] is True
    assert row["depositor"] == "Carol C."
    assert row["state"] == "DRAFT"
    assert row["has_draft"] is True
    assert row["file_count"] == 2  # falsy search count filled from inventory
    assert "files" not in row  # sums-only: no file arrays embedded


def test_drafts_first_with_cap() -> None:
    pub, draft = "doi:10.5072/FK2/PUB", "doi:10.5072/FK2/DRF"
    docs = {
        pub: _version_doc([_entry("p.csv", 10)], state="RELEASED"),
        draft: _version_doc([_entry("d.csv", 20)]),
    }
    client = _StubClient(docs)
    rows = [_thin(pub, draft=False), _thin(draft, draft=True)]
    stats = client.enrich_datasets_with_inventory(rows, max_rows=1, max_workers=1)
    assert stats["enriched"] == 1
    assert stats["pending"] == 1
    by_pid = {r["persistent_id"]: r for r in rows}
    assert by_pid[draft]["total_size_bytes"] == 20
    assert by_pid[pub].get("total_size_bytes") is None
    assert by_pid[pub].get("size_pending") is True


def test_error_isolation() -> None:
    pids = [f"doi:10.5072/FK2/{c}" for c in "ABC"]
    docs = {
        pids[0]: _version_doc([_entry("a.csv", 5)]),
        pids[1]: RuntimeError("boom"),
        pids[2]: _version_doc([_entry("c.csv", 7)]),
    }
    client = _StubClient(docs)
    rows = [_thin(p) for p in pids]
    stats = client.enrich_datasets_with_inventory(rows, max_workers=2)
    assert stats["attempted"] == 3
    assert stats["enriched"] == 2
    assert rows[0]["total_size_bytes"] == 5
    assert rows[1].get("total_size_bytes") is None
    assert rows[2]["total_size_bytes"] == 7


def test_auth_abort() -> None:
    pid = "doi:10.5072/FK2/A"
    client = _StubClient({pid: _http_error(401)})
    rows = [_thin(pid)]
    stats = client.enrich_datasets_with_inventory(rows, max_workers=1)
    assert stats["auth_failed"] == 1
    assert stats["enriched"] == 0
    assert rows[0].get("total_size_bytes") is None
    assert "size_enriched" not in rows[0]


def test_cancellation() -> None:
    pids = [f"doi:10.5072/FK2/{c}" for c in "ABC"]
    docs = {p: _version_doc([_entry("f.csv", 1)]) for p in pids}
    client = _StubClient(docs)
    calls: dict[str, int] = {"n": 0}

    def _cancel_after_first() -> bool:
        calls["n"] += 1
        return calls["n"] > 1

    rows = [_thin(p) for p in pids]
    stats = client.enrich_datasets_with_inventory(
        rows, max_workers=1, is_cancelled=_cancel_after_first
    )
    assert stats["attempted"] == 1
    assert stats["enriched"] == 1
    assert rows[0]["total_size_bytes"] == 1
    assert rows[1].get("total_size_bytes") is None


def test_enrichment_never_clobbers_in_review() -> None:
    pid = "doi:10.5072/FK2/A"
    docs = {pid: _version_doc([_entry("a.csv", 9)], state="RELEASED")}
    client = _StubClient(docs)
    rows = [_thin(pid)]
    rows[0]["state"] = "In Review"  # locks stage already confirmed
    client.enrich_datasets_with_inventory(rows, max_workers=1)
    assert rows[0]["state"] == "In Review"
    assert rows[0]["total_size_bytes"] == 9


def test_discovery_pages_until_total(monkeypatch: pytest.MonkeyPatch) -> None:
    """Discovery is total-driven: 2500 datasets at per_page=1000 → 3 calls."""
    calls: dict[str, int] = {"n": 0}

    def _page(
        self: Any, subtree: Any = "", per_page: int = 1000, start: int = 0
    ) -> tuple[list[dict[str, Any]], int | None]:
        calls["n"] += 1
        remaining = 2500 - start
        n = max(0, min(per_page, remaining))
        return (
            [
                {"persistent_id": f"doi:10.5072/FK2/{start + i}", "has_draft": False}
                for i in range(n)
            ],
            2500,
        )

    monkeypatch.setattr(DataverseClient, "_search_page", _page)
    client = DataverseClient("https://example.invalid", "token")
    try:
        rows = client.list_draft_datasets("")
    finally:
        client.close()
    assert calls["n"] == 3
    assert len(rows) == 2500


def test_discovery_stops_on_short_page_when_total_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """No total_count from the server → the short page ends the crawl."""
    calls: dict[str, int] = {"n": 0}

    def _page(
        self: Any, subtree: Any = "", per_page: int = 1000, start: int = 0
    ) -> tuple[list[dict[str, Any]], int | None]:
        calls["n"] += 1
        n = 1000 if start == 0 else 12
        return (
            [
                {"persistent_id": f"doi:10.5072/FK2/{start + i}", "has_draft": False}
                for i in range(n)
            ],
            None,
        )

    monkeypatch.setattr(DataverseClient, "_search_page", _page)
    client = DataverseClient("https://example.invalid", "token")
    try:
        rows = client.list_draft_datasets("")
    finally:
        client.close()
    assert calls["n"] == 2
    assert len(rows) == 1012


def test_discovery_runaway_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """A server that always returns a full page stops at the guard."""
    calls: dict[str, int] = {"n": 0}

    def _page(
        self: Any, subtree: Any = "", per_page: int = 1000, start: int = 0
    ) -> tuple[list[dict[str, Any]], int | None]:
        calls["n"] += 1
        return (
            [
                {"persistent_id": f"doi:10.5072/FK2/{start + i}", "has_draft": False}
                for i in range(per_page)
            ],
            None,
        )

    monkeypatch.setattr(DataverseClient, "_search_page", _page)
    client = DataverseClient("https://example.invalid", "token")
    try:
        rows = client.list_draft_datasets("", per_page=1000, max_pages=3)
    finally:
        client.close()
    assert calls["n"] == 3
    assert len(rows) == 3000


def test_discovery_progress_reports_page_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[Any] = []

    def _page(
        self: Any, subtree: Any = "", per_page: int = 1000, start: int = 0
    ) -> tuple[list[dict[str, Any]], int | None]:
        remaining = 2000 - start
        n = max(0, min(per_page, remaining))
        return (
            [
                {"persistent_id": f"doi:10.5072/FK2/{start + i}", "has_draft": False}
                for i in range(n)
            ],
            2000,
        )

    monkeypatch.setattr(DataverseClient, "_search_page", _page)
    client = DataverseClient("https://example.invalid", "token")
    try:
        client.list_draft_datasets("", progress=lambda p, t, c: seen.append((p, t, c)))
    finally:
        client.close()
    assert seen == [(1, 2, 1000), (2, 2, 2000)]


def test_enrichment_falls_back_to_published_when_draft_denied() -> None:
    """A published dataset with no readable draft still enriches.

    `:draft` is refused (401) but `:latest` answers — the row must be
    enriched from the published version, not dropped. Stubs the HTTP
    layer so the real version-fallback logic runs.
    """
    pid = "doi:10.5072/FK2/PUB"
    # A plain client (no _fetch_version_data override) so the real
    # version-fallback logic runs against a patched HTTP layer.
    client = DataverseClient("https://example.invalid", "token")
    seen: list[str] = []

    def _get_json(path: str, params: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        seen.append(path)
        if path.endswith("/versions/:draft"):
            raise _http_error(401)
        return {
            "data": {
                "files": [_entry("p.csv", 42)],
                "versionState": "RELEASED",
            }
        }

    client._get_json = _get_json  # type: ignore[method-assign]
    rows = [_thin(pid, draft=False)]
    stats = client.enrich_datasets_with_inventory(rows, max_workers=1)
    assert stats["enriched"] == 1
    assert stats["auth_failed"] == 0
    assert rows[0]["total_size_bytes"] == 42
    assert any(p.endswith("/versions/:draft") for p in seen)
    assert any(p.endswith("/versions/:latest") for p in seen)


def test_enrichment_leaves_size_unknown_when_files_absent() -> None:
    """A payload with no `files` key means 'unknown', not 'zero bytes'."""
    pid = "doi:10.5072/FK2/NOFILES"
    client = _StubClient({pid: {"versionState": "RELEASED", "metadataBlocks": {}}})
    rows = [_thin(pid, draft=False)]
    stats = client.enrich_datasets_with_inventory(rows, max_workers=1)
    assert stats["enriched"] == 1
    assert rows[0].get("total_size_bytes") is None
    assert "size_enriched" not in rows[0]


def test_merge_helper_copies_and_preserves_review() -> None:
    existing = [_thin("doi:10.5072/FK2/A")]
    existing[0]["state"] = "In Review"
    existing[0]["total_size_bytes"] = 111
    existing[0]["size_from_cache"] = True
    batch = [
        {
            "persistent_id": "doi:10.5072/FK2/A",
            "total_size_bytes": 150,
            "file_count": 2,
            "depositor": "Carol C.",
            "state": "RELEASED",
            "has_draft": True,
            "size_enriched": True,
        },
        {"persistent_id": "doi:10.5072/FK2/GHOST", "total_size_bytes": 1},
    ]
    assert merge_enriched_rows(existing, batch) == 1
    row = existing[0]
    assert row["total_size_bytes"] == 150  # live value wins
    assert row.get("size_from_cache") is None  # stale disk fill cleared
    assert row["depositor"] == "Carol C."
    assert row["state"] == "In Review"  # lock confirmation preserved
    assert merge_enriched_rows(existing, []) == 0
    assert merge_enriched_rows(existing, [{"no_pid": 1}]) == 0


def test_cache_roundtrip_and_diff_semantics(tmp_path: Path) -> None:
    old = [_thin("doi:10.5072/FK2/A")]
    new = [_thin("doi:10.5072/FK2/A")]
    new[0].update(
        {
            "total_size_bytes": 150,  # size-only change: invisible to diff
            "size_enriched": True,
            "size_pending": False,
        }
    )
    assert diff_dashboard_datasets(old, new)["changed"] == []
    new[0]["depositor"] = "Carol C."  # genuine new data: visible
    assert diff_dashboard_datasets(old, new)["changed"] == ["doi:10.5072/FK2/A"]
    save_dashboard_cache(tmp_path, "k", new, ["L1"])
    loaded = load_dashboard_cache(tmp_path, "k")
    assert loaded is not None
    row = loaded["datasets"][0]
    assert row["total_size_bytes"] == 150
    assert row["size_enriched"] is True
    assert loaded["labels"] == ["L1"]
