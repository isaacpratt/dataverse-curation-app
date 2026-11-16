"""Bundle-download error reporting (guestbook vs. a genuinely missing dataset).

Dataverse refuses guestbook-protected datasets with HTTP 400 ("You may not
download this file without the required Guestbook response ..."). That was
previously mistaken for a missing version, retried three times, and reported
as "Dataset bundle download not available (404)" — which sent curators to the
Base URL setting instead of the guestbook. These tests pin the real error.
"""

import requests

from dataverse_client import DataverseClient, GuestbookRequired


class _ErrorResponse:
    def __init__(self, status, message, url="http://example.test/zip"):
        self.status_code = status
        self._message = message
        self.url = url
        self.headers: dict = {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def json(self):
        return {"status": "ERROR", "message": self._message}

    @property
    def text(self):
        import json

        return json.dumps({"status": "ERROR", "message": self._message})

    def raise_for_status(self):
        raise requests.HTTPError(response=self)

    def iter_content(self, chunk_size):
        yield b""


class _FakeSession:
    def __init__(self, response):
        self.calls = 0
        self._response = response

    def get(self, url, **kwargs):
        self.calls += 1
        return self._response


def _client_with(session):
    client = DataverseClient.__new__(DataverseClient)
    client._session = session
    client._api_token = None
    client._timeout = 5
    client._last_download_error = ""

    def _api(path):
        return "http://example.test" + path

    client._api = _api
    return client


def test_guestbook_blocked_bundle_raises_actionable_error(tmp_path):
    message = (
        "You may not download this file without the required Guestbook response for guestbookID 24."
    )
    session = _FakeSession(_ErrorResponse(400, message))
    client = _client_with(session)

    try:
        client.download_dataset_zip("doi:10.80240/FK2/RZXIKC", tmp_path / "b.zip.part")
    except GuestbookRequired as exc:
        text = str(exc)
    else:  # pragma: no cover - the call must fail
        raise AssertionError("guestbook refusal must raise GuestbookRequired")

    assert message in text
    assert "guestbook" in text.lower()
    assert "404" not in text, "a guestbook refusal is not a not-found error"
    assert session.calls == 1, "no version retries can satisfy a guestbook"


def test_missing_dataset_reports_server_message_instead_of_bogus_404(tmp_path):
    message = "Could not find requested dataset."
    session = _FakeSession(_ErrorResponse(400, message))
    client = _client_with(session)

    try:
        client.download_dataset_zip("doi:10.5072/FK2/MISSING", tmp_path / "b.zip.part")
    except requests.HTTPError as exc:
        text = str(exc)
    else:  # pragma: no cover - the call must fail
        raise AssertionError("missing dataset must raise HTTPError")

    assert message in text
    assert "HTTP 400" in text
    assert "404" not in text
    assert session.calls == 3, "draft, latest and unversioned are all attempted"
