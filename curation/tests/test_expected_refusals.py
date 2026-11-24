"""Expected API refusals: classified, logged as EXPECTED, never as bugs.

Dataverse answers some requests with a 4xx by design — a draft this
account may not read, a dataset with no published version, a curation
status that only exists for datasets under curation. Those answers are
the server's documented reply, so the app keeps the raw call and the raw
response and only says EXPECTED instead of ERROR. A status that is NOT
an expected answer (500, a bad request, a wrong path) stays an ERROR.
"""

import json
from typing import Any

import pytest
import requests

import curation.applog as applog
from curation.client import (
    DataverseClient,
    expected_api_reason,
    probe_skip_reason,
    refusal_code,
    version_probe_order,
)

_DRAFT_PATH = "/api/datasets/:persistentId/versions/:draft"
_PUBLISHED_PATH = "/api/datasets/:persistentId/versions/:latest-published"
_CURATION_PATH = "/api/datasets/:persistentId/curationStatus"


class _Response:
    """A minimal stand-in for a requests response."""

    def __init__(self, status: int, message: str = "", url: str = "http://example.test/x"):
        self.status_code = int(status)
        self._message = str(message)
        self.url = url
        self.headers: dict[str, Any] = {}
        self.content = b""

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    @property
    def text(self) -> str:
        return json.dumps({"status": "ERROR", "message": self._message})

    def json(self):
        return json.loads(self.text)

    def raise_for_status(self):
        if not self.ok:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)


class _Session:
    def __init__(self, response: Any) -> None:
        self._response = response
        self.calls: list[str] = []

    def get(self, url: str, **kwargs: Any) -> Any:
        self.calls.append(url)
        return self._response


def _client(response) -> DataverseClient:
    client = DataverseClient("https://example.test", "token")
    client._session = _Session(response)  # type: ignore[assignment]
    return client


@pytest.fixture(autouse=True)
def _clear_log():
    applog.clear()
    yield
    applog.clear()


def _log_text() -> str:
    return "\n".join(applog.lines())


# -- the classifier ---------------------------------------------------------


def test_draft_refusal_is_classified_as_expected():
    reason = expected_api_reason(_DRAFT_PATH, 401)
    assert reason
    assert refusal_code(_DRAFT_PATH, 401) == "draft_not_readable"


def test_published_version_refusal_is_classified_as_expected():
    assert refusal_code(_PUBLISHED_PATH, 404) == "no_published_version"
    assert expected_api_reason(_PUBLISHED_PATH, 404)


def test_curation_status_refusal_is_classified_as_expected():
    assert refusal_code(_CURATION_PATH, 403) == "not_under_curation"


def test_unexpected_statuses_are_not_classified():
    assert expected_api_reason(_DRAFT_PATH, 500) == ""
    assert expected_api_reason(_DRAFT_PATH, 400) == ""
    assert expected_api_reason("/api/datasets/:persistentId", 404) == ""
    assert expected_api_reason("/api/search", 401) == ""


# -- the log ----------------------------------------------------------------


def test_expected_refusal_is_logged_with_the_raw_call_and_response():
    client = _client(_Response(401, "User @pratti is not permitted to perform requested action."))
    with pytest.raises(requests.HTTPError):
        client._get_json(_DRAFT_PATH, params={"persistentId": "doi:10.5072/FK2/A"})
    text = _log_text()
    # The true call and the true response are kept verbatim.
    assert "GET http://example.test" in text
    assert "401" in text
    assert "User @pratti is not permitted" in text
    # ... and the refusal is marked as the server's expected answer.
    assert "EXPECTED" in text
    assert "ERROR:" not in text


def test_expected_refusal_context_is_added_to_the_call_line():
    client = _client(_Response(404, "Dataset version :latest-published of dataset 1 not found"))
    with pytest.raises(requests.HTTPError):
        client._get_json(_PUBLISHED_PATH, params={"persistentId": "doi:10.5072/FK2/A"})
    text = _log_text()
    assert "→ 404" in text
    assert "EXPECTED:" in text


def test_curation_status_refusal_is_reported_to_the_caller():
    client = _client(
        _Response(403, "You are not permitted to view the curation status of this dataset.")
    )
    refusal: dict[str, Any] = {}
    assert client.get_curation_status("doi:10.5072/FK2/A", refusal=refusal) is None
    assert refusal["status"] == 403
    assert refusal["code"] == "not_under_curation"
    assert "not permitted" in refusal["detail"]


def test_server_error_is_still_logged_as_an_error():
    client = _client(_Response(500, "Internal server error"))
    with pytest.raises(requests.HTTPError):
        client._get_json(_DRAFT_PATH, params={"persistentId": "doi:10.5072/FK2/A"})
    text = _log_text()
    assert "ERROR" in text
    assert "EXPECTED" not in text


def test_bad_request_is_still_logged_as_an_error():
    client = _client(_Response(400, "Bad request"))
    with pytest.raises(requests.HTTPError):
        client._get_json(_DRAFT_PATH, params={"persistentId": "doi:10.5072/FK2/A"})
    text = _log_text()
    assert "ERROR" in text
    assert "EXPECTED" not in text


# -- the probe order --------------------------------------------------------


def test_probe_order_uses_the_search_state():
    draft = {"state": "DRAFT", "has_draft": True}
    review = {"state": "In Review", "has_draft": True}
    published = {"state": "RELEASED", "has_draft": False}
    deaccessioned = {"state": "DEACCESSIONED", "has_draft": False}
    unknown = {"state": "", "has_draft": False}

    # A row under curation is probed at :draft — the only version a
    # curator cares about, and the only one the search payload proves
    # can exist.
    assert version_probe_order(draft) == [":draft"]
    assert version_probe_order(review) == [":draft"]
    # Every other row is read once, without a version probe: the dataset
    # read answers with the version the account may see. A :draft probe
    # on a published dataset is answered "not permitted" every time.
    assert version_probe_order(published) == []
    assert version_probe_order(deaccessioned) == []
    assert version_probe_order(unknown) == []


def test_probe_skip_reason_explains_the_skip():
    published = {"state": "RELEASED", "has_draft": False}
    assert "no draft" in probe_skip_reason(published)
    deaccessioned = {"state": "DEACCESSIONED", "has_draft": False}
    assert "deaccessioned" in probe_skip_reason(deaccessioned)
    draft = {"state": "DRAFT", "has_draft": True}
    assert probe_skip_reason(draft) == ""
