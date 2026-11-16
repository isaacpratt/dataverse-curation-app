"""P3 decision guardrails: consequence copy + commit gated until a real choice.

Promoted from probe35_p3_decision.py — the combo must start on its
placeholder (Commit disabled, helper explains the gate), show per-action
consequence copy once chosen, re-gate on return to the placeholder, and
survive an options refresh without losing the selection.
"""

import pytest


@pytest.fixture(scope="module")
def det(win, qapp):
    win._open_dataset("doi:10.5072/FK2/PROBE", "Probe dataset (tests)")
    detail = None
    for _ in range(100):
        qapp.processEvents()
        detail = getattr(win, "_detail", None)
        if detail is not None and getattr(detail, "_decision_combo", None) is not None:
            break
    assert detail is not None, "detail view did not open"
    assert detail._decision_combo is not None, "decision combo missing"
    return detail


def test_placeholder_gates_commit(det):
    combo, commit = det._decision_combo, det._commit_btn
    combo.setCurrentIndex(0)
    assert combo.currentData() is None
    assert not commit.isEnabled()
    text = det._decision_help.text()
    assert "disabled" in text
    assert "Pick an action" in text


def test_real_choice_enables_commit(det):
    combo, commit = det._decision_combo, det._commit_btn
    combo.setCurrentIndex(0)
    combo.setCurrentIndex(1)
    assert commit.isEnabled()
    assert "records" in det._decision_help.text().lower()


def test_consequence_copy_differs_per_action(det):
    combo, help_lbl = det._decision_combo, det._decision_help
    combo.setCurrentIndex(1)
    text1, first = help_lbl.text(), combo.currentText()
    combo.setCurrentIndex(2)
    assert combo.currentText() != first
    assert help_lbl.text() != text1


def test_returning_to_placeholder_regates(det):
    combo, commit = det._decision_combo, det._commit_btn
    combo.setCurrentIndex(0)
    gate = det._decision_help.text()
    combo.setCurrentIndex(2)
    combo.setCurrentIndex(0)
    assert not commit.isEnabled()
    assert det._decision_help.text() == gate


def test_option_refresh_keeps_selection_in_sync(det):
    combo, commit = det._decision_combo, det._commit_btn
    combo.setCurrentIndex(1)
    wanted, help1 = combo.currentText(), det._decision_help.text()
    det._refresh_decision_options()
    assert combo.currentText() == wanted
    assert commit.isEnabled()
    assert det._decision_help.text() == help1
    # Leave the shared window on its neutral state.
    combo.setCurrentIndex(0)
