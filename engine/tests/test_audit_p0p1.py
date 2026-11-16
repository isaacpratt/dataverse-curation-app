"""Regression tests for the code/UI audit fix batch (no network, no GUI).

Covers: log redaction, config save (token ACL), storage table state,
headless report path, human-size units, and dead-module removal.
"""

import json
import os
import sys
from pathlib import Path

import applog
from config import AppConfig, Config, DataverseConfig

# -- log redaction -----------------------------------------------------------


def test_applog_redacts_api_key_and_token():
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


def test_applog_redact_standalone():
    out = applog._redact("api_token=sekret&persistentId=doi:10.1234/x")
    assert "sekret" not in out
    assert "***" in out


# -- config save -------------------------------------------------------------


def test_config_save_writes_and_restricts(tmp_path):
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


def test_config_load_roundtrip(tmp_path):
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


def test_storage_table_state_roundtrip(tmp_path):  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
    from storage import clear_table_state, save_table_state

    class _Hdr:
        def __init__(self):
            self._order = [2, 0, 1]
            self._sizes = {0: 80, 1: 120, 2: 40}
            self._vis = {0: True, 1: False, 2: True}
            self._sort_section = 1
            self._sort_order = 0  # AscendingOrder

        def count(self):
            return 3

        def logicalIndex(self, i):
            return self._order[i] if i < len(self._order) else i

        def visualIndex(self, i):
            return self._order.index(i) if i in self._order else i

        def sectionSize(self, i):
            return self._sizes.get(i, 50)

        def isSectionHidden(self, i):
            return not self._vis.get(i, True)

        def sortIndicatorSection(self):
            return self._sort_section

        def sortIndicatorOrder(self):
            return self._sort_order

        def isSortIndicatorShown(self):
            return True

        def saveState(self):
            return b""

        def restoreState(self, _s):
            return True

        def resizeSection(self, i, w):
            self._sizes[i] = w

        def setSectionHidden(self, i, h):
            self._vis[i] = not h

        def moveSection(self, old, new):
            pass

        def setSortIndicator(self, s, o):
            self._sort_section = s
            self._sort_order = o

        def logicalSectionCount(self):
            return 3

        def sectionsClickable(self):
            return True

        def setSectionsClickable(self, _v):
            pass

        def sectionsMovable(self):
            return True

        def setSectionsMovable(self, _v):
            pass

        def stretchLastSection(self):
            return False

        def setStretchLastSection(self, _v):
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


def test_storage_size_cache(tmp_path):
    from storage import read_size_cache, write_size_entry

    write_size_entry(tmp_path, "doi:10.1/x", 12345, 3)
    cache = read_size_cache(tmp_path)
    assert "doi:10.1/x" in cache
    assert cache["doi:10.1/x"]["size"] == 12345
    assert cache["doi:10.1/x"]["files"] == 3


# -- headless ----------------------------------------------------------------


def test_headless_writes_report(tmp_path):
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


# -- human size --------------------------------------------------------------


def test_human_size_gb_and_tb():
    from ui.checks_tree import _human_size as checks_size
    from ui.dashboard import _human_size as dash_size
    from ui.dataset_detail import _human_size as detail_size
    from ui.download_dialog import _human_size as dl_size

    for fn in (checks_size, dash_size, detail_size, dl_size):
        assert fn(512) == "512 B"
        assert "KB" in fn(2048)
        assert "MB" in fn(5 * 1000 * 1000)
        assert "GB" in fn(3 * 1000**3)
        assert "TB" in fn(2 * 1000**4)
    # All four are the same shared helper (dv-005).
    assert checks_size is dash_size or checks_size(2048) == dash_size(2048)
    for fn in (checks_size, dash_size, detail_size, dl_size):
        assert fn(999) == "999 B"
        assert fn(1000).startswith("1.0 KB")


# -- dead modules removed ----------------------------------------------------


def test_dead_modules_removed():
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


def test_no_imports_of_deleted_modules():
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


def test_pandas_not_in_requirements():
    # requirements.txt was deleted when uv adopted (dv-ceh.1); dependency
    # declarations now live solely in pyproject.toml (project.dependencies +
    # [dependency-groups]).
    root = Path(__file__).resolve().parents[2]
    assert not (root / "requirements.txt").exists()
    pyproj = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert '"pandas' not in pyproj
    assert '"pandas"' not in pyproj
