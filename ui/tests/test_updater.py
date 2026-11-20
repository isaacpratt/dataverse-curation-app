"""In-app update check: the Qt-free core and the worker contract, no network.

Every manager here is a fake; the velopack module is never imported
(except the two tests that substitute their own into sys.modules). The
feed timestamp lives in a throwaway workspace, so nothing touches the
real ui_prefs.json.
"""

from __future__ import annotations

import sys
import time
import types
from pathlib import Path
from typing import Any

import pytest

import ui.updater as updater


class FakeAsset:
    def __init__(self, version: str) -> None:
        self.Version = version
        self.FileName = f"DataverseDocent-{version}-full.nupkg"
        self.Size = 1024 * 1024


class FakeInfo:
    def __init__(self, version: str) -> None:
        self.TargetFullRelease = FakeAsset(version)
        self.IsDowngrade = False


class FakeManager:
    def __init__(
        self, *, info="1.2.0", portable=False, download_ok=True, error: Exception | None = None
    ):
        self.info_version = info
        self.portable = portable
        self.download_ok = download_ok
        self.error = error
        self.download_calls = 0
        self.progress_seen: list[int] = []
        self.pending_queries = 0
        self.apply_calls = 0

    # The Velopack surface updater.py uses ---------------------------------
    def get_is_portable(self):
        return self.portable

    def get_current_version(self):
        return "0.1.0"

    def check_for_updates(self):
        if self.error is not None:
            raise self.error
        if self.info_version is None:
            return None
        return FakeInfo(self.info_version)

    def download_updates(self, info, progress_callback=None):
        self.download_calls += 1
        if self.error is not None:
            raise self.error
        if not self.download_ok:
            raise RuntimeError("download exploded")
        for pct in (0, 25, 75, 100):
            if progress_callback is not None:
                progress_callback(pct)

    def get_update_pending_restart(self):
        self.pending_queries += 1
        return FakeAsset("1.2.0") if self.download_ok else None

    def wait_exit_then_apply_updates(self, asset, silent=False, restart=True, restart_args=None):
        self.apply_calls += 1


class BoomError(RuntimeError):
    pass


# ------------------------------------------------------------------
# The 24 h cache
# ------------------------------------------------------------------


def test_first_check_is_due(tmp_path: Path) -> None:
    assert updater.is_check_due(workspace=tmp_path) is True


def test_recent_check_is_not_due(tmp_path: Path) -> None:
    updater.record_check(now_s=1000, workspace=tmp_path)
    assert updater.is_check_due(now_s=1000 + 3600, workspace=tmp_path) is False
    assert updater.is_check_due(now_s=1000 + 24 * 3600 + 1, workspace=tmp_path) is True


def test_a_missing_timestamp_key_reads_as_due(tmp_path: Path) -> None:
    assert updater.last_checked_at(workspace=tmp_path) is None
    assert updater.is_check_due(workspace=tmp_path) is True


def test_cached_check_does_not_call_the_feed(tmp_path: Path) -> None:
    manager = FakeManager(info="9.9.9")
    updater.record_check(now_s=time.time(), workspace=tmp_path)

    outcome = updater.check_for_updates(manager=manager, workspace=tmp_path)

    assert outcome == {"status": "cached"}
    assert manager.download_calls == 0


def test_forced_check_bypasses_the_daily_cache(tmp_path: Path) -> None:
    manager = FakeManager(info="9.9.9")
    updater.record_check(now_s=time.time(), workspace=tmp_path)

    outcome = updater.check_for_updates(manager=manager, force=True, workspace=tmp_path)

    assert outcome["status"] == "update_available"
    assert outcome["version"] == "9.9.9"


# ------------------------------------------------------------------
# Happy path + core behaviours
# ------------------------------------------------------------------


def test_update_available_is_reported_with_version(tmp_path: Path) -> None:
    outcome = updater.check_for_updates(manager=FakeManager(info="0.2.0"), workspace=tmp_path)

    assert outcome["status"] == "update_available"
    assert outcome["version"] == "0.2.0"


def test_no_update_available_reports_up_to_date(tmp_path: Path) -> None:
    outcome = updater.check_for_updates(manager=FakeManager(info=None), workspace=tmp_path)

    assert outcome["status"] == "up_to_date"


