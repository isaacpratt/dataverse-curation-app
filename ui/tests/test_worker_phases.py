"""Worker phase methods, driven synchronously with stub clients (dv-130).

The QThreads are constructed without starting them: each phase takes its
client explicitly and only emits signals, so no network or thread scheduling
is involved. This is what makes ui/workers.py testable in a few seconds.
"""

from __future__ import annotations

import threading
from typing import Any

import pytest
from PySide6.QtCore import QThread

from curation.client import STATE_IN_REVIEW
from ui import workers
from ui.i18n import t


class _Client:
    """Minimal client double; methods record calls and return canned data."""

    def __init__(self, **overrides: Any) -> None:
        self.calls: list[tuple[str, Any]] = []
        self._overrides = overrides

    def __getattr__(self, name: str) -> Any:
        def _call(*args: Any, **kwargs: Any) -> Any:
            self.calls.append((name, args))
            value = self._overrides.get(name)
            return value(*args, **kwargs) if callable(value) else value

        return _call


class _CancelledCrawl(workers.CrawlWorker):
    def isInterruptionRequested(self) -> bool:
        return True


class _CancelledDetail(workers.MetadataWorker):
    def isInterruptionRequested(self) -> bool:
        return True


def _crawl(cancelled: bool = False) -> tuple[Any, dict[str, list[Any]]]:
    cls = _CancelledCrawl if cancelled else workers.CrawlWorker
    worker = cls.__new__(cls)
    QThread.__init__(worker)
    worker._base_url = "https://demo.test"
    worker._api_token = "tok"
    worker._subtree = ""
    worker._last_fraction = -1.0
    captured: dict[str, list[Any]] = {
        "progress": [],
        "enriched": [],
        "allowed": [],
        "labels": [],
        "fractions": [],
    }
    worker.progress.connect(lambda msg: captured["progress"].append(msg))
    worker.enriched.connect(lambda rows: captured["enriched"].append(rows))
    worker.allowedProbed.connect(lambda payload: captured["allowed"].append(payload))
    worker.labelsDiscovered.connect(lambda labels: captured["labels"].append(labels))
    worker.progressFraction.connect(lambda value: captured["fractions"].append(value))
    return worker, captured


def _detail(cancelled: bool = False) -> tuple[Any, dict[str, list[Any]]]:
    cls = _CancelledDetail if cancelled else workers.MetadataWorker
    worker = cls.__new__(cls)
    QThread.__init__(worker)
    worker._base_url = "https://demo.test"
    worker._api_token = "tok"
    worker._pid = "doi:10.1/X"
    worker._collection = "science"
    worker._draft_hint = None
    captured: dict[str, list[Any]] = {"finished": []}
    worker.finished.connect(lambda *args: captured["finished"].append(args))
    return worker, captured


def test_discovery_progress_and_fraction(qapp: Any) -> None:
    worker, seen = _crawl()
    worker._discovery_progress(2, 5, 200)
    worker._discovery_progress(7, 0, 7)
    assert len(seen["progress"]) == 2
    assert t("workers.fetching_page", page=2, pages=5, found=200) == seen["progress"][0]
    assert t("workers.fetching_found", found=7) == seen["progress"][1]
    # Fractions are monotonic; the "found" path may sit below the page path.
    assert seen["fractions"] == sorted(seen["fractions"])
    assert seen["fractions"]


def test_discover_forwards_callbacks_and_returns_rows(qapp: Any) -> None:
    worker, seen = _crawl()

    def _list(subtree: str, progress: Any, is_cancelled: Any) -> list[dict[str, Any]]:
        assert subtree == ""
        progress(1, 2, 5)
        assert callable(is_cancelled)
        return [{"persistent_id": "p1"}]

    client = _Client(list_draft_datasets=_list)
    rows = worker._discover(client)
    assert rows == [{"persistent_id": "p1"}]
    assert t("workers.fetching_all", collection=t("workers.whole_repository")) in seen["progress"]
    assert seen["fractions"]


