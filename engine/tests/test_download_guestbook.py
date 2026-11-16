"""Guestbook-protected downloads: POST the answers, then stream the signed URL.

Dataverse answers a guestbook-protected bundle with HTTP 400 until the
guestbook is answered. The supported exchange is a POST to the access
endpoint carrying ``{"guestbookResponse": ...}``; the reply holds a signed
URL that streams the ZIP. These tests pin the wire format and the error path.
"""

import requests

from dataverse_client import DataverseClient

PID = "doi:10.80240/FK2/RZXIKC"


class _SignedUrlResponse:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None

    def close(self):
        return None


class _ErrorResponse:
    def __init__(self, status, message):
        self.status_code = status
        self._message = message

    def json(self):
        return {"status": "ERROR", "message": self._message}

    @property
    def text(self):
        import json

        return json.dumps({"status": "ERROR", "message": self._message})

    def raise_for_status(self):
        raise requests.HTTPError(response=self)

    def close(self):
        return None


class _ZipResponse:
    status_code = 200
    url = "http://example.test/signed"
    headers: dict = {}

    def __init__(self, payload=b"zipbytes"):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size):
        yield self._payload


class _FakeSession:
    def __init__(self, post_response, zip_response):
        self._post_response = post_response
        self._zip_response = zip_response
        self.posts: list[tuple[str, dict]] = []
        self.gets: list[tuple[str, dict]] = []

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        return self._post_response

    def get(self, url, **kwargs):
        self.gets.append((url, kwargs))
        return self._zip_response


def _client_with(session, token="token"):
    client = DataverseClient.__new__(DataverseClient)
    client._session = session
    client._api_token = token
    client._timeout = 5
    client._last_download_error = ""

    def _api(path):
        return "http://example.test" + path

    client._api = _api
    return client


def test_guestbook_response_is_posted_then_signed_url_streamed(tmp_path):
    signed = "http://example.test/api/access/dataset/11657?gbrecs=true&gbrids=99"
    session = _FakeSession(
        _SignedUrlResponse({"status": "OK", "data": {"signedUrl": signed}}),
        _ZipResponse(),
    )
    client = _client_with(session)
    answers = {
        "name": "Ada",
        "email": "ada@example.com",
        "institution": "McMaster",
        "position": "Librarian",
        "answers": [{"id": 22, "value": "yes"}],
    }
    dest = tmp_path / "bundle.zip.part"

    client.download_dataset_zip(PID, dest, guestbook_response=answers)

    assert dest.read_bytes() == b"zipbytes"
    url, kwargs = session.posts[0]
    assert url.endswith("/api/access/dataset/:persistentId")
    assert kwargs["params"] == {"persistentId": PID}
    assert kwargs["json"] == {"guestbookResponse": answers}
    assert kwargs["headers"]["X-Dataverse-key"] == "token"
    assert session.gets[0][0] == signed, "the signed URL, not the API path"


def test_rejected_guestbook_reports_the_server_reason(tmp_path):
    session = _FakeSession(_ErrorResponse(400, "Missing required fields: Position"), _ZipResponse())
    client = _client_with(session)

    try:
        client.download_dataset_zip(
            PID, tmp_path / "b.zip.part", guestbook_response={"answers": []}
        )
    except requests.HTTPError as exc:
        text = str(exc)
    else:  # pragma: no cover - the POST must fail
        raise AssertionError("a rejected guestbook must raise")

    assert "rejected the guestbook response" in text
    assert "Missing required fields: Position" in text
    assert not session.gets, "nothing streams when the guestbook is rejected"


def test_guestbook_response_needs_an_api_token(tmp_path):
    session = _FakeSession(
        _SignedUrlResponse({"data": {"signedUrl": "http://example.test/x"}}),
        _ZipResponse(),
    )
    client = _client_with(session, token="")

    try:
        client.download_dataset_zip(
            PID, tmp_path / "b.zip.part", guestbook_response={"name": "Ada"}
        )
    except requests.HTTPError as exc:
        text = str(exc)
    else:  # pragma: no cover - a token is mandatory
        raise AssertionError("no token must raise")

    assert "API token" in text
    assert not session.posts
