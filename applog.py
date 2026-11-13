"""Application-wide communication log.

Records every Dataverse API request/response (and other notable events)
in an in-memory ring buffer. The UI can display it in a Log dialog.
Bridged to stdlib `logging` so `pytest -q` and file handlers work.
"""

import logging
import threading
from collections import deque
from datetime import datetime

_LOCK = threading.Lock()
_BUFFER: deque[str] = deque(maxlen=2000)

_logger = logging.getLogger("curation_app")


def _redact(message: str) -> str:
    """Redact API tokens / keys from log lines (never persist secrets)."""
    try:
        import re

        text = str(message or "")
        # X-Dataverse-key header values, API_KEY=..., key=..., token=...
        text = re.sub(r"(X-Dataverse-key['\":\s=]+)([^\s'\"&]+)", r"\1***", text, flags=re.IGNORECASE)
        text = re.sub(r"((?:API[_-]?KEY|api_token|token)['\":\s=]+)([^\s'\"&]+)", r"\1***", text, flags=re.IGNORECASE)
        text = re.sub(r"(persistentId=[^\s&]*key=[^\s&]*)", "***", text, flags=re.IGNORECASE)
        return text
    except Exception:
        return str(message or "")


def log(message: str) -> None:
    # Local time (was UTC): curators read the strip against their clock.
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {_redact(message)}"
    with _LOCK:
        _BUFFER.append(line)
    try:
        _logger.debug(line)
    except Exception:
        pass


def lines() -> list[str]:
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
        try:
            _logger.info(_redact(message))
        except Exception:
            pass

    @staticmethod
    def debug(message: str) -> None:
        log(f"DEBUG: {message}")

    @staticmethod
    def error(message: str) -> None:
        log(f"ERROR: {message}")
        try:
            _logger.error(_redact(message))
        except Exception:
            pass


def log_response(method: str, url: str, status: int, elapsed_ms: int, summary: str = "") -> None:
    # Strip query-string secrets from URLs before storing.
    try:
        import re

        safe_url = re.sub(r"([?&](?:key|token|api_key)=)[^&]*", r"\1***", str(url or ""), flags=re.IGNORECASE)
    except Exception:
        safe_url = url
    msg = f"{method} {safe_url} → {status} ({elapsed_ms} ms)"
    if summary:
        msg += f" — {summary}"
    log(msg)
