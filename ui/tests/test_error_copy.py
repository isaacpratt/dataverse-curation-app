"""Error-copy mapping: a guestbook refusal must not blame the Base URL."""

from ui.dialogs import describe_error


def test_guestbook_error_gets_guestbook_headline():
    headline, details = describe_error(
        "You may not download this file without the required Guestbook "
        "response for guestbookID 24. Reload the dataset metadata so the "
        "download window can show the guestbook fields, then try again."
    )
    assert "Guestbook" in headline
    assert "URL or collection" not in headline
    assert "guestbookID 24" in details


def test_rejected_guestbook_answers_get_a_correction_headline():
    headline, _ = describe_error(
        "Dataverse rejected the guestbook response: Guestbook Response entry "
        "is required but not present (Position)."
    )
    assert "guestbook answers" in headline.lower()