def test_a_failed_check_is_a_value_not_an_exception(tmp_path: Path) -> None:
    outcome = updater.check_for_updates(
        manager=FakeManager(error=BoomError("403 rate limit")), workspace=tmp_path
    )

    assert outcome["status"] == "failed"
    assert outcome["reason"] == "rate_limited"


def test_pending_version_roundtrip(tmp_path: Path) -> None:
    assert updater.pending_version(workspace=tmp_path) is None
    updater.set_pending_version("0.2.0", workspace=tmp_path)
    assert updater.pending_version(workspace=tmp_path) == "0.2.0"
    updater.set_pending_version(None, workspace=tmp_path)
    assert updater.pending_version(workspace=tmp_path) is None


def test_feed_without_velopack_returns_unavailable() -> None:
    saved = sys.modules.get("velopack")
    sys.modules["velopack"] = types.ModuleType("velopack")
    try:
        assert updater.make_update_manager() is None
        assert updater.check_for_updates() == {"status": "unavailable"}
    finally:
        if saved is not None:
            sys.modules["velopack"] = saved
        else:
            del sys.modules["velopack"]


def test_portable_build_returns_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    fake: Any = types.ModuleType("velopack")
    captured: dict[str, object] = {}

    class Options:
        def __init__(self, allow_downgrade, maximum_deltas):
            captured["allow_downgrade"] = allow_downgrade
            captured["maximum_deltas"] = maximum_deltas

    class Source:
        def __init__(self, url, token, prerelease):
            captured["repo"] = url

    manager = FakeManager(portable=True)

    fake.GithubSource = Source
    fake.UpdateOptions = Options
    fake.UpdateManager = lambda source, options: manager
    monkeypatch.setitem(sys.modules, "velopack", fake)

    assert updater.make_update_manager() is None
    assert updater.check_for_updates() == {"status": "unavailable"}
    assert captured["allow_downgrade"] is False
    assert captured["maximum_deltas"] == 10


# ------------------------------------------------------------------
# Error classification + the one Log line
# ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("exc", "reason"),
    [
        (BoomError("403 rate limit exceeded"), "rate_limited"),
        (ConnectionResetError("reset by peer"), "network"),
        (TimeoutError("operation timed out"), "timeout"),
        (BoomError("404 Not Found"), "feed"),
        (BoomError("something exotic happened"), "unknown"),
    ],
)
def test_error_classification(exc: Exception, reason: str) -> None:
    assert updater.classify_error(exc) == reason


def test_a_failure_writes_one_log_line(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import curation.applog as applog

    applog.clear()
    outcome = updater.check_for_updates(
        manager=FakeManager(error=BoomError("boom")), force=True, workspace=tmp_path
    )
    matching = [line for line in applog.lines() if "Update check:" in line]
    assert outcome["status"] == "failed"
    assert len(matching) == 1


# ------------------------------------------------------------------
# Workers: off-GUI-thread contract (run synchronously, no thread needed)
# ------------------------------------------------------------------


def test_the_check_worker_emits_its_outcome(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(updater, "make_update_manager", lambda: FakeManager(info="0.2.0"))
    monkeypatch.setattr(updater, "is_check_due", lambda **_: True)
    outcomes: list[dict[str, Any]] = []

    worker = updater.UpdateCheckWorker(force=True)
    worker.finished.connect(lambda outcome: outcomes.append(outcome))
    worker.run()

    assert outcomes == [{"status": "update_available", "version": "0.2.0"}]


def test_the_download_worker_reports_progress_in_order(
    qapp, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manager = FakeManager(info="0.2.0")
    monkeypatch.setattr(updater, "make_update_manager", lambda: manager)
    monkeypatch.setattr(updater, "_resolve_workspace", lambda ws: tmp_path)
    monkeypatch.setattr(updater, "is_check_due", lambda **_: True)
    seen: list[int] = []

    worker = updater.UpdateDownloadWorker()
    worker.progress.connect(seen.append)
    finished: list[bool] = []
    worker.finished.connect(finished.append)
    worker.run()

    assert seen == sorted(seen)
    assert seen[-1] == 100
    assert finished == [True]
    assert updater.pending_version(workspace=tmp_path) == "0.2.0"


def test_pending_restart_uses_the_downloaded_asset(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = FakeManager(info="0.2.0")
    info = FakeInfo("0.2.0")

    assert updater.apply_update_on_restart(manager, info) is True
    assert manager.apply_calls == 1
