"""Depositor follow-up tracking (dv-5eg) — pure logic + storage round-trip."""


import follow_ups as fu
from curation.storage import open_state


class TestRevisionDetection:
    def test_generic_revisions_label_matches(self):
        assert fu.is_revision_decision("Revisions requested")
        assert fu.is_revision_decision("Revisions Requested")

    def test_instance_labels_match_by_substring(self):
        assert fu.is_revision_decision("Needs revisions before publish")
        assert fu.is_revision_decision("Changes requested")

    def test_approval_and_other_states_do_not_match(self):
        assert not fu.is_revision_decision("Approve")
        assert not fu.is_revision_decision("Publish")
        assert not fu.is_revision_decision("Reject")
        assert not fu.is_revision_decision("")

    def test_configured_revision_label_matches_exactly(self):
        assert fu.is_revision_decision("Send back", revision_label="Send back")


class TestTimestampComparison:
    def test_z_suffixed_stamp_parses(self):
        assert fu.parse_ts("2026-10-14T12:30:00Z") is not None

    def test_newer_draft_is_detected(self):
        assert fu.newer_than("2026-10-20T09:00:00Z", "2026-10-14T12:30:00Z")

    def test_older_draft_is_not(self):
        assert not fu.newer_than("2026-10-01T09:00:00Z", "2026-10-14T12:30:00Z")

    def test_equal_stamps_are_not_newer(self):
        assert not fu.newer_than("2026-10-14T12:30:00Z", "2026-10-14T12:30:00Z")

    def test_tz_offsets_compare_in_utc(self):
        # 08:30 at +02:00 == 06:30 UTC, which is NOT newer than 07:00 UTC.
        assert not fu.newer_than("2026-10-14T08:30:00+02:00", "2026-10-14T07:00:00Z")
        assert fu.newer_than("2026-10-14T09:30:00+02:00", "2026-10-14T07:00:00Z")

    def test_naive_stamps_are_read_as_utc(self):
        assert fu.newer_than("2026-10-20 09:00:00", "2026-10-14T12:30:00Z")

    def test_garbage_or_missing_is_never_newer(self):
        assert not fu.newer_than("not a date", "2026-10-14T12:30:00Z")
        assert not fu.newer_than("2026-10-20T09:00:00Z", "")
        assert not fu.newer_than(None, None)


class TestStateFor:
    def test_awaiting_without_last_update(self):
        assert fu.state_for("2026-10-14T12:30:00Z") == fu.STATE_AWAITING

    def test_depositor_updated_when_draft_moved(self):
        assert (
            fu.state_for("2026-10-14T12:30:00Z", "2026-10-16T08:00:00Z")
            == fu.STATE_UPDATED
        )

    def test_awaiting_when_draft_is_older(self):
        assert (
            fu.state_for("2026-10-14T12:30:00Z", "2026-10-01T08:00:00Z")
            == fu.STATE_AWAITING
        )


class TestStorageRoundTrip:
    def test_open_and_close(self, tmp_path):
        st = open_state(tmp_path)
        try:
            st.open_follow_up("doi:1", decision_label="Revisions requested")
            row = st.get_follow_up("doi:1")
            assert row is not None
            assert row["opened_at"]
            assert row["state"] == fu.STATE_AWAITING
            # A different decision closes it.
            assert st.close_follow_up("doi:1") is True
            assert st.get_follow_up("doi:1") is None
            assert st.close_follow_up("doi:1") is False
        finally:
            st.close()

    def test_reopen_preserves_first_request_date(self, tmp_path):
        st = open_state(tmp_path)
        try:
            st.open_follow_up(
                "doi:2",
                decision_label="Revisions requested",
                opened_at="2026-09-01T00:00:00+00:00",
            )
            st.open_follow_up(
                "doi:2",
                decision_label="Revisions requested again",
                opened_at="2026-10-20T00:00:00+00:00",
            )
            row = st.get_follow_up("doi:2")
            assert row["opened_at"].startswith("2026-09-01")
            assert row["decision_label"] == "Revisions requested again"
        finally:
            st.close()

    def test_last_update_flips_state_to_updated(self, tmp_path):
        st = open_state(tmp_path)
        try:
            st.open_follow_up(
                "doi:3",
                decision_label="Revisions requested",
                opened_at="2026-10-14T12:00:00+00:00",
            )
            st.set_follow_up_last_update("doi:3", "2026-10-20T09:00:00Z")
            row = st.get_follow_up("doi:3")
            assert row["state"] == fu.STATE_UPDATED
            assert row["last_update"] == "2026-10-20T09:00:00Z"
            listing = st.list_follow_ups()
            assert listing["doi:3"]["state"] == fu.STATE_UPDATED
        finally:
            st.close()

    def test_nothing_open_lists_empty(self, tmp_path):
        st = open_state(tmp_path)
        try:
            assert st.list_follow_ups() == {}
        finally:
            st.close()
