"""Application-wide communication log.

Records every Dataverse API request/response (and other notable events)
in an in-memory ring buffer. The UI can display it in a Log dialog.
"""

import threading
from collections import deque
from datetime import datetime, timezone
from typing import Deque, List

_LOCK = threading.Lock()
_BUFFER: Deque[str] = deque(maxlen=2000)


def log(message: str) -> None:
    line = f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {message}"
    with _LOCK:
        _BUFFER.append(line)


def lines() -> List[str]:
    with _LOCK:
        return list(_BUFFER)


def clear() -> None:
    with _LOCK:
        _BUFFER.clear()


def get_app_log() -> "AppLog":
    return AppLog


class AppLog:
    """Namespace used by dataverse_client for structured logging."""

    @staticmethod
    def info(message: str) -> None:
        log(message)

    @staticmethod
    def debug(message: str) -> None:
        log(f"DEBUG: {message}")

    @staticmethod
    def error(message: str) -> None:
        log(f"ERROR: {message}")


def log_response(method: str, url: str, status: int, elapsed_ms: int, summary: str = "") -> None:
    msg = f"{method} {url} → {status} ({elapsed_ms} ms)"
    if summary:
        msg += f" — {summary}"
    log(msg)