"""Regression tests for the dashboard table cache (no network, no GUI).

Covers: change-only diffing (added/removed/changed), fingerprint ignoring
local enrichment, cache save/load round-trip, corrupt-cache tolerance and
per-instance cache-key separation.
"""

from ui.dashboard import (
    _dataset_fingerprint,
    dashboard_cache_key,
    diff_dashboard_datasets,
    load_dashboard_cache,
    save_dashboard_cache,
)


def _row(pid, **over):
    base = {
        "persistent_id": pid,
        "title": f"Title {pid}",
        "contact": "Contact",
        "depositor": "Contact",
        "date_created": "2024-01-01",
        "date_published": "2024-02-01",
        "collection": "Coll",
        "state": "DRAFT",
        "has_draft": True,
        "publication_statuses": ["Draft"],
        "file_count": 2,
        "total_size_bytes": None,
        "curation_label": "",
        "curation_time": "",
        "curation_assigner": "",
        "downloaded_at": "",
    }
    base.update(over)
    return base


def test_diff_detects_added_removed_changed():
    old = [_row("doi:1"), _row("doi:2"), _row("doi:3")]
    new = [
        _row("doi:1"),
        _row("doi:2", title="Retitled"),  # changed
        _row("doi:4"),  # added (doi:3 removed)
    ]
    diff = diff_dashboard_datasets(old, new)
    assert diff["added"] == ["doi:4"]
    assert diff["removed"] == ["doi:3"]
    assert diff["changed"] == ["doi:2"]


def test_diff_ignores_local_enrichment():
    old = [_row("doi:1")]
    new = [
        _row(
            "doi:1",
            downloaded_at="2026-01-01 10:00",
            total_size_bytes=1234,
            size_from_cache=True,
        )
    ]
    assert diff_dashboard_datasets(old, new) == {"added": [], "removed": [], "changed": []}


def test_diff_flags_state_label_and_file_changes():
    old = [_row("doi:1")]
    assert diff_dashboard_datasets(old, [_row("doi:1", state="In Review")])["changed"] == ["doi:1"]
    assert diff_dashboard_datasets(old, [_row("doi:1", curation_label="Approve")])["changed"] == [
        "doi:1"
    ]
    assert diff_dashboard_datasets(old, [_row("doi:1", file_count=5)])["changed"] == ["doi:1"]
    assert diff_dashboard_datasets([], []) == {"added": [], "removed": [], "changed": []}


def test_fingerprint_stable_for_identical_rows():
    assert _dataset_fingerprint(_row("doi:1")) == _dataset_fingerprint(_row("doi:1"))


def test_cache_round_trip(tmp_path):
    key = dashboard_cache_key("https://demo.example.ca/", "dv")
    rows = [_row("doi:1"), _row("doi:2")]
    save_dashboard_cache(tmp_path, key, rows, ["Approve", "Reject"])
    entry = load_dashboard_cache(tmp_path, key)
    assert entry is not None
    assert [d["persistent_id"] for d in entry["datasets"]] == ["doi:1", "doi:2"]
    assert entry["labels"] == ["Approve", "Reject"]
    assert entry["saved_at"]


def test_cache_missing_and_corrupt(tmp_path):
    assert load_dashboard_cache(tmp_path, "nope|x") is None
    (tmp_path / "dashboard_cache.json").write_text("{not json", encoding="utf-8")
    assert load_dashboard_cache(tmp_path, "nope|x") is None


def test_cache_key_separates_instances_and_collections():
    a = dashboard_cache_key("https://demo.example.ca", "dv")
    assert dashboard_cache_key("https://demo.example.ca/", "dv") == a
    assert dashboard_cache_key("https://demo.example.ca", "DV") == a
    assert dashboard_cache_key("https://demo.example.ca", "") != a
    assert dashboard_cache_key("https://other.example.ca", "dv") != a


def test_cache_slots_do_not_clobber(tmp_path):
    k1 = dashboard_cache_key("https://a.example.ca", "dv")
    k2 = dashboard_cache_key("https://a.example.ca", "other")
    save_dashboard_cache(tmp_path, k1, [_row("doi:1")], [])
    save_dashboard_cache(tmp_path, k2, [_row("doi:9")], [])
    assert [d["persistent_id"] for d in load_dashboard_cache(tmp_path, k1)["datasets"]] == ["doi:1"]
    assert [d["persistent_id"] for d in load_dashboard_cache(tmp_path, k2)["datasets"]] == ["doi:9"]
