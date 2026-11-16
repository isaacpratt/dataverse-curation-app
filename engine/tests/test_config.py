"""Keyring-backed token persistence for config.json (Dataverse Docent).

Covers the contract: env > keyring > plaintext precedence, atomic keyring
writes, legacy plaintext migration on save, broken-store fallback, and
stale-credential deletion when the token is cleared.
"""

from __future__ import annotations

import json

import pytest

import config as cfg_module
from config import DEFAULT_CONFIG_PATH, Config


class FakeKeyring:
    def __init__(self, broken: bool = False):
        self.store: dict[tuple[str, str], str] = {}
        self.broken = broken

    def get_password(self, service, username):
        if self.broken:
            raise RuntimeError("store is unavailable")
        return self.store.get((service, username))

    def set_password(self, service, username, password):
        if self.broken:
            raise RuntimeError("store is unavailable")
        self.store[(service, username)] = password

    def delete_password(self, service, username):
        if self.broken:
            raise RuntimeError("store is unavailable")
        self.store.pop((service, username), None)


@pytest.fixture
def store(monkeypatch):
    fake = FakeKeyring()
    monkeypatch.setattr(cfg_module, "_keyring", fake)
    return fake


@pytest.fixture
def broken(monkeypatch):
    fake = FakeKeyring(broken=True)
    monkeypatch.setattr(cfg_module, "_keyring", fake)
    return fake


def _write(tmp_path, payload: dict) -> None:
    (tmp_path / "config.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _read(tmp_path) -> dict:
    return json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))


def test_save_writes_keyring_and_blanks_plaintext(store, tmp_path):
    cfg = Config()
    cfg.dataverse.base_url = "https://example.test"
    cfg.dataverse.api_token = "supersecret"
    cfg.save(tmp_path / "config.json")
    raw = _read(tmp_path)
    assert raw["dataverse"]["api_token"] == ""
    assert raw["dataverse"]["api_token_source"] == "keyring"
    assert store.store[(cfg_module.KEYRING_SERVICE, "https://example.test")] == "supersecret"


def test_reload_reads_token_from_keyring(store, tmp_path):
    _write(
        tmp_path,
        {
            "dataverse": {
                "base_url": "https://example.test",
                "api_token": "",
                "api_token_source": "keyring",
                "collection": "",
            },
            "app": {},
        },
    )
    store.store[(cfg_module.KEYRING_SERVICE, "https://example.test")] = "token-from-store"
    cfg = Config.load(tmp_path / "config.json")
    assert cfg.dataverse.api_token == "token-from-store"
    assert cfg.dataverse.api_token_source == "keyring"


def test_env_overrides_keyring(store, tmp_path, monkeypatch):
    _write(
        tmp_path,
        {
            "dataverse": {
                "base_url": "https://example.test",
                "api_token": "",
                "api_token_source": "keyring",
                "collection": "",
            },
            "app": {},
        },
    )
    store.store[(cfg_module.KEYRING_SERVICE, "https://example.test")] = "from-store"
    monkeypatch.setenv("DATAVERSE_API_TOKEN", "from-env")
    cfg = Config.load(tmp_path / "config.json")
    assert cfg.dataverse.api_token == "from-env"
    assert cfg.dataverse.api_token_source == "env"


def test_fallback_to_plaintext_when_store_broken(broken, tmp_path):
    cfg = Config()
    cfg.dataverse.base_url = "https://example.test"
    cfg.dataverse.api_token = "supersecret"
    cfg.save(tmp_path / "config.json")
    raw = _read(tmp_path)
    assert raw["dataverse"]["api_token"] == "supersecret"
    assert raw["dataverse"]["api_token_source"] == "config"


def test_load_falls_back_to_plaintext_when_store_broken(broken, tmp_path):
    _write(
        tmp_path,
        {
            "dataverse": {
                "base_url": "https://example.test",
                "api_token": "legacy-token",
                "api_token_source": "keyring",
                "collection": "",
            },
            "app": {},
        },
    )
    cfg = Config.load(tmp_path / "config.json")
    assert cfg.dataverse.api_token == "legacy-token"


