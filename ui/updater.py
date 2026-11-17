"""In-app update check (Velopack + the repo's GitHub releases feed).

Two layers, split so the policy is testable without Qt or a running app:

- the Qt-free core: manager construction (``make_update_manager``), the
  once-a-day cache decision (``is_check_due`` / ``record_check``), the
  result classification (``classify_error``) and ``check_for_updates`` —
  every failure is a value, never an exception;
- the thin Qt layer: ``UpdateCheckWorker`` / ``UpdateDownloadWorker``
  QThreads (registered with ``ui.workers.register_worker``). A module
  bus singleton carries "something changed" pings to the About pane, so
  a daily check that finds an update lights the affordance without the
  pane being open.

The feed is the repo's own public releases via ``GithubSource`` with no
token - 60 requests per hour per IP, so the automatic check is cached for
24 h and the manual button cannot hammer it. Only an installed Velopack
build may apply an update: a portable zip or a source checkout reports
"updates are unavailable in this build" - never an exception, never a
modal, never a traceback.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from engine.feed import REPO_URL

LAST_CHECK_PREF = "update_check_last"  # epoch seconds (ui_prefs.json)
PENDING_PREF = "update_pending_version"  # downloaded, waiting for a restart

CHECK_INTERVAL_S = 24 * 60 * 60

_LOG_TAG = "Update check:"


# --------------------------------------------------------------------------
# Qt-free core
# --------------------------------------------------------------------------


def _now_s() -> float:
    return time.time()


def _resolve_workspace(workspace) -> Path | None:
    if workspace is not None:
        return Path(workspace)
    try:
        from config import Config

        return Path(Config.load(None).app.workspace)
    except Exception:
        return None


def _pref_get(key: str, default=None, workspace=None):
    ws = _resolve_workspace(workspace)
    if ws is None:
        return default
    from storage import read_ui_pref

    return read_ui_pref(ws, key, default)


def _pref_set(key: str, value, workspace=None) -> None:
    ws = _resolve_workspace(workspace)
    if ws is None:
        return
    from storage import write_ui_pref

    write_ui_pref(ws, key, value)


def is_check_due(now_s: float | None = None, workspace=None) -> bool:
    """Return True when no check has been recorded inside the last 24 h."""
    last = _pref_get(LAST_CHECK_PREF, workspace=workspace)
    if last is None:
        return True
    try:
        return (now_s if now_s is not None else _now_s()) - float(last) >= CHECK_INTERVAL_S
    except (TypeError, ValueError):
        return True


def record_check(now_s: float | None = None, workspace=None) -> None:
    _pref_set(LAST_CHECK_PREF, int(now_s if now_s is not None else _now_s()), workspace=workspace)


def last_checked_at(workspace=None) -> int | None:
    value = _pref_get(LAST_CHECK_PREF, workspace=workspace)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def pending_version(workspace=None) -> str | None:
    value = _pref_get(PENDING_PREF, workspace=workspace)
    return str(value) if value else None


def set_pending_version(version: str | None, workspace=None) -> None:
    _pref_set(PENDING_PREF, version, workspace=workspace)


def classify_error(exc: BaseException) -> str:
    """Bucket an exception into one short i18n-friendly reason."""
    text = f"{type(exc).__name__}: {exc}".lower()
    if any(needle in text for needle in ("403", "rate limit", "x-ratelimit")):
        return "rate_limited"
    if any(needle in text for needle in ("connection", "network", "dns", "10054", "reset")):
        return "network"
    if any(needle in text for needle in ("timeout", "timed out", "10060")):
        return "timeout"
    if any(needle in text for needle in ("404", "not found", "feed", "release", "json")):
        return "feed"
    return "unknown"


def _log_failure(detail: str) -> None:
    try:
        import applog

        applog.log(f"{_LOG_TAG} {detail}")
    except Exception:
        pass


def make_update_manager():
    """Return an UpdateManager for this install, or None when updates don't apply.

    Returns None for a source checkout, a portable zip and a frozen build
    without the Velopack locator - never raises.
    """
    try:
        import velopack

        source = velopack.GithubSource(REPO_URL, None, False)
        options = velopack.UpdateOptions(
            False,  # AllowVersionDowngrade: only move forward
            10,     # MaximumDeltasBeforeFallback (Velopack default)
        )
        manager = velopack.UpdateManager(source, options)
        # Portable builds expose no locator and cannot self-replace.
        if manager.get_is_portable():
            return None
        # Resolve against the install layout now, not at the first check.
        manager.get_current_version()
        return manager
    except Exception:
        return None


def check_for_updates(manager=None, *, force: bool = False, workspace=None) -> dict[str, Any]:
    """Check once and return a plain-dict outcome (never raises).

    Outcome keys:
      status:  unavailable | cached | up_to_date | update_available | failed
      version: target version when status == update_available
      reason:  classification tag when status == failed
    """
    try:
        manager = manager if manager is not None else make_update_manager()
        if manager is None:
            return {"status": "unavailable"}
        if not force and not is_check_due(workspace=workspace):
            return {"status": "cached"}
        try:
            info = manager.check_for_updates()
        except Exception as exc:
            reason = classify_error(exc)
            _log_failure(f"{reason} ({exc})")
            record_check(workspace=workspace)  # a flapping feed must not spin the daily tick
            return {"status": "failed", "reason": reason}
        record_check(workspace=workspace)
        if info is None:
            return {"status": "up_to_date"}
        version = getattr(getattr(info, "TargetFullRelease", None), "Version", None)
        return {
            "status": "update_available",
            "version": str(version) if version else None,
        }
    except Exception as exc:  # belt and braces; the guard above must hold
        reason = classify_error(exc)
        _log_failure(f"{reason} ({exc})")
        return {"status": "failed", "reason": reason}


def download_update(manager, info=None, progress_callback=None, workspace=None):
    """Download the pending update; returns (ok, update_info). Never raises."""
    try:
        info = info if info is not None else manager.check_for_updates()
        if info is None:
            return False, None
        manager.download_updates(info, progress_callback)
        version = getattr(getattr(info, "TargetFullRelease", None), "Version", None)
        if version:
            set_pending_version(str(version), workspace=workspace)
        return True, info
    except Exception as exc:
        _log_failure(f"download failed: {exc}")
        return False, None


def apply_update_on_restart(manager, info=None) -> bool:
    """Queue the downloaded update to apply after the app exits. Never raises."""
    try:
        target = info if info is not None else manager.get_update_pending_restart()
        if target is None:
            return False
        manager.wait_exit_then_apply_updates(target, silent=False, restart=True)
        return True
    except Exception as exc:
        _log_failure(f"apply failed: {exc}")
        return False


# --------------------------------------------------------------------------
# QThread wrappers (the UI side)
# --------------------------------------------------------------------------

from PySide6.QtCore import QObject, QThread, Signal  # noqa: E402


class UpdateBus(QObject):
    # Payload-free: listeners re-read state rather than trusting contents.
    stateChanged = Signal()


_bus: UpdateBus | None = None


def bus() -> UpdateBus:
    global _bus
    if _bus is None:
        _bus = UpdateBus()
    return _bus


def notify_state_changed() -> None:
    try:
        bus().stateChanged.emit()
    except Exception:
        pass


class UpdateCheckWorker(QThread):
    """One feed query; the About pane and the daily tick share it."""

    finished = Signal(dict)

    def __init__(self, force: bool = False, parent=None):
        super().__init__(parent)
        from ui.workers import register_worker

        self._force = force
        self._outcome: dict[str, Any] = {"status": "failed", "reason": "unknown"}
        register_worker(self)

    def run(self) -> None:
        try:
            self._outcome = check_for_updates(force=self._force)
        except Exception as exc:  # pragma: no cover - the core never raises
            _log_failure(f"worker: {classify_error(exc)} ({exc})")
        self.finished.emit(self._outcome)


class UpdateDownloadWorker(QThread):
    progress = Signal(int)  # 0..100
    finished = Signal(bool)

    def __init__(self, info=None, parent=None):
        super().__init__(parent)
        from ui.workers import register_worker

        self._info = info
        self.info = None  # the UpdateInfo a later restart hands back to Velopack
        register_worker(self)

    def run(self) -> None:
        try:
            manager = make_update_manager()
            if manager is None:
                self.finished.emit(False)
                return

            def _progress(*args) -> None:
                try:
                    pct = float(args[0]) if args else 0.0
                    self.progress.emit(max(0, min(100, int(pct))))
                except Exception:
                    pass

            ok, info = download_update(manager, self._info, _progress)
            self._info = info
            self.info = info
            self.finished.emit(ok)
        except Exception as exc:
            _log_failure(f"download worker: {classify_error(exc)} ({exc})")
            self.finished.emit(False)
