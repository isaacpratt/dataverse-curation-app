"""Dashboard enrichment: bulk inventory sums without dvmeta (no network).

Covers W-01 (enrich_datasets_with_inventory: sums/patches, drafts-first
cap, per-item isolation, auth abort, cancellation, discovery cap),
W-03 (progressive merge helper) and W-04 (cache round-trip preserves
enriched fields; size-only changes stay out of the diff fingerprint).
"""

import requests

from dataverse_client import DataverseClient
from ui.dashboard import (
    _merge_enriched_rows,
    diff_dashboard_datasets,
    load_dashboard_cache,
    save_dashboard_cache,
)


def _version_doc(files, depositor="", state="DRAFT"):
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


def _entry(name, size):
    return {
        "filename": name,
        "dataFile": {
            "id": 1,
            "filesize": size,
            "contentType": "text/csv",
            "checksum": {"type": "MD5", "value": "d" * 32},
        },
    }


def _thin(pid, draft=True):
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

    def __init__(self, docs):
        super().__init__("https://example.invalid", "token")
        self._docs = docs

    def _fetch_version_data(self, identifier, version="draft", fall_back_on_auth=False,
                            order=None):
        doc = self._docs.get(identifier)
        if isinstance(doc, BaseException):
            raise doc
        return doc, ":draft", []


def _http_error(status):
    resp = requests.Response()
    resp.status_code = status
    exc = requests.HTTPError(f"HTTP {status}")
    exc.response = resp
    return exc


def test_enrich_sums_and_patches():
    pid = "doi:10.5072/FK2/A"
    docs = {
        pid: _version_doc(
            [_entry("a.csv", 100), _entry("b.csv", 50)], depositor="Carol C."
        )
    }
    client = _StubClient(docs)
    rows = [_thin(pid)]
    stats = client.enrich_datasets_with_inventory(rows, max_workers=1)
    assert stats == {
        "attempted": 1, "enriched": 1, "pending": 0,
        "auth_failed": 0, "restricted": 0,
    }
    row = rows[0]
    assert row["total_size_bytes"] == 150
    assert row["size_enriched"] is True
    assert row["depositor"] == "Carol C."
    assert row["state"] == "DRAFT"
    assert row["has_draft"] is True
    assert row["file_count"] == 2  # falsy search count filled from inventory
    assert "files" not in row  # sums-only: no file arrays embedded
    assert row["access"]["state"] == "readable"
    assert row["access"]["version"] == ":draft"


def test_drafts_first_with_cap():
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


def test_error_isolation():
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


def test_restricted_row_is_marked_and_the_batch_continues():
    """A dataset this account may not read is marked, not dropped.

    A 401 on one dataset is the server's answer for that dataset (its
    curation scope), not a broken token: the row records the refusal and
    the other rows are still enriched.
    """
    denied, ok = "doi:10.5072/FK2/DENIED", "doi:10.5072/FK2/OK"
    client = _StubClient(
        {denied: _http_error(401), ok: _version_doc([_entry("a.csv", 5)])}
    )
    rows = [_thin(denied), _thin(ok)]
    stats = client.enrich_datasets_with_inventory(rows, max_workers=1)
    assert stats["restricted"] == 1
    assert stats["enriched"] == 1
    assert stats["auth_failed"] == 0
    denied_row = rows[0]
    assert denied_row["access"]["state"] == "restricted"
    assert denied_row["access"]["reason"]
    assert denied_row.get("total_size_bytes") is None
    assert rows[1]["total_size_bytes"] == 5


def test_cancellation():
    pids = [f"doi:10.5072/FK2/{c}" for c in "ABC"]
    docs = {p: _version_doc([_entry("f.csv", 1)]) for p in pids}
    client = _StubClient(docs)
    calls = {"n": 0}

    def _cancel_after_first():
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


def test_enrichment_never_clobbers_in_review():
    pid = "doi:10.5072/FK2/A"
    docs = {pid: _version_doc([_entry("a.csv", 9)], state="RELEASED")}
    client = _StubClient(docs)
    rows = [_thin(pid)]
    rows[0]["state"] = "In Review"  # locks stage already confirmed
    client.enrich_datasets_with_inventory(rows, max_workers=1)
    assert rows[0]["state"] == "In Review"
    assert rows[0]["total_size_bytes"] == 9


def test_discovery_pages_until_total(monkeypatch):
    """Discovery is total-driven: 2500 datasets at per_page=1000 → 3 calls."""
    calls = {"n": 0}

    def _page(self, subtree="", per_page=1000, start=0):
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


def test_discovery_stops_on_short_page_when_total_missing(monkeypatch):
    """No total_count from the server → the short page ends the crawl."""
    calls = {"n": 0}

    def _page(self, subtree="", per_page=1000, start=0):
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


def test_discovery_runaway_guard(monkeypatch):
    """A server that always returns a full page stops at the guard."""
    calls = {"n": 0}

    def _page(self, subtree="", per_page=1000, start=0):
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


def test_discovery_progress_reports_page_counts(monkeypatch):
    seen = []

    def _page(self, subtree="", per_page=1000, start=0):
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


