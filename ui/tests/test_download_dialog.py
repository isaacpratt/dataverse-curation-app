"""Download window renders guestbook fields and returns the POST body."""

from typing import Any

from PySide6.QtWidgets import QComboBox, QDialog

from curation.download_manager import DownloadQuote
from ui.download_dialog import DownloadApprovalDialog

GUESTBOOK = {
    "id": 24,
    "name": "Test guestbook 2",
    "enabled": True,
    "nameRequired": True,
    "emailRequired": True,
    "institutionRequired": True,
    "positionRequired": True,
    "customQuestions": [
        {
            "id": 22,
            "question": "are you reasonable?",
            "required": True,
            "type": "options",
            "optionValues": [
                {"id": 31, "value": "no"},
                {"id": 30, "value": "yes"},
            ],
        }
    ],
}

ACCOUNT = {
    "firstName": "Ada",
    "lastName": "Lovelace",
    "email": "ada@example.com",
    "affiliation": "McMaster University",
    "position": "Librarian",
}


def _quote() -> Any:
    return DownloadQuote("doi:10.80240/FK2/RZXIKC", 2, 1024)


def test_dialog_without_guestbook_has_no_form(qapp):
    dlg = DownloadApprovalDialog(_quote())
    assert dlg.guestbook_response() is None
    assert not dlg._base_inputs


def test_account_details_prefill_and_guestbook_fields_become_a_response(qapp):
    dlg = DownloadApprovalDialog(_quote(), guestbook=GUESTBOOK, account=ACCOUNT)
    assert set(dlg._base_inputs) == {"name", "email", "institution", "position"}
    assert dlg._base_inputs["name"].text() == "Ada Lovelace"
    assert dlg._base_inputs["position"].text() == "Librarian"
    dlg._base_inputs["email"].setText("ada@example.org")
    question, widget = dlg._question_inputs[0]
    assert isinstance(widget, QComboBox)
    assert question["id"] == 22
    widget.setCurrentIndex(2)  # "yes" (index 0 is the blank prompt)

    response = dlg.guestbook_response()

    assert response == {
        "name": "Ada Lovelace",
        "email": "ada@example.org",
        "institution": "McMaster University",
        "position": "Librarian",
        "answers": [{"id": 22, "value": "yes"}],
    }


def test_required_question_blocks_accept_until_answered(qapp):
    dlg = DownloadApprovalDialog(_quote(), guestbook=GUESTBOOK, account=ACCOUNT)
    dlg.accept()
    assert dlg.result() != QDialog.DialogCode.Accepted
    assert "are you reasonable?" in dlg._error.text()

    _, widget = dlg._question_inputs[0]
    assert isinstance(widget, QComboBox)
    widget.setCurrentIndex(1)
    dlg.accept()
    assert dlg.result() == QDialog.DialogCode.Accepted


def test_missing_required_account_field_blocks_accept(qapp):
    # This account has no Position, and the guestbook requires it — this is
    # exactly what Dataverse rejects, so the window must ask for it first.
    account = dict(ACCOUNT)
    account["position"] = ""
    dlg = DownloadApprovalDialog(_quote(), guestbook=GUESTBOOK, account=account)
    _, widget = dlg._question_inputs[0]
    assert isinstance(widget, QComboBox)
    widget.setCurrentIndex(1)

    dlg.accept()
    assert dlg.result() != QDialog.DialogCode.Accepted
    assert "Position" in dlg._error.text()
