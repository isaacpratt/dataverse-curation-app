"""Sensitivity & ethics review (dv-3c2): schema, completion, suggestions,
storage round-trip, and the Approve gate semantics."""

from engine.checks.base import CheckResult
from engine.report import DatasetReport, FileEntry
from sensitivity import (
    ANSWER_TOKENS,
    NO,
    QUESTION_IDS,
    QUESTIONS,
    YES,
    answered_count,
    is_complete,
    ruleset_requires,
    suggested_answers,
)
from storage import AppState


class TestSchema:
    def test_question_shape(self):
        for q in QUESTIONS:
            assert q["id"] and q["prompt"] and q["help"]
            assert q["type"] == "yes-no"
        assert QUESTION_IDS == (
            "human-subjects", "consent-irb", "identifiers",
            "indigenous-care", "restricted-terms",
        )

    def test_answer_tokens(self):
        assert ANSWER_TOKENS == ("", "yes", "no")


class TestCompletion:
    def test_incomplete_by_default(self):
        assert not is_complete(None)
        assert not is_complete({})
        assert not is_complete({"human-subjects": "yes"})

    def test_complete_when_all_answered(self):
        answers = {qid: "no" for qid in QUESTION_IDS}
        assert is_complete(answers)

    def test_blank_is_not_an_answer(self):
        answers = {qid: "no" for qid in QUESTION_IDS}
        answers["identifiers"] = ""
        assert not is_complete(answers)

    def test_answered_count(self):
        assert answered_count({}) == 0
        assert answered_count({qid: "yes" for qid in QUESTION_IDS}) == 5


class TestSuggestions:
    def test_no_data_no_machine_answers(self):
        s = suggested_answers(None, None)
        assert s["identifiers"] is None
        assert s["restricted-terms"] is None

    def test_clean_report_suggests_no_pii(self):
        report = DatasetReport(
            persistent_id="p", label="l", engine_version="t",
            files=[FileEntry(path="a.csv", size_bytes=1, mime_type="text/csv",
                             checks=[CheckResult("format.csv.content", "info", True, "ok")])],
        )
        s = suggested_answers(report, [])
        assert s["identifiers"] == NO

    def test_pii_finding_blocks_the_suggestion(self):
        report = DatasetReport(
            persistent_id="p", label="l", engine_version="t",
            files=[FileEntry(path="a.csv", size_bytes=1, mime_type="text/csv",
                             checks=[CheckResult("format.csv.pii", "warning", False, "2 emails")])],
        )
        s = suggested_answers(report, [])
        assert s["identifiers"] is None

    def test_restricted_files_block_the_terms_suggestion(self):
        s = suggested_answers(None, [{"path": "secret.csv", "restricted": True}])
        assert s["restricted-terms"] is None
        s2 = suggested_answers(None, [{"path": "open.csv"}])
        assert s2["restricted-terms"] == YES


class TestRulesetFlag:
    def test_flag_semantics(self):
        assert ruleset_requires({"requires_sensitivity": True})
        assert not ruleset_requires({"requires_sensitivity": False})
        assert not ruleset_requires({})
        assert not ruleset_requires(None)


class TestStorage:
    def test_round_trip_and_reopen(self, tmp_path):
        st = AppState(tmp_path / "state.db")
        assert st.get_sensitivity_review("pid") is None
        answers = {qid: "no" for qid in QUESTION_IDS}
        answers["human-subjects"] = "yes"
        st.set_sensitivity_review("pid", answers, note="checked with PI")
        got = st.get_sensitivity_review("pid")
        assert got["answers"]["human-subjects"] == "yes"
        assert got["note"] == "checked with PI"
        st.close()
        st2 = AppState(tmp_path / "state.db")
        got2 = st2.get_sensitivity_review("pid")
        assert got2["answers"]["identifiers"] == "no"
        st2.close()

    def test_upsert_replaces(self, tmp_path):
        st = AppState(tmp_path / "state.db")
        st.set_sensitivity_review("pid", {"human-subjects": "yes"})
        st.set_sensitivity_review("pid", {"identifiers": NO})
        got = st.get_sensitivity_review("pid")
        assert got["answers"] == {"identifiers": "no"}
        st.close()