def test_plaintext_migrates_to_keyring_on_save(store, tmp_path):
    _write(
        tmp_path,
        {
            "dataverse": {
                "base_url": "https://example.test",
                "api_token": "legacy-token",
                "api_token_source": "config",
                "collection": "",
            },
            "app": {},
        },
    )
    cfg = Config.load(tmp_path / "config.json")
    assert cfg.dataverse.api_token == "legacy-token"  # file token still valid pre-save
    cfg.save(tmp_path / "config.json")
    raw = _read(tmp_path)
    assert raw["dataverse"]["api_token"] == ""
    assert raw["dataverse"]["api_token_source"] == "keyring"
    assert store.store[(cfg_module.KEYRING_SERVICE, "https://example.test")] == "legacy-token"


def test_legacy_config_without_source_marker(store, tmp_path):
    _write(
        tmp_path,
        {
            "dataverse": {
                "base_url": "https://example.test",
                "api_token": "plain",
                "collection": "",
            },
            "app": {},
        },
    )
    cfg = Config.load(tmp_path / "config.json")
    assert cfg.dataverse.api_token == "plain"
    assert cfg.dataverse.api_token_source == "config"


def test_clearing_token_deletes_stale_credential(store, tmp_path):
    _write(
        tmp_path,
        {
            "dataverse": {
                "base_url": "https://example.test",
                "api_token": "",
                "api_token_source": "keyring",
                "collection": "",
            },
            "app": {},
        },
    )
    store.store[(cfg_module.KEYRING_SERVICE, "https://example.test")] = "stale"
    cfg = Config.load(tmp_path / "config.json")
    cfg.dataverse.api_token = ""
    cfg.save(tmp_path / "config.json")
    assert (cfg_module.KEYRING_SERVICE, "https://example.test") not in store.store


def test_keyring_keyed_by_base_url(store, tmp_path):
    cfg = Config()
    cfg.dataverse.base_url = "https://other.test/"
    cfg.dataverse.api_token = "abc"
    cfg.save(tmp_path / "config.json")
    assert (cfg_module.KEYRING_SERVICE, "https://other.test") in store.store


def test_default_path_untouched():
    assert cfg_module.Path("config.json") == DEFAULT_CONFIG_PATH

def _cfg_env(monkeypatch, **vars):
    # scrub every relevant var, then set what the test wants
    for name in ("DATAVERSE_BASE_URL", "DATAVERSE_API_TOKEN", "DATAVERSE_COLLECTION", "DATAVERSE_WORKSPACE"):
        monkeypatch.delenv(name, raising=False)
    for name, value in vars.items():
        monkeypatch.setenv(name, value)


def test_env_http_url_rejected(store, tmp_path, monkeypatch):
    _cfg_env(monkeypatch, DATAVERSE_BASE_URL="http://borealis.example")
    with pytest.raises(ValueError, match="plain HTTP"):
        Config.load(tmp_path / "config.json")


def test_env_non_https_scheme_rejected(store, tmp_path, monkeypatch):
    _cfg_env(monkeypatch, DATAVERSE_BASE_URL="ftp://borealis.example")
    with pytest.raises(ValueError, match="https://"):
        Config.load(tmp_path / "config.json")


def test_env_url_without_host_rejected(store, tmp_path, monkeypatch):
    _cfg_env(monkeypatch, DATAVERSE_BASE_URL="https://")
    with pytest.raises(ValueError, match="no host"):
        Config.load(tmp_path / "config.json")


def test_env_url_normalised_and_ws_honoured(tmp_path, monkeypatch):
    store_dir = tmp_path / "ws-from-env"
    _cfg_env(
        monkeypatch,
        DATAVERSE_BASE_URL="  https://demo.borealisdata.ca/  ",
        DATAVERSE_WORKSPACE=str(store_dir),
    )
    cfg = Config.load(tmp_path / "config.json")
    assert cfg.dataverse.base_url == "https://demo.borealisdata.ca"
    assert cfg.app.workspace == store_dir


def test_env_http_url_rejected_with_file(store, tmp_path, monkeypatch):
    _write(
        tmp_path,
        {
            "dataverse": {"base_url": "https://ok.test", "api_token": "", "collection": ""},
            "app": {},
        },
    )
    _cfg_env(monkeypatch, DATAVERSE_BASE_URL="http://borealis.example")
    with pytest.raises(ValueError, match="plain HTTP"):
        Config.load(tmp_path / "config.json")
