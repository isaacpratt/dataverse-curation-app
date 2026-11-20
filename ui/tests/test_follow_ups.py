"""Depositor follow-up UI surface (dv-5eg): queue cell + detail banner."""

from typing import Any

import pytest


class TestFollowUpCellText:
    def _cell(self, ds: Any):
        from ui.dashboard import DashboardView

        pane = DashboardView.__new__(DashboardView)
        return DashboardView._cell_text(pane, ds, "follow_up")

    def test_empty_when_no_follow_up(self):
        assert self._cell({}) == ""
        assert self._cell({"follow_up": None}) == ""
        assert self._cell({"follow_up": {}}) == ""

    def test_awaiting_shows_since_date(self):
        ds = {
            "follow_up": {
                "state": "awaiting_depositor",
                "opened_at": "2026-10-14T12:00:00+00:00",
            }
        }
        cell = self._cell(ds)
        assert "2026-10-14" in cell
        assert "Awaiting" in cell

    def test_updated_shows_rerun_prompt(self):
        ds = {
            "follow_up": {
                "state": "depositor_updated",
                "opened_at": "2026-10-14T12:00:00+00:00",
            }
        }
        cell = self._cell(ds)
        assert "updated" in cell.lower()
        assert "re-run" in cell.lower()


class TestAttachFollowUps:
    def test_stamps_state_and_recomputes_from_draft(self):
        from ui.dashboard import attach_follow_ups

        datasets: list[dict[str, Any]] = [
            {"persistent_id": "doi:1"},
            {"persistent_id": "doi:2", "draft_updated_at": "2026-10-20T09:00:00Z"},
            {"persistent_id": "doi:3"},
        ]
        follow_ups = {
            "doi:1": {
                "opened_at": "2026-10-14T00:00:00Z",
                "state": "awaiting_depositor",
                "decision_label": "Rev",
            },
            "doi:2": {
                "opened_at": "2026-10-14T00:00:00Z",
                "state": "awaiting_depositor",
                "decision_label": "Rev",
            },
        }
        attach_follow_ups(datasets, follow_ups)
        assert datasets[0]["follow_up"]["state"] == "awaiting_depositor"
        # Draft lastUpdateTime newer than the request flips to updated.
        assert datasets[1]["follow_up"]["state"] == "depositor_updated"
        # No follow-up row: key removed so a stale stamp cannot survive.
        assert "follow_up" not in datasets[2]

    def test_empty_follow_ups_clears_stale_stamps(self):
        from ui.dashboard import attach_follow_ups

        datasets = [
            {
                "persistent_id": "doi:1",
                "follow_up": {"state": "awaiting_depositor"},
            }
        ]
        attach_follow_ups(datasets, {})
        assert "follow_up" not in datasets[0]


@pytest.fixture
def view(qapp, tmp_path):
    """Create a bare detail view with a real workspace for the follow-up banner."""
    from curation.config import Config
    from ui.dataset import DatasetDetailView

    try:
        cfg = Config.load(None)
    except Exception:
        cfg = Config()
    cfg.app.workspace = tmp_path

    v = DatasetDetailView.__new__(DatasetDetailView)
    v._pid = "doi:follow-up"
    v._config = cfg
    v._timestamps = {}
    v._logged = []

    class _StubDl:
        def dataset_dir(self, pid):
            return tmp_path / "dataset"

    v._dl_mgr = _StubDl()  # type: ignore[assignment]
    v._set_status = lambda msg, **_kw: None  # type: ignore[method-assign]
    v._state = lambda: __import__("curation.storage", fromlist=["x"]).open_state(cfg.app.workspace)  # type: ignore[method-assign]

    def _log(action, notes="", details=None):
        v._logged.append((action, notes, details))

    v._log_action = _log  # type: ignore[method-assign]

    # The banner is built through the real builder so the widget tree is the
    # one the app ships.
    v._follow_up_card = v._build_follow_up_card()
    return v


class TestFollowUpBanner:
    def test_banner_hidden_without_follow_up(self, view):
        view._refresh_follow_up()
        assert view._follow_up_card.isHidden()

    def test_banner_visible_for_open_follow_up(self, view):
        st = view._state()
        try:
            st.open_follow_up(
                view._pid,
                decision_label="Revisions requested",
                opened_at="2026-10-14T12:00:00+00:00",
            )
        finally:
            st.close()
        view._timestamps = {"lastUpdateTime": "2026-10-01T00:00:00Z"}
        view._refresh_follow_up()
        assert not view._follow_up_card.isHidden()
        assert "awaiting" in view._follow_up_label.text().lower()
        assert view._follow_up_checks_btn.isHidden()

    def test_banner_flips_to_updated_when_draft_moved(self, view):
        st = view._state()
        try:
            st.open_follow_up(
                view._pid,
                decision_label="Revisions requested",
                opened_at="2026-10-14T12:00:00+00:00",
            )
        finally:
            st.close()
        view._timestamps = {"lastUpdateTime": "2026-10-20T09:00:00Z"}
        view._refresh_follow_up()
        assert not view._follow_up_card.isHidden()
        assert "updated" in view._follow_up_label.text().lower()
        assert not view._follow_up_checks_btn.isHidden()

    def test_revisions_decision_opens_and_other_closes(self, view):
        view._timestamps = {}
        view._sync_follow_up("Revisions requested")
        st = view._state()
        try:
            assert st.get_follow_up(view._pid) is not None
        finally:
            st.close()
        assert any(a == "follow_up_opened" for a, _n, _d in view._logged)
        view._sync_follow_up("Approve")
        st = view._state()
        try:
            assert st.get_follow_up(view._pid) is None
        finally:
            st.close()
        assert any(a == "follow_up_closed" for a, _n, _d in view._logged)