def test_enrich_progress_flushes_at_cap_and_tail(qapp: Any) -> None:
    worker, seen = _crawl()
    datasets = [{"persistent_id": f"p{i}", "size_enriched": True} for i in range(30)]
    emitted: set[str] = set()
    batch: list[dict[str, Any]] = []
    worker._enrich_progress(25, 30, datasets, emitted, batch)
    assert len(seen["enriched"]) == 1
    assert len(seen["enriched"][0]) == 30
    assert all(
        isinstance(row, dict) and row is not d
        for d, row in zip(datasets, seen["enriched"][0], strict=True)
    )
    assert batch == []
    assert len(emitted) == 30
    worker._enrich_progress(30, 30, datasets, emitted, batch)
    assert len(seen["enriched"]) == 1  # nothing new to flush

    batch2: list[dict[str, Any]] = []
    worker._enrich_progress(3, 3, datasets[:3], set(), batch2)
    assert len(seen["enriched"]) == 2
    assert len(seen["enriched"][1]) == 3


def test_enrich_cancellation_and_reporting(qapp: Any) -> None:
    import curation.applog as applog

    applog.clear()
    worker, seen = _crawl()
    stats = {"attempted": 7, "enriched": 5, "pending": 2}
    client = _Client(enrich_datasets_with_inventory=stats)
    datasets = [{"persistent_id": "p1"}]

    assert worker._enrich(client, datasets) is True
    assert any("200" in line for line in applog.lines())
    assert t("workers.enriched", count=5, tail=t("workers.beyond_cap", count=2)) in seen["progress"]

    cancelled, cancelled_seen = _crawl(cancelled=True)
    assert cancelled._enrich(client, datasets) is False
    assert not any(
        t("workers.enriched", count=5, tail="") in msg for msg in cancelled_seen["progress"]
    )
    assert cancelled_seen["enriched"] == []


def test_probe_locks_flags_review_and_reports(qapp: Any) -> None:
    worker, seen = _crawl()
    client = _Client(dataset_in_review=lambda pid: pid == "p2")
    datasets = [{"persistent_id": "p1"}, {"persistent_id": "p2"}]
    assert worker._probe_locks(client, datasets) == 1
    assert datasets[0].get("state") is None
    assert datasets[1]["state"] == STATE_IN_REVIEW
    assert len(seen["progress"]) == 1
    assert seen["fractions"]

    cancelled, _ = _crawl(cancelled=True)
    assert cancelled._probe_locks(client, [{"persistent_id": "p1"}]) is None


def test_identity_and_report_paths(qapp: Any) -> None:
    worker, seen = _crawl()
    report = [{"persistent_id": "p1", "title": "T", "label": "Approve"}]

    superuser = _Client(
        user_is_superuser=True,
        get_me={"displayName": "Curator"},
        list_curation_states=report,
    )
    assert worker._identity_and_report(superuser) is report
    assert t("workers.connected_superuser", who="Curator") in seen["progress"]

    non_superuser = _Client(
        user_is_superuser=False, get_me={}, list_curation_states=lambda: pytest.fail("403 probe")
    )
    assert worker._identity_and_report(non_superuser) is None
    assert not any(name == "list_curation_states" for name, _ in non_superuser.calls)

    unknown = _Client(
        user_is_superuser=lambda: (_ for _ in ()).throw(RuntimeError("offline")),
        get_me={},
        list_curation_states=report,
    )
    assert worker._identity_and_report(unknown) is report


def test_apply_bulk_report_stamps_rows(qapp: Any) -> None:
    worker, seen = _crawl()
    datasets = [
        {"persistent_id": "p1", "title": "T1"},
        {"persistent_id": "p2", "title": "T2"},
        {"persistent_id": "p3", "title": "T3"},
    ]
    report = [
        {"persistent_id": "p1", "label": "Approve", "label_time": "2026-01-01", "assigner": "a"},
        {"title": "T2", "label": "Fix", "label_time": "2026-01-02", "assigner": "b"},
    ]
    labels = worker._apply_bulk_report(report, datasets)
    assert labels == ["Approve", "Fix"]
    assert datasets[0]["curation_assigner"] == "a"
    assert datasets[1]["curation_label"] == "Fix"
    assert datasets[2]["curation_label"] == ""
    assert seen["fractions"]
    assert len(seen["progress"]) == 1


