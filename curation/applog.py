"""Application-wide communication log.

Records every Dataverse API request/response (and other notable events)
in an in-memory ring buffer. The UI can display it in a Log dialog.
Bridged to stdlib `logging` so `pytest -q` and file handlers work.
"""

import logging
import re
import threading
from collections import deque
from datetime import datetime

_LOCK = threading.Lock()


_REDACT_PATTERNS = [
    # Header-shaped credentials: X-Dataverse-key / Authorization / Api-Key.
    (re.compile(r"(X-Dataverse-key['\":\s=]+)([^\s'\"&]+)", re.IGNORECASE), r"\1***"),
    (re.compile(r"(Authorization['\":\s=]+[Bb]earer\s+)([^\s'\"&]+)", re.IGNORECASE), r"\1***"),
    (re.compile(r"(Api-Key['\":\s=]+)([^\s'\"&]+)", re.IGNORECASE), r"\1***"),
    # key=/token=.../password=... style secrets anywhere in the line.
    (
        re.compile(
            r"((?:API[_-]?KEY|api_token|token|password|secret)['\":\s=]+)([^\s'\"&]+)",
            re.IGNORECASE,
        ),
        r"\1***",
    ),
    (re.compile(r"(persistentId=[^\s&]*key=[^\s&]*)", re.IGNORECASE), "***"),
    # URLs with ?key=/token=/api_key= query params.
    (re.compile(r"([?&](?:key|token|api_key)=)[^&\s]*", re.IGNORECASE), r"\1***"),
]


_BUFFER: deque[str] = deque(maxlen=2000)


_logger = logging.getLogger("dataverse_docent")


def _redact(message: str) -> str:
    """Redact API tokens / keys from log lines (never persist secrets)."""
    try:
        text = str(message or "")
        for pattern, replacement in _REDACT_PATTERNS:
            text = pattern.sub(replacement, text)
        return text
    except Exception:
        return str(message or "")


def log(message: str) -> None:
    """Append one line to the in-memory request log."""
    # Local time (was UTC): curators read the strip against their clock.
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {_redact(message)}"
    with _LOCK:
        _BUFFER.append(line)
    try:
        _logger.debug(line)
    except Exception:
        pass


def lines() -> list[str]:
    """Return all logged lines (copy)."""
    with _LOCK:
        return list(_BUFFER)


def clear() -> None:
    """Drop all logged lines."""
    with _LOCK:
        _BUFFER.clear()


def get_app_log() -> type["AppLog"]:
    """Return the AppLog namespace (a class of staticmethods, not an instance)."""
    return AppLog


class AppLog:
    """Namespace used by dataverse_client for structured logging."""

    @staticmethod
    def warn(message: str) -> None:
        log(f"WARN: {message}")
        try:
            _logger.warning(_redact(message))
        except Exception:
            pass

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

    @staticmethod
    def expected(message: str) -> None:
        """Log a server answer that is the documented answer, not a bug.

        The message still carries the true call and response; the EXPECTED
        word only says the refusal is expected for that endpoint (for
        example a draft this account may not read). The Log page paints
        these in the muted tone instead of the error red.
        """
        log(f"EXPECTED: {message}")
        try:
            _logger.info(_redact(message))
        except Exception:
            pass


def log_response(
    method: str,
    url: str,
    status: int,
    elapsed_ms: int,
    summary: str = "",
    context: str = "",
) -> None:
    """Log one completed HTTP response (method, url, status code, elapsed ms)."""
    # Strip query-string secrets from URLs before storing.
    try:
        import re

        safe_url = re.sub(
            r"([?&](?:key|token|api_key)=)[^&]*", r"\1***", str(url or ""), flags=re.IGNORECASE
        )
    except Exception:
        safe_url = url
    msg = f"{method} {safe_url} → {status} ({elapsed_ms} ms)"
    if summary:
        msg += f" — {summary}"
    if context:
        # Context is appended, never substituted: the call, the status and
        # the timing stay exactly as the server answered them. The marker
        # is the same word the Log page paints in the muted tone.
        msg += f" — EXPECTED: {context}"
    log(msg)
