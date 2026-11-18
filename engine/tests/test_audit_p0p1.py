"""Regression tests for the code/UI audit fix batch (no network, no GUI).

Covers: log redaction, config save (token ACL), storage table state,
headless report path, human-size units, and dead-module removal.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

import curation.applog as applog
import curation.config as _config_module
from curation.config import AppConfig, Config, DataverseConfig


class _DictKeyring:
    def __init__(self) -> None:
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self.store.pop((service, username), None)


class _BrokenKeyring:
    def get_password(self, *a: Any) -> None:
        raise RuntimeError("no store available")

    def set_password(self, *a: Any) -> None:
        raise RuntimeError("no store available")

    def delete_password(self, *a: Any, **kw: Any) -> None:
        raise RuntimeError("no store available")


# -- log redaction -----------------------------------------------------------


def test_applog_redacts_api_key_and_token() -> None:
    applog.clear()
    applog.log("GET https://example/api with API_KEY=supersecret123")
    applog.log("X-Dataverse-key: abcdef123456 on header line")
    applog.log("token='zzz' query")
    joined = "\n".join(applog.lines())
    assert "supersecret123" not in joined
    assert "abcdef123456" not in joined
    assert "zzz" not in joined
    assert "***" in joined
    applog.clear()


def test_applog_redact_standalone() -> None:
    out = applog._redact("api_token=sekret&persistentId=doi:10.1234/x")
    assert "sekret" not in out
    assert "***" in out


@pytest.mark.parametrize(
    "line",
    [
        "Authorization: Bearer token-abc123",
        "Authorization: bearer token-abc123",
        "X-Dataverse-key: dvc-secret-456",
        "Api-Key: 9876543210",
        "api_key='legacy'",
        "password=hunter2",
        "secret=topsecret-1",
        "https://x.test/api?key=querykey123&other=1",
        "https://x.test/api?token=querykey123&key=two",
    ],
)
def test_applog_redacts_header_shaped_secrets(line: str) -> None:
    assert "***" in applog._redact(line)
    for leaked in (
        "token-abc123",
        "dvc-secret-456",
        "9876543210",
        "legacy",
        "hunter2",
        "topsecret-1",
        "querykey123",
    ):
        assert leaked not in applog._redact(line)


def test_applog_keeps_ordinary_lines() -> None:
    ordinary = "GET https://x.test/api/search q=* type=dataset per_page=1000 start=0"
    assert applog._redact(ordinary) == ordinary


# -- config save -------------------------------------------------------------


def test_config_save_writes_and_restricts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # keyring unavailable -> save falls back to plaintext + ACLs (the
    # POSIX-friendly path this test pins). The keyring-happy path is
    # covered in test_config.py.
    monkeypatch.setattr(_config_module, "_keyring", _BrokenKeyring())
    cfg_path = tmp_path / "config.json"
    cfg = Config(
        dataverse=DataverseConfig(
            base_url="https://demo.example.org",
            api_token="tok-abc",
            collection="root",
        ),
        app=AppConfig(workspace=tmp_path / "ws"),
    )
    cfg.save(cfg_path)
    assert cfg_path.exists()
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert data["dataverse"]["base_url"] == "https://demo.example.org"
    assert data["dataverse"]["api_token"] == "tok-abc"
    # POSIX: owner-only. Windows: chmod may be a no-op — ACL is applied best-effort.
    if os.name != "nt":
        mode = cfg_path.stat().st_mode & 0o777
        assert mode == 0o600


def test_config_load_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_config_module, "_keyring", _DictKeyring())
    cfg_path = tmp_path / "config.json"
    cfg = Config(
        dataverse=DataverseConfig(base_url="https://x.example", api_token="t"),
        app=AppConfig(workspace=tmp_path),
    )
    cfg.save(cfg_path)
    loaded = Config.load(cfg_path)
    assert loaded.dataverse.base_url == "https://x.example"
    assert loaded.dataverse.api_token == "t"


# -- storage -----------------------------------------------------------------


def test_storage_table_state_roundtrip(tmp_path: Path) -> None:  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
    from curation.storage import clear_table_state, save_table_state

    class _Hdr:
        def __init__(self) -> None:
            self._order = [2, 0, 1]
            self._sizes = {0: 80, 1: 120, 2: 40}
            self._vis = {0: True, 1: False, 2: True}
            self._sort_section = 1
            self._sort_order = 0  # AscendingOrder

        def count(self) -> int:
            return 3

        def logicalIndex(self, i: int) -> int:
            return self._order[i] if i < len(self._order) else i

        def visualIndex(self, i: int) -> int:
            return self._order.index(i) if i in self._order else i

        def sectionSize(self, i: int) -> int:
            return self._sizes.get(i, 50)

        def isSectionHidden(self, i: int) -> bool:
            return not self._vis.get(i, True)

        def sortIndicatorSection(self) -> int:
            return self._sort_section

        def sortIndicatorOrder(self) -> int:
            return self._sort_order

        def isSortIndicatorShown(self) -> bool:
            return True

        def saveState(self) -> bytes:
            return b""

        def restoreState(self, _s: Any) -> bool:
            return True

        def resizeSection(self, i: int, w: int) -> None:
            self._sizes[i] = w

        def setSectionHidden(self, i: int, h: bool) -> None:
            self._vis[i] = not h

        def moveSection(self, old: int, new: int) -> None:
            pass

        def setSortIndicator(self, s: int, o: int) -> None:
            self._sort_section = s
            self._sort_order = o

        def logicalSectionCount(self) -> int:
            return 3

        def sectionsClickable(self) -> bool:
            return True

        def setSectionsClickable(self, _v: Any) -> None:
            pass

        def sectionsMovable(self) -> bool:
            return True

        def setSectionsMovable(self, _v: Any) -> None:
            pass

        def stretchLastSection(self) -> bool:
            return False

        def setStretchLastSection(self, _v: Any) -> None:
            pass

    hdr = _Hdr()
    save_table_state(tmp_path, "test_table", hdr)
    snap_path = tmp_path / "table_layout.json"
    assert snap_path.exists()
    data = json.loads(snap_path.read_text(encoding="utf-8"))
    assert "test_table" in data
    clear_table_state(tmp_path, "test_table")
    data2 = json.loads(snap_path.read_text(encoding="utf-8"))
    assert "test_table" not in data2


def test_storage_size_cache(tmp_path: Path) -> None:
    from curation.storage import read_size_cache, write_size_entry

    write_size_entry(tmp_path, "doi:10.1/x", 12345, 3)
    cache = read_size_cache(tmp_path)
    assert "doi:10.1/x" in cache
    assert cache["doi:10.1/x"]["size"] == 12345
    assert cache["doi:10.1/x"]["files"] == 3


# -- headless ----------------------------------------------------------------


def test_headless_writes_report(tmp_path: Path) -> None:
    import subprocess

    ds = tmp_path / "ds"
    ds.mkdir()
    (ds / "a.txt").write_text("hello\n", encoding="utf-8")
    out = tmp_path / "report.json"
    proc = subprocess.run(
        [sys.executable, "main.py", "--headless", str(ds), "--out", str(out)],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(Path(__file__).resolve().parents[2]),
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert out.exists()
    report = json.loads(out.read_text(encoding="utf-8"))
    assert "files" in report or "results" in report or report


# -- dead modules removed ----------------------------------------------------


def test_dead_modules_removed() -> None:
    root = Path(__file__).resolve().parents[2]
    assert not (root / "ui" / "log_dialog.py").exists()
    assert not (root / "ui" / "requirements_dialog.py").exists()
    # LogPanel (dead strip widget) must not exist in log_panel.py
    src = (root / "ui" / "log_panel.py").read_text(encoding="utf-8")
    assert "class LogPanel" not in src
    assert "class LogPage" in src
    # LogPage show/hide gates the poll timer
    assert "def showEvent" in src
    assert "def hideEvent" in src


# -- no stale imports of deleted modules -------------------------------------


def test_no_imports_of_deleted_modules() -> None:
    root = Path(__file__).resolve().parents[2]
    bad = (
        "from ui.log_dialog",
        "from ui.requirements_dialog",
        "import log_dialog",
        "import requirements_dialog",
    )
    for py in root.rglob("*.py"):
        if ".venv" in py.parts or "dist" in py.parts or "build" in py.parts:
            continue
        if py.name == "test_audit_p0p1.py":
            continue
        text = py.read_text(encoding="utf-8", errors="ignore")
        for needle in bad:
            assert needle not in text, f"{py} still references {needle}"


# -- pandas not a hard dependency --------------------------------------------


def test_pandas_not_in_requirements() -> None:
    # requirements.txt was deleted when uv adopted (dv-ceh.1); dependency
    # declarations now live solely in pyproject.toml (project.dependencies +
    # [dependency-groups]).
    root = Path(__file__).resolve().parents[2]
    assert not (root / "requirements.txt").exists()
    pyproj = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert '"pandas' not in pyproj
    assert '"pandas"' not in pyproj
    # The lock is the real source of truth: a transitive bump can pull pandas
    # back in without pyproject.toml changing at all.
    lock = (root / "uv.lock").read_text(encoding="utf-8")
    assert 'name = "pandas"' not in lock
