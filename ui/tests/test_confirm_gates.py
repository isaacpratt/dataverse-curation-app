"""Confirmation gates: nothing remote happens before the curator says yes.

Two actions reach outside the app:

* committing an assessment whose decision came from the instance's
  curation labels also writes that label to Dataverse - the dataset
  changes on the server, for everyone;
* uninstalling an extension removes a package from the Python
  environment, which can silently switch off an optional check.

Both ask first, and the dialog's safe answer is the default (No).
"""

import pytest
from PySide6.QtWidgets import QDialog, QDialogButtonBox

from ui.i18n import t


@pytest.fixture(scope="module")
def detail(win, qapp):
    win._open_dataset("doi:10.5072/FK2/GATE", "Confirmation gate (tests)")
    det = None
    for _ in range(100):
        qapp.processEvents()
        det = getattr(win, "_detail", None)
        if det is not None and getattr(det, "_decision_combo", None) is not None:
            break
    assert det is not None, "detail view did not open"
    return det


@pytest.fixture
def quiet_commit(monkeypatch):
    """Silence the modal result dialogs a commit raises."""
    monkeypatch.setattr("ui.dataset_detail.show_info", lambda *a, **k: None)
    monkeypatch.setattr("ui.dataset_detail.show_warning", lambda *a, **k: None)
    monkeypatch.setattr("ui.dataset_detail.show_critical", lambda *a, **k: None)


def _choose_instance_label(detail, label="Approved"):
    """Point the decision combo at a label from the instance's own list."""
    detail._curation = {"allowed": [label, "Needs work"]}
    detail._refresh_decision_options()
    combo = detail._decision_combo
    combo.setCurrentIndex(combo.findText(label))
    assert combo.currentData() == label
    return label


def test_commit_asks_before_writing_to_dataverse(detail, monkeypatch):
    """A remote write asks first."""
    label = _choose_instance_label(detail)
    asked: list[str] = []

    def _confirm(decision):
        asked.append(decision)
        return False

    monkeypatch.setattr(detail, "_confirm_remote_write", _confirm)
    detail._on_commit()
    assert asked == [label], "the gate must ask before the write"


def test_declining_writes_nothing_and_logs_nothing(detail, monkeypatch, quiet_commit):
    """No means no: no log entry, no workflow step, no push."""
    _choose_instance_label(detail)
    monkeypatch.setattr(detail, "_confirm_remote_write", lambda _decision: False)
    logged: list = []
    monkeypatch.setattr(detail, "_log_action", lambda *a, **k: logged.append(a))
    pushed: list = []

    def _fake_set_label(pid, label):
        pushed.append((pid, label))
        return True

    monkeypatch.setattr(detail._client, "set_curation_label", _fake_set_label)
    detail._decision_committed = False
    try:
        detail._on_commit()
    finally:
        detail._decision_committed = False
    assert not pushed, "nothing may be written before the curator confirms"
    assert not logged, "nothing may be logged before the curator confirms"
    assert detail._decision_committed is False, (
        "the workflow must not record a decision that was not confirmed"
    )


def test_confirming_writes_logs_and_closes_the_step(detail, monkeypatch, quiet_commit):
    """Yes means yes: the label is pushed, the decision is logged."""
    label = _choose_instance_label(detail)
    monkeypatch.setattr(detail, "_confirm_remote_write", lambda _decision: True)
    logged: list = []
    monkeypatch.setattr(detail, "_log_action", lambda *a, **k: logged.append(a))
    pushed: list = []

    def _fake_set_label(pid, value):
        pushed.append((pid, value))
        return True

    monkeypatch.setattr(detail._client, "set_curation_label", _fake_set_label)
    detail._decision_committed = False
    try:
        detail._on_commit()
        assert pushed == [(detail._pid, label)], "the confirmed label must be pushed"
        assert logged, "a confirmed decision is recorded in the dataset log"
        assert detail._decision_committed is True
    finally:
        detail._decision_committed = False


def test_a_local_only_decision_asks_nothing(detail, monkeypatch, quiet_commit):
    """A decision that is not a Dataverse label stays a one-click action."""
    detail._curation = {}
    detail._refresh_decision_options()
    combo = detail._decision_combo
    combo.setCurrentIndex(1)
    assert combo.currentData()
    asked: list = []

    def _fake_confirm(decision):
        asked.append(decision)
        return True

    monkeypatch.setattr(detail, "_confirm_remote_write", _fake_confirm)
    monkeypatch.setattr(detail, "_log_action", lambda *a, **k: None)
    monkeypatch.setattr(detail._client, "set_curation_label", lambda pid, label: True)
    detail._on_commit()
    assert not asked, "a local-only decision must not raise a remote-write gate"


def test_confirm_dialog_defaults_to_no_and_is_themed(qapp, monkeypatch):
    """The safe answer is the default, and the buttons wear the kit's roles."""
    from ui.dialogs import confirm

    captured: dict = {}

    def _fake_exec(self):
        captured["dialog"] = self
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(QDialog, "exec", _fake_exec)
    assert confirm(None, t("detail.decision.title"), "Body") is False
    box = captured["dialog"].findChild(QDialogButtonBox)
    assert box is not None, "the dialog must carry a button box"
    no_btn = box.button(QDialogButtonBox.StandardButton.No)
    assert no_btn is not None
    assert no_btn.isDefault(), "No must be the default answer"
    assert no_btn.objectName() == "SecondaryButton"
    yes_btn = next(b for b in box.buttons() if b is not no_btn)
    assert yes_btn.objectName() == "PrimaryButton", (
        "the affirmative button must wear the brand face"
    )


def test_uninstall_asks_before_removing_a_package(win, monkeypatch):
    """Uninstalling an extension asks first."""
    pane = win._ensure_settings()
    asked: list = []

    def _fake_confirm(parent, title, text, **kwargs):
        asked.append(title)
        return False

    monkeypatch.setattr("ui.settings_dialog.confirm", _fake_confirm)
    ran: list = []
    monkeypatch.setattr(pane, "_run_shell", lambda fn, status: ran.append(status))
    pane._uninstall_package("Pillow")
    assert asked, "uninstall must ask first"
    assert not ran, "nothing may be removed before the curator confirms"


def test_confirmed_uninstall_runs(win, monkeypatch):
    """A confirmed uninstall goes ahead."""
    pane = win._ensure_settings()
    monkeypatch.setattr(
        "ui.settings_dialog.confirm",
        lambda parent, title, text, **kwargs: True,
    )
    ran: list = []
    monkeypatch.setattr(pane, "_run_shell", lambda fn, status: ran.append(status))
    pane._uninstall_package("Pillow")
    assert ran, "a confirmed uninstall must run"
