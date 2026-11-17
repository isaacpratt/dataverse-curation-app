"""Shared human_size helper + metric-card tap filters (dv-005, dv-896).

The GB/TB boundary case moved here from engine/tests/ (dv-hcg.26): it
asserts something about the four view modules, so it belongs with the
UI tests rather than in the Qt-free engine suite.
"""

from ui.widgets import human_size


def test_human_size_decimal_boundaries():
    assert human_size(0) == "0 B"
    assert human_size(512) == "512 B"
    assert human_size(999) == "999 B"
    assert human_size(1000) == "1.0 KB"
    assert "KB" in human_size(2048)
    assert "MB" in human_size(5 * 1000 * 1000)
    assert "GB" in human_size(3 * 1000**3)
    assert "TB" in human_size(2 * 1000**4)


def test_human_size_all_call_sites_share():
    from ui.checks_tree import _human_size as checks_size
    from ui.dashboard import _human_size as dash_size
    from ui.dataset.helpers import _human_size as detail_size
    from ui.download_dialog import _human_size as dl_size
    from ui.settings_dialog import SettingsPane

    for fn in (checks_size, dash_size, detail_size, dl_size):
        assert fn(1000) == "1.0 KB"
        assert fn(512) == "512 B"
    assert SettingsPane._humanize_bytes(2048) == human_size(2048)


def test_human_size_gb_and_tb():
    from ui.checks_tree import _human_size as checks_size
    from ui.dashboard import _human_size as dash_size
    from ui.dataset.helpers import _human_size as detail_size
    from ui.download_dialog import _human_size as dl_size

    for fn in (checks_size, dash_size, detail_size, dl_size):
        assert fn(512) == "512 B"
        assert "KB" in fn(2048)
        assert "MB" in fn(5 * 1000 * 1000)
        assert "GB" in fn(3 * 1000**3)
        assert "TB" in fn(2 * 1000**4)
    # All four are the same shared helper (dv-005).
    assert checks_size is dash_size or checks_size(2048) == dash_size(2048)
    for fn in (checks_size, dash_size, detail_size, dl_size):
        assert fn(999) == "999 B"
        assert fn(1000).startswith("1.0 KB")


def test_pending_filter_is_draft_plus_in_review(win, monkeypatch):
    dash = win._dashboard
    dash._all_datasets = [
        {"title": "a", "persistent_id": "p1", "state": "DRAFT"},
        {"title": "b", "persistent_id": "p2", "state": "IN REVIEW"},
        {"title": "c", "persistent_id": "p3", "state": "RELEASED"},
        {"title": "d", "persistent_id": "p4", "state": "DEACCESSIONED"},
    ]
    # Pending index (second entry after All).
    dash._state_filter.setCurrentIndex(1)
    dash._apply_filter()
    assert {d["persistent_id"] for d in dash._datasets} == {"p1", "p2"}


def test_metric_card_taps_apply_filters(win, monkeypatch):
    dash = win._dashboard
    dash._all_datasets = [
        {"title": "a", "persistent_id": "p1", "state": "DRAFT"},
        {"title": "b", "persistent_id": "p2", "state": "IN REVIEW"},
        {"title": "c", "persistent_id": "p3", "state": "RELEASED"},
    ]
    dash._on_metric_clicked("tertiary")
    assert {d["persistent_id"] for d in dash._datasets} == {"p1", "p2"}
    dash._on_metric_clicked("primary")
    assert {d["persistent_id"] for d in dash._datasets} == {"p2"}