def test_read_draft_statuses_and_refusal(qapp: Any) -> None:
    worker, _ = _crawl()

    def _status(pid: str, refusal: dict[str, Any]) -> dict[str, Any] | None:
        if pid == "p2":
            refusal.update({"code": "draft_not_readable", "detail": "no access", "status": 403})
            return None
        return {"label": "Approve", "time": "2026-01-01", "assigner": "a"}

    client = _Client(get_curation_status=_status)
    datasets: list[dict[str, Any]] = [
        {"persistent_id": "p1", "state": "DRAFT"},
        {"persistent_id": "p2", "state": "DRAFT"},
        {"persistent_id": "p3", "state": "RELEASED", "curation_label": "stale"},
    ]
    assert worker._read_draft_statuses(client, datasets) == ([], 2)
    assert datasets[0]["curation_label"] == "Approve"
    assert datasets[1]["curation_access"]["reason"] == "draft_not_readable"
    assert datasets[2]["curation_label"] == ""

    cancelled, _ = _crawl(cancelled=True)
    assert cancelled._read_draft_statuses(client, datasets[:1]) is None


def test_probe_allowed_labels_cached_and_pure(qapp: Any, monkeypatch: Any) -> None:
    import curation.client as client_module

    worker, seen = _crawl()
    monkeypatch.setattr(client_module, "get_cached_allowed_labels", lambda *_a: None)
    client = _Client(
        fetch_allowed_labels_shared=["Approve"],
        last_allowed_probe_answered=True,
    )
    labels: list[str] = []
    assert (
        worker._probe_allowed_labels(client, [{"persistent_id": "p1", "state": "DRAFT"}], labels)
        is True
    )
    assert labels == ["Approve"]
    payload = seen["allowed"][0]
    assert payload["probed"] is True
    assert payload["labels"] == ["Approve"]

    cached_worker, cached_seen = _crawl()
    monkeypatch.setattr(client_module, "get_cached_allowed_labels", lambda *_a: ["old"])
    assert cached_worker._probe_allowed_labels(client, [], []) is True
    assert cached_seen["allowed"][0]["probed"] is False


def test_announce_labels_emits_summary(qapp: Any) -> None:
    worker, seen = _crawl()
    worker._announce_labels(["Approve", "Fix", "Blocked", "Wontfix", "A", "B"], 4, 2)
    assert seen["labels"] == [["Approve", "Fix", "Blocked", "Wontfix", "A", "B"]]
    assert t("workers.received", total=4, in_review=2) in seen["progress"]
    assert (
        t("workers.curation_labels", labels="Approve, Fix, Blocked, Wontfix, A…")
        in seen["progress"]
    )

    empty, empty_seen = _crawl()
    empty._announce_labels([], 1, 0)
    assert t("workers.no_curation_labels") in empty_seen["progress"]


