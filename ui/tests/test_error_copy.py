"""Error-copy mapping: a guestbook refusal must not blame the Base URL."""

from ui.dialogs import describe_error


def test_guestbook_error_gets_guestbook_headline():
    headline, details = describe_error(
        "You may not download this file without the required Guestbook "
        "response for guestbookID 24. Answer the guestbook on the dataset's "
        "Dataverse page (or remove it from the dataset) and try again."
    )
    assert "Guestbook" in headline
    assert "URL or collection" not in headline
    assert "guestbookID 24" in details
