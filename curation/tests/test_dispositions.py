"""Finding dispositions (dv-32x): finding_key stability, storage round-trip, and the response-draft exclusion of "Won't fix" findings."""

from typing import Any

from curation.response_draft import (
    build_response,
    collect_filecheck_sections,
    collect_metadata_sections,
)
from curation.storage import (
    RESOLVED_DISPOSITIONS,
    AppState,
    finding_key,
)
from engine.checks.base import CheckResult
from engine.report import DatasetReport, FileEntry

# ---------------------------------------------------------------- keys


class TestFindingKey:
    def test_stable_across_whitespace(self):
        assert finding_key("format.csv.content", "a.csv", "mixed  delimiters") == (
            finding_key("format.csv.content", "a.csv", "mixed\tdelimiters\n")
        )

    def test_differs_by_path(self):
        assert finding_key("x", "a.csv", "m") != finding_key("x", "b.csv", "m")

    def test_differs_by_message_and_id(self):
        assert finding_key("x", "a.csv", "m") != finding_key("x", "a.csv", "n")
        assert finding_key("x", "a.csv", "m") != finding_key("y", "a.csv", "m")

    def test_metadata_rule_shape(self):
        """Rule findings use the rule id as check_id and requirement text."""
        key = finding_key("authorAffiliation", "", "McMaster — Recommended")
        assert key == finding_key("authorAffiliation", "", "McMaster — Recommended ")

    # The kit/storage token agreement is checked in ui/tests (it
    # legitimately imports the kit, the engine must stay Qt-free).


# ------------------------------------------------------------- storage


class TestStorageRoundTrip:
    def test_set_get_list(self, tmp_path):
        st = AppState(tmp_path / "state.db")
        key = finding_key("format.csv.pii", "a.csv", "2 emails")
        st.set_finding_disposition("pid", key, "wontfix", "contact person")
        got = st.get_finding_disposition("pid", key)
        assert got is not None
        assert got["disposition"] == "wontfix"
        assert got["note"] == "contact person"
        assert list(st.list_finding_dispositions("pid")) == [key]
        st.close()

    def test_overwrite(self, tmp_path):
        st = AppState(tmp_path / "state.db")
        key = finding_key("x", "", "m")
        st.set_finding_disposition("pid", key, "acknowledged", "")
        st.set_finding_disposition("pid", key, "blocked", "waiting on IRB")
        got = st.get_finding_disposition("pid", key)
        assert got is not None
        assert got["disposition"] == "blocked"
        assert got["note"] == "waiting on IRB"
        st.close()

    def test_unset_deletes(self, tmp_path):
        st = AppState(tmp_path / "state.db")
        key = finding_key("x", "", "m")
        st.set_finding_disposition("pid", key, "acknowledged")
        st.set_finding_disposition("pid", key, "")
        assert st.get_finding_disposition("pid", key) is None
        assert st.list_finding_dispositions("pid") == {}
        st.close()

    def test_persists_across_reopen(self, tmp_path):
        key = finding_key("x", "a.csv", "m")
        st = AppState(tmp_path / "state.db")
        st.set_finding_disposition("pid", key, "fix-requested", "needs UTF-8")
        st.close()
        st2 = AppState(tmp_path / "state.db")
        got = st2.get_finding_disposition("pid", key)
        assert got is not None
        assert got["disposition"] == "fix-requested"
        st2.close()

    def test_invalid_token_stored_as_clear(self, tmp_path):
        st = AppState(tmp_path / "state.db")
        key = finding_key("x", "", "m")
        st.set_finding_disposition("pid", key, "nonsense")
        assert st.get_finding_disposition("pid", key) is None
        st.close()

    def test_empty_key_is_noop(self, tmp_path):
        st = AppState(tmp_path / "state.db")
        st.set_finding_disposition("pid", "", "acknowledged")
        assert st.list_finding_dispositions("pid") == {}
        st.close()

    def test_resolved_set(self):
        assert frozenset({"acknowledged", "wontfix"}) == RESOLVED_DISPOSITIONS


# ------------------------------------------------------- response draft


def _report() -> DatasetReport:
    return DatasetReport(
        persistent_id="doi:10.5072/FK2/EXAMPLE",
        label="Example",
        engine_version="test",
        dataset_checks=[
            CheckResult(
                check_id="inventory.extensions",
                level="warning",
                passed=False,
                message="1 executable file",
            ),
        ],
        files=[
            FileEntry(
                path="a.csv",
                size_bytes=10,
                mime_type="text/csv",
                checks=[
                    CheckResult(
                        check_id="format.csv.pii",
                        level="warning",
                        passed=False,
                        message="2 emails found",
                    ),
                ],
            ),
        ],
    )


def _completeness() -> list[dict[str, Any]]:
    return [
        {
            "field": "Affiliation",
            "rule_id": "authorAffiliation",
            "requirement": "McMaster — Recommended",
            "value": "—",
            "status": "incomplete",
            "level": "required",
            "pending": False,
            "response_template": "",
        },
    ]


class TestResponseDraftExclusion:
    def test_sections_carry_finding_keys(self, tmp_path):
        sections = build_response({}, _completeness(), _report(), "", "")[1]
        keys = {s["finding_key"] for s in sections}
        assert finding_key("authorAffiliation", "", "McMaster — Recommended") in keys
        assert finding_key("format.csv.pii", "a.csv", "2 emails found") in keys
        assert finding_key("inventory.extensions", "", "1 executable file") in keys

    def test_wontfix_excluded_from_draft(self):
        disp = {
            finding_key("format.csv.pii", "a.csv", "2 emails found"): {
                "disposition": "wontfix",
                "note": "contact person",
            },
        }
        md, sections = build_response({}, _completeness(), _report(), "", "", dispositions=disp)
        assert "2 emails found" not in md
        by_key = {s["finding_key"]: s for s in sections}
        assert by_key[finding_key("format.csv.pii", "a.csv", "2 emails found")]["included"] is False
        # Other findings stay included.
        assert (
            by_key[finding_key("inventory.extensions", "", "1 executable file")]["included"] is True
        )

    def test_other_dispositions_stay_included(self):
        disp = {
            finding_key("inventory.extensions", "", "1 executable file"): {
                "disposition": "acknowledged",
                "note": "",
            },
        }
        md, _sections = build_response({}, _completeness(), _report(), "", "", dispositions=disp)
        assert "1 executable file" in md
        assert md.strip()  # draft still renders

    def test_collect_functions_accept_none(self):
        assert collect_metadata_sections({}, _completeness()) != []
        assert collect_filecheck_sections({}, _report()) != []

    def test_skipped_rows_emit_no_sections(self):
        rows = [
            *_completeness(),
            {
                "field": "Subject",
                "rule_id": "field:citation.subject",
                "requirement": "off",
                "value": "—",
                "status": "skipped",
                "level": "unchecked",
                "pending": False,
                "response_template": "",
            },
        ]
        sections = collect_metadata_sections({}, rows)
        assert [s["label"] for s in sections] == ["Affiliation"]
