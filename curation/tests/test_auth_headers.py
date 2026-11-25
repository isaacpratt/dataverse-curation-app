"""A :guest 401 is a missing token, not a curation-scope refusal (dv-6rdy)."""

from typing import Any, cast

import pytest


class _Response:
    def __init__(self, payload: dict[str, Any], status: int = 200) -> None:
        self._payload = payload
        self.status_code = status
        self.ok = status < 400
        self.text = str(payload)
        self.url = "https://demo.borealisdata.ca/api/datasets/:persistentId"

    def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if not self.ok:
            import requests

            raise requests.HTTPError(response=self)


class _Session:
    """Captures the headers actually sent, not the headers we meant to send."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> _Response:
        self.calls.append({"url": url, **kwargs})
        return _Response({"status": "OK", "data": {"latestVersion": {}}})


def _client(token: str, session: _Session) -> Any:
    from curation.client.client import DataverseClient

    client = DataverseClient("https://demo.borealisdata.ca", token)
    client._session = cast(Any, session)
    return client


def test_dataset_read_sends_the_api_key_header():
    session = _Session()
    client = _client("secret-token", session)
    client.get_dataset_metadata("doi:10.80240/FK2/BDLPJF")
    assert session.calls
    assert session.calls[0]["headers"]["X-Dataverse-key"] == "secret-token"


def test_missing_token_refuses_before_sending_a_guest_request():
    import curation.applog as applog
    from curation.client.errors import ApiTokenRequired

    applog.clear()
    session = _Session()
    client = _client("", session)
    with pytest.raises(ApiTokenRequired):
        client.get_dataset_metadata("doi:10.80240/FK2/BDLPJF")
    with pytest.raises(ApiTokenRequired):
        client.get_file_inventory("doi:10.80240/FK2/BDLPJF")
    assert session.calls == [], "no anonymous request may be sent"
    assert any("API token" in line for line in applog.lines())


@pytest.mark.parametrize(
    "body",
    [
        '{"status":"ERROR","message":"User :guest is not permitted to perform requested action."}',
        '{"status":"ERROR","message":"Bad API key"}',
    ],
)
def test_guest_and_bad_key_are_not_expected_refusals(body):
    from curation.client.refusals import expected_api_reason, refusal_code

    for path in (
        "/api/datasets/:persistentId",
        "/api/datasets/:persistentId/versions/:draft",
    ):
        assert refusal_code(path, 401, body) == ""
        assert expected_api_reason(path, 401, body) == ""


def test_no_config_file_still_loads_a_stored_keyring_token(monkeypatch, tmp_path):
    from curation import config

    monkeypatch.setattr(config, "resolve_config_path", lambda _p=None: tmp_path / "config.json")
    monkeypatch.setattr(config, "_keyring_token", lambda _url: ("stored-token", ""))
    cfg = config.Config.load()
    assert cfg.dataverse.api_token == "stored-token"
    assert cfg.dataverse.api_token_source == "keyring"
    assert not cfg.dataverse.token_missing


def test_keyring_miss_is_flagged_instead_of_silent_anonymous(monkeypatch, tmp_path):
    from curation import config

    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(
        '{"dataverse":{"api_token_source":"keyring"}}', encoding="utf-8"
    )
    monkeypatch.setattr(config, "resolve_config_path", lambda _p=None: cfg_path)
    monkeypatch.setattr(config, "_keyring_token", lambda _url: ("", "no credential stored"))
    cfg = config.Config.load()
    assert cfg.dataverse.api_token == ""
    assert cfg.dataverse.token_missing
