"""Keyring-backed token persistence for config.json (Dataverse Docent).

Covers the contract: env > keyring > plaintext precedence, atomic keyring
writes, legacy plaintext migration on save, broken-store fallback, and
stale-credential deletion when the token is cleared.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

import curation.config as cfg_module
from curation.config import DEFAULT_CONFIG_PATH, Config


class FakeKeyring:
    def __init__(self, broken: bool = False) -> None:
        self.store: dict[tuple[str, str], str] = {}
        self.broken = broken

    def get_password(self, service: str, username: str) -> str | None:
        if self.broken:
            raise RuntimeError("store is unavailable")
        return self.store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        if self.broken:
            raise RuntimeError("store is unavailable")
        self.store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        if self.broken:
            raise RuntimeError("store is unavailable")
        self.store.pop((service, username), None)


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> FakeKeyring:
    fake = FakeKeyring()
    monkeypatch.setattr(cfg_module, "_keyring", fake)
    return fake


@pytest.fixture
def broken(monkeypatch: pytest.MonkeyPatch) -> FakeKeyring:
    fake = FakeKeyring(broken=True)
    monkeypatch.setattr(cfg_module, "_keyring", fake)
    return fake


def _write(tmp_path: Path, payload: dict[str, Any]) -> None:
    (tmp_path / "config.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _read(tmp_path: Path) -> dict[str, Any]:
    raw = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return raw


def test_save_writes_keyring_and_blanks_plaintext(store: FakeKeyring, tmp_path: Path) -> None:
    cfg = Config()
    cfg.dataverse.base_url = "https://example.test"
    cfg.dataverse.api_token = "supersecret"
    cfg.save(tmp_path / "config.json")
    raw = _read(tmp_path)
    assert raw["dataverse"]["api_token"] == ""
    assert raw["dataverse"]["api_token_source"] == "keyring"
    assert store.store[(cfg_module.KEYRING_SERVICE, "https://example.test")] == "supersecret"


def test_reload_reads_token_from_keyring(store: FakeKeyring, tmp_path: Path) -> None:
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


def test_env_overrides_keyring(
    store: FakeKeyring, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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


def test_fallback_to_plaintext_when_store_broken(broken: FakeKeyring, tmp_path: Path) -> None:
    cfg = Config()
    cfg.dataverse.base_url = "https://example.test"
    cfg.dataverse.api_token = "supersecret"
    cfg.save(tmp_path / "config.json")
    raw = _read(tmp_path)
    assert raw["dataverse"]["api_token"] == "supersecret"
    assert raw["dataverse"]["api_token_source"] == "config"


def test_load_falls_back_to_plaintext_when_store_broken(
    broken: FakeKeyring, tmp_path: Path
) -> None:
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


def test_plaintext_migrates_to_keyring_on_save(store: FakeKeyring, tmp_path: Path) -> None:
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


def test_legacy_config_without_source_marker(store: FakeKeyring, tmp_path: Path) -> None:
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


def test_clearing_token_deletes_stale_credential(store: FakeKeyring, tmp_path: Path) -> None:
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


def test_keyring_keyed_by_base_url(store: FakeKeyring, tmp_path: Path) -> None:
    cfg = Config()
    cfg.dataverse.base_url = "https://other.test/"
    cfg.dataverse.api_token = "abc"
    cfg.save(tmp_path / "config.json")
    assert (cfg_module.KEYRING_SERVICE, "https://other.test") in store.store


def test_default_path_untouched() -> None:
    assert Path("config.json") == DEFAULT_CONFIG_PATH


def _cfg_env(monkeypatch: pytest.MonkeyPatch, **vars: str) -> None:
    # scrub every relevant var, then set what the test wants
    for name in (
        "DATAVERSE_BASE_URL",
        "DATAVERSE_API_TOKEN",
        "DATAVERSE_COLLECTION",
        "DATAVERSE_WORKSPACE",
    ):
        monkeypatch.delenv(name, raising=False)
    for name, value in vars.items():
        monkeypatch.setenv(name, value)


def test_env_http_url_rejected(
    store: FakeKeyring, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _cfg_env(monkeypatch, DATAVERSE_BASE_URL="http://borealis.example")
    with pytest.raises(ValueError, match="plain HTTP"):
        Config.load(tmp_path / "config.json")


def test_env_non_https_scheme_rejected(
    store: FakeKeyring, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _cfg_env(monkeypatch, DATAVERSE_BASE_URL="ftp://borealis.example")
    with pytest.raises(ValueError, match="https://"):
        Config.load(tmp_path / "config.json")


def test_env_url_without_host_rejected(
    store: FakeKeyring, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _cfg_env(monkeypatch, DATAVERSE_BASE_URL="https://")
    with pytest.raises(ValueError, match="no host"):
        Config.load(tmp_path / "config.json")


def test_env_url_normalised_and_ws_honoured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store_dir = tmp_path / "ws-from-env"
    _cfg_env(
        monkeypatch,
        DATAVERSE_BASE_URL="  https://demo.borealisdata.ca/  ",
        DATAVERSE_WORKSPACE=str(store_dir),
    )
    cfg = Config.load(tmp_path / "config.json")
    assert cfg.dataverse.base_url == "https://demo.borealisdata.ca"
    assert cfg.app.workspace == store_dir


def test_env_http_url_rejected_with_file(
    store: FakeKeyring, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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


def test_config_write_includes_schema_version(store: FakeKeyring, tmp_path: Path) -> None:
    cfg = Config()
    cfg.save(tmp_path / "config.json")
    raw = _read(tmp_path)
    assert raw["version"] == 1


def test_config_drops_compat_aliases(store: FakeKeyring, tmp_path: Path) -> None:
    cfg = Config()
    cfg.dataverse.collection = "mcmaster"
    cfg.save(tmp_path / "config.json")
    raw = _read(tmp_path)
    dv = raw["dataverse"]
    assert "subtree" not in dv
    assert "collection_alias" not in dv
    assert dv["collection"] == "mcmaster"


def test_config_version_missing_is_tolerated(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {
            "dataverse": {"base_url": "https://ok.test", "api_token": "", "collection": ""},
            "app": {},
        },
    )
    cfg = Config.load(tmp_path / "config.json")
    assert cfg.dataverse.base_url == "https://ok.test"


def test_config_wrong_shaped_section_fails_loudly(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {"dataverse": "not-an-object", "app": {}},
    )
    with pytest.raises(ValueError, match="dataverse"):
        Config.load(tmp_path / "config.json")


def test_config_wrong_shaped_engine_tools_fails_loudly(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {"dataverse": {}, "engine": {"optional_tools": {"tesseract": 123}}},
    )
    with pytest.raises(ValueError, match="optional_tools"):
        Config.load(tmp_path / "config.json")


def test_config_wrong_base_url_type_fails_loudly(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {"dataverse": {"base_url": 42}, "app": {}},
    )
    with pytest.raises(ValueError, match=r"dataverse\.base_url"):
        Config.load(tmp_path / "config.json")


def test_chmod_failure_logs_warning_without_token(
    store: FakeKeyring, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os

    import curation.applog as applog

    def _boom(_path: Path, _mode: str) -> None:
        raise OSError("read-only filesystem")

    monkeypatch.setattr(os, "chmod", _boom)
    applog.clear()
    cfg = Config()
    cfg.dataverse.base_url = "https://example.test"
    cfg.dataverse.api_token = "tok-secret-marker-999"
    cfg.save(tmp_path / "config.json")
    joined = "\n".join(applog.lines())
    assert "could not be locked down" in joined
    assert "tok-secret-marker-999" not in joined


@pytest.mark.skipif(os.name != "nt", reason="icacls is Windows-only")
def test_icacls_failure_logs_warning_without_token(
    store: FakeKeyring, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess

    import curation.applog as applog

    class _Out:
        returncode = 1
        stderr = b"Access denied"
        stdout = b""

    calls: list[list[str]] = []

    def _run(args: list[str], **kwargs: Any) -> Any:
        calls.append(args)
        return _Out()

    monkeypatch.setattr(subprocess, "run", _run)
    monkeypatch.setenv("USERDOMAIN", "TESTDOMAIN")
    monkeypatch.setenv("USERNAME", "tester")
    applog.clear()
    cfg = Config()
    cfg.dataverse.base_url = "https://example.test"
    cfg.dataverse.api_token = "tok-secret-marker-999"
    cfg.save(tmp_path / "config.json")
    joined = "\n".join(applog.lines())
    assert "could not be locked down" in joined
    assert "tok-secret-marker-999" not in joined
    assert any(cmd[0] == "icacls" and "TESTDOMAIN\\tester:F" in cmd for cmd in calls)
    assert not any("Everyone" in arg for cmd in calls for arg in cmd)


@pytest.mark.skipif(os.name != "nt", reason="icacls is Windows-only")
def test_config_save_aborts_when_owner_cannot_be_resolved(
    store: FakeKeyring, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess

    monkeypatch.delenv("USERNAME", raising=False)
    monkeypatch.delenv("USERDOMAIN", raising=False)

    class _Fail:
        returncode = 1
        stdout = b""
        stderr = b"no such user"

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _Fail())
    cfg = Config()
    cfg.dataverse.base_url = "https://example.test"
    cfg.dataverse.api_token = "tok-secret-marker-999"
    target = tmp_path / "config.json"
    with pytest.raises(RuntimeError, match="could not resolve the current Windows account"):
        cfg.save(target)
    assert not target.exists()


# -- base URL validation (dv-v2e) -------------------------------------------


@pytest.mark.parametrize(
    ("bad_url", "match"),
    [
        ("http://host", "plain HTTP"),
        ("httpx://host", "https://"),
        ("ftp://host", "https://"),
        ("https://", "no host"),
        ("   ", "DATAVERSE_BASE_URL is empty"),
        ("host.test", "https://"),
    ],
)
def test_file_base_url_rejected(
    bad_url: str,
    match: str,
    store: FakeKeyring,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _cfg_env(monkeypatch)
    _write(
        tmp_path,
        {
            "version": 1,
            "dataverse": {"base_url": bad_url, "api_token": "", "collection": ""},
            "app": {},
        },
    )
    with pytest.raises(ValueError, match=match):
        Config.load(tmp_path / "config.json")


def test_file_base_url_normalised(
    store: FakeKeyring, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _cfg_env(monkeypatch)
    _write(
        tmp_path,
        {
            "version": 1,
            "dataverse": {"base_url": "https://Demo.Example/ ", "api_token": "", "collection": ""},
            "app": {},
        },
    )
    assert Config.load(tmp_path / "config.json").dataverse.base_url == "https://Demo.Example"


def test_client_rejects_cleartext_base_url() -> None:
    from curation.client import DataverseClient

    with pytest.raises(ValueError, match="plain HTTP"):
        DataverseClient("http://host.test", "tok")


def test_cli_dataverse_flag_rejects_cleartext(
    store: FakeKeyring, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import argparse

    from main import main as run_main

    _cfg_env(monkeypatch)
    monkeypatch.setattr(
        "curation.config.resolve_config_path", lambda path=None: tmp_path / "config.json"
    )
    seen: list[str] = []

    def _error(message: str) -> None:
        seen.append(message)
        raise SystemExit(2)

    monkeypatch.setattr(argparse.ArgumentParser, "error", lambda self, message: _error(message))
    with pytest.raises(SystemExit):
        run_main(["--dataverse", "http://host.test"])
    assert seen
    assert "plain HTTP" in seen[0]