def test_detail_fetch_names_and_single_fetch(qapp: Any) -> None:
    worker, _ = _detail()
    all_names = worker._fetch_names()
    assert "curation" in all_names
    assert "version_diff" in all_names
    worker._draft_hint = False
    names = worker._fetch_names()
    assert "curation" not in names
    assert "version_diff" not in names
    assert "history" not in names

    client = _Client(
        get_dataset_metadata={"id": 1},
        get_file_inventory=[],
        get_curation_status={"label": "Approve"},
        compare_versions={},
        list_versions=[],
        get_curation_history=[],
        fetch_allowed_labels_shared=[],
        dataset_in_review=True,
    )
    refusals: dict[str, Any] = {}
    assert worker._fetch_one(client, "metadata", refusals, threading.Lock()) == (
        "metadata",
        {"id": 1},
    )
    assert worker._fetch_one(client, "curation", refusals, threading.Lock()) == (
        "curation",
        {"label": "Approve"},
    )
    assert worker._fetch_one(client, "in_review", refusals, threading.Lock()) == ("in_review", True)

    denied = RuntimeError("denied")
    denied.refusal_code = "draft_not_readable"  # type: ignore[attr-defined]
    denied.refusal_detail = "no access"  # type: ignore[attr-defined]
    denied.response = type("R", (), {"status_code": 403})()  # type: ignore[attr-defined]

    class _Deny:
        def get_dataset_metadata(self, *_a: Any, **_k: Any) -> Any:
            raise denied

    assert worker._fetch_one(_Deny(), "metadata", refusals, threading.Lock()) == ("metadata", None)
    assert refusals["metadata"]["reason"] == "draft_not_readable"


def test_detail_fanout_and_normalise(qapp: Any) -> None:
    worker, _ = _detail()
    client = _Client(
        get_dataset_metadata={"id": 1},
        get_file_inventory=[{"path": "a"}],
        get_curation_status={},
        compare_versions={},
        list_versions=["v1"],
        get_curation_history=[{"label": "Approve"}],
        fetch_allowed_labels_shared=["Approve"],
        dataset_in_review=False,
    )
    refusals: dict[str, Any] = {}
    result = worker._fanout(client, refusals, threading.Lock())
    assert result is not None
    assert set(result) >= {"metadata", "inventory", "versions", "history", "allowed"}
    assert refusals == {}

    cancelled, _ = _detail(cancelled=True)
    assert cancelled._fanout(client, {}, threading.Lock()) is None

    normalised = workers.MetadataWorker._normalise_results(
        {
            "metadata": "bad",
            "inventory": "bad",
            "curation": "bad",
            "version_diff": "bad",
            "versions": "bad",
            "history": [{"label": "Approve"}],
            "allowed": ["Approve"],
            "in_review": True,
        }
    )
    assert normalised["metadata"] == {}
    assert normalised["inventory"] == []
    assert normalised["inventory_failed"] is True
    assert normalised["curation"]["history"] == [{"label": "Approve"}]
    assert normalised["curation"]["allowed"] == ["Approve"]
    assert normalised["in_review"] is True


def test_detail_extras_cache_hit_and_guestbook(qapp: Any) -> None:
    from ui import workers as wm

    worker, _ = _detail()
    key = wm._inbox_key(worker._base_url, worker._pid, worker._api_token)
    wm._inbox_cache[key] = (float("inf"), [{"time": "cached"}])
    client = _Client(
        get_timestamps={"createTime": "2026-01-01"},
        find_review_submissions=lambda *_a: pytest.fail("cache hit must not call API"),
        get_guestbook={"id": 1},
        get_current_user={"displayName": "Curator"},
    )
    extra = worker._load_extras(client, {"id": 1, "guestbookId": 7}, ["v1"], True, False, {})
    assert extra["review_submissions"] == [{"time": "cached"}]
    assert extra["guestbook"] == {"id": 1}
    assert extra["account"] == {"displayName": "Curator"}
    assert extra["in_review"] is True
    wm._inbox_cache.pop(key, None)

    worker._base_url = "https://other.test"
    key2 = wm._inbox_key(worker._base_url, worker._pid, worker._api_token)
    wm._inbox_cache.pop(key2, None)
    client2 = _Client(
        get_timestamps=None,
        find_review_submissions=[{"time": "fresh"}],
        get_guestbook=lambda *_a: pytest.fail("no guestbook id"),
        get_current_user={},
    )
    extra2 = worker._load_extras(client2, {}, [], False, False, {})
    assert extra2["review_submissions"] == [{"time": "fresh"}]
    assert extra2["guestbook"] is None
    assert extra2["timestamps"] == {}