def test_published_row_is_read_once_without_a_version_probe():
    """A published row needs one dataset read — no doomed :draft probe.

    The search payload already says the dataset is published with no
    draft, and a :draft probe there is answered "not permitted" every
    time. The unversioned dataset read answers with the published
    version.
    """
    pid = "doi:10.5072/FK2/PUB"
    client = DataverseClient("https://example.invalid", "token")
    seen = []

    def _get_json(path, params=None, **kwargs):
        seen.append(path)
        return {
            "data": {
                "latestVersion": {
                    "files": [_entry("p.csv", 42)],
                    "versionState": "RELEASED",
                }
            }
        }

    client._get_json = _get_json
    rows = [_thin(pid, draft=False)]
    stats = client.enrich_datasets_with_inventory(rows, max_workers=1)
    assert stats["enriched"] == 1
    assert rows[0]["total_size_bytes"] == 42
    assert rows[0]["access"]["state"] == "readable"
    assert rows[0]["access"]["version"] == ":latest-published"
    # One call, and it is not a version probe.
    assert len(seen) == 1
    assert "/versions/" not in seen[0]


def test_deaccessioned_row_never_asks_for_a_published_version():
    """A deaccessioned row has no published version — do not ask for one."""
    pid = "doi:10.5072/FK2/DEACC"
    client = DataverseClient("https://example.invalid", "token")
    seen = []

    def _get_json(path, params=None, **kwargs):
        seen.append(path)
        if "/versions/" in path:
            raise _http_error(404)
        # The dataset itself answers (a deaccessioned dataset still has a
        # record) — only its versions are gone.
        return {"data": {"versionState": "DEACCESSIONED"}}

    client._get_json = _get_json
    rows = [_thin(pid, draft=False)]
    rows[0]["state"] = "DEACCESSIONED"
    client.enrich_datasets_with_inventory(rows, max_workers=1)
    assert not any("/versions/" in p for p in seen)
    assert rows[0]["access"]["state"] == "metadata_only"
    assert rows[0]["access"]["reason"] == "no_published_version"
    assert rows[0].get("size_enriched") is None


def test_draft_row_probes_draft_first_and_falls_back():
    """A row under curation is read at :draft first, the dataset read second."""
    pid = "doi:10.5072/FK2/DRF"
    client = DataverseClient("https://example.invalid", "token")
    seen = []

    def _get_json(path, params=None, **kwargs):
        seen.append(path)
        if path.endswith("/versions/:draft"):
            raise _http_error(401)
        # The dataset read answers with the published version.
        return {
            "data": {
                "latestVersion": {
                    "files": [_entry("d.csv", 7)],
                    "versionState": "RELEASED",
                }
            }
        }

    client._get_json = _get_json
    rows = [_thin(pid, draft=True)]
    stats = client.enrich_datasets_with_inventory(rows, max_workers=1)
    assert stats["enriched"] == 1
    assert rows[0]["total_size_bytes"] == 7
    assert seen[0].endswith("/versions/:draft")
    assert "/versions/" not in seen[1]
    # The draft was refused for this account, so the row says so.
    assert rows[0]["access"]["state"] == "readable"
    assert rows[0]["access"]["version"] == ":latest-published"


def test_draft_row_readable_at_draft_is_marked_as_a_draft():
    """A draft the account may read is recorded as a draft."""
    pid = "doi:10.5072/FK2/DRF2"
    client = DataverseClient("https://example.invalid", "token")
    seen = []

    def _get_json(path, params=None, **kwargs):
        seen.append(path)
        return {
            "data": {
                "files": [_entry("d.csv", 7)],
                "versionState": "DRAFT",
            }
        }

    client._get_json = _get_json
    rows = [_thin(pid, draft=True)]
    stats = client.enrich_datasets_with_inventory(rows, max_workers=1)
    assert stats["enriched"] == 1
    assert seen[0].endswith("/versions/:draft")
    assert len(seen) == 1
    assert rows[0]["has_draft"] is True
    assert rows[0]["access"]["state"] == "readable"
    assert rows[0]["access"]["version"] == ":draft"


def test_enrichment_leaves_size_unknown_when_files_absent():
    """A payload with no `files` key means 'unknown', not 'zero bytes'."""
    pid = "doi:10.5072/FK2/NOFILES"
    client = _StubClient({pid: {"versionState": "RELEASED", "metadataBlocks": {}}})
    rows = [_thin(pid, draft=False)]
    stats = client.enrich_datasets_with_inventory(rows, max_workers=1)
    assert stats["enriched"] == 1
    assert rows[0].get("total_size_bytes") is None
    assert "size_enriched" not in rows[0]


def test_merge_helper_copies_and_preserves_review():
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
    assert _merge_enriched_rows(existing, batch) == 1
    row = existing[0]
    assert row["total_size_bytes"] == 150  # live value wins
    assert row.get("size_from_cache") is None  # stale disk fill cleared
    assert row["depositor"] == "Carol C."
    assert row["state"] == "In Review"  # lock confirmation preserved
    assert _merge_enriched_rows(existing, []) == 0
    assert _merge_enriched_rows(existing, [{"no_pid": 1}]) == 0


def test_cache_roundtrip_and_diff_semantics(tmp_path):
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
