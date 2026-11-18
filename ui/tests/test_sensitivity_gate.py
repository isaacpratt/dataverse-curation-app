"""Sensitivity gate (dv-3c2): the card renders, suggestions prefill, answers persist, and the Approve gate follows the ruleset flag."""

import pytest


@pytest.fixture
def view(qapp, tmp_path):
    """Create a bare DatasetDetailView wired to a throwaway workspace."""
    from curation.config import Config
    from ui.dataset import DatasetDetailView

    try:
        cfg = Config.load(None)
    except Exception:
        cfg = Config()
    cfg.app.workspace = tmp_path
    v = DatasetDetailView.__new__(DatasetDetailView)
    v._pid = "doi:10.5072/FK2/GATE"
    v._config = cfg
    v._ruleset = {}
    v._report = None
    v._inventory = []
    v._sensitivity_answers = {}
    v._logged = []
    v._state = lambda: __import__("curation.storage", fromlist=["x"]).open_state(cfg.app.workspace)  # type: ignore[method-assign]

    def _log(action, notes="", details=None):
        v._logged.append((action, notes))

    v._log_action = _log  # type: ignore[method-assign]
    v._refresh_dataset_log = lambda: None  # type: ignore[method-assign]
    return v


def test_card_renders_five_questions(view):
    from PySide6.QtWidgets import QComboBox

    view._inventory = None  # access picture unknown: no machine suggestions
    card = view._build_sensitivity_card()
    combos = card.findChildren(QComboBox)
    assert len(combos) == 5
    assert all(c.currentData() == "" for c in combos)
    assert "0 of 5 questions answered" in view._sensitivity_status.text()


def test_suggestions_prefill_with_data(view):
    from PySide6.QtWidgets import QComboBox

    from engine.checks.base import CheckResult
    from engine.report import DatasetReport, FileEntry

    view._report = DatasetReport(
        persistent_id="p",
        label="l",
        engine_version="t",
        files=[
            FileEntry(
                path="a.csv",
                size_bytes=1,
                mime_type="text/csv",
                checks=[CheckResult("format.csv.content", "info", True, "ok")],
            )
        ],
    )
    view._inventory = [{"path": "a.csv"}]
    card = view._build_sensitivity_card()
    combos = card.findChildren(QComboBox)
    by_qid = dict(view._sensitivity_combos.items())
    # Machine-known answers prefill; the human ones stay unanswered.
    assert by_qid["identifiers"].currentData() == "no"
    assert by_qid["restricted-terms"].currentData() == "yes"
    assert by_qid["human-subjects"].currentData() == ""
    assert "2 of 5 questions answered" in view._sensitivity_status.text()
    del combos


def test_answer_persists_and_logs(view, qapp):

    card = view._build_sensitivity_card()
    qapp.processEvents()
    combo = view._sensitivity_combos["human-subjects"]
    combo.setCurrentIndex(1)  # yes
    qapp.processEvents()
    stored = view._state().get_sensitivity_review(view._pid)
    assert stored["answers"]["human-subjects"] == "yes"
    assert any(a == "sensitivity_reviewed" for a, _n in view._logged)
    # The empty inventory prefilled restricted-terms = yes, so this answer
    # makes 2 of 5.
    assert "2 of 5 questions answered" in view._sensitivity_status.text()
    del card


class TestApproveGate:
    def test_gate_off_without_flag(self, view):
        view._sensitivity_answers = {}
        blocked, _msg = view._sensitivity_blocks()
        assert blocked is False

    def test_gate_blocks_incomplete(self, view):
        view._ruleset = {"requires_sensitivity": True}
        blocked, msg = view._sensitivity_blocks()
        assert blocked is True
        assert "0 of 5" in msg

    def test_gate_passes_complete(self, view):
        from curation.sensitivity import QUESTION_IDS

        view._ruleset = {"requires_sensitivity": True}
        view._sensitivity_answers = dict.fromkeys(QUESTION_IDS, "no")
        blocked, _msg = view._sensitivity_blocks()
        assert blocked is False
