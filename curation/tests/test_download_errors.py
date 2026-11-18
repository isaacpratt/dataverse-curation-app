"""Bundle-download error reporting (guestbook vs. a genuinely missing dataset).

Dataverse refuses guestbook-protected datasets with HTTP 400 ("You may not
download this file without the required Guestbook response ..."). That was
previously mistaken for a missing version, retried three times, and reported
as "Dataset bundle download not available (404)" — which sent curators to the
Base URL setting instead of the guestbook. These tests pin the real error.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any, Literal

import requests

from curation.client import DataverseClient, GuestbookRequired


class _ErrorResponse:
    def __init__(self, status: int, message: str, url: str = "http://example.test/zip") -> None:
        self.status_code = status
        self._message = message
        self.url = url
        self.headers: dict[str, str] = {}

    def __enter__(self) -> "_ErrorResponse":
        return self

    def __exit__(self, *exc: Any) -> Literal[False]:
        return False

    def json(self) -> dict[str, str]:
        return {"status": "ERROR", "message": self._message}

    @property
    def text(self) -> str:
        import json

        return json.dumps({"status": "ERROR", "message": self._message})

    def raise_for_status(self) -> None:
        raise requests.HTTPError(response=self)

    def iter_content(self, chunk_size: int) -> Iterator[bytes]:
        yield b""


class _FakeSession:
    def __init__(self, response: Any) -> None:
        self.calls = 0
        self._response = response

    def get(self, url: str, **kwargs: Any) -> Any:
        self.calls += 1
        return self._response


def _client_with(session: Any) -> DataverseClient:
    client = DataverseClient.__new__(DataverseClient)
    client._session = session
    client._api_token = ""
    client._timeout = 5
    client._last_download_error = ""

    def _api(path: str) -> str:
        return "http://example.test" + path

    client._api = _api  # type: ignore[method-assign]
    return client


def test_guestbook_blocked_bundle_raises_actionable_error(tmp_path: Path) -> None:
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


def test_missing_dataset_reports_server_message_instead_of_bogus_404(tmp_path: Path) -> None:
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
