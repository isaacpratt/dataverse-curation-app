"""The app log is for Dataverse API calls and responses only.

Non-API notices (window-frame management, config warnings, dashboard
metrics, updater lines, help-page lines, etc.) must not appear here.
This test runs the app offscreen and asserts every captured log line is
an API call/response. Any non-API line found is reported as a failure,
so the check surfaces infra/UI noise that should be silenced or removed.
"""

import re

import pytest


_API_LINE_RE = re.compile(
    r"^(GET|PUT|DELETE|POST|PATCH|HEAD|OPTIONS) "
    r"https?://"
    r".*"
    r" → \d+ \(.*\)$"
)

_EXPECTED_API_RE = re.compile(
    r"^(GET|PUT|DELETE|POST|PATCH|HEAD|OPTIONS) "
    r"https?://"
    r".*"
    r" → \d+ \(.*\)$"
    r" — EXPECTED:"
)

_WARN_API_RE = re.compile(
    r"^WARN: (GET|PUT|DELETE|POST|PATCH|HEAD|OPTIONS) "
    r"https?://"
)

_ERROR_API_RE = re.compile(
    r"^ERROR: (GET|PUT|DELETE|POST|PATCH|HEAD|OPTIONS) "
    r"https?://"
)

_DEBUG_API_RE = re.compile(
    r"^DEBUG: (GET|PUT|DELETE|POST|PATCH|HEAD|OPTIONS) "
    r"https?://"
)


def _is_api_line(line: str) -> bool:
    """True when `line` is a Dataverse API call or response."""
    return bool(
        _API_LINE_RE.match(line)
        or _EXPECTED_API_RE.match(line)
        or _WARN_API_RE.match(line)
        or _ERROR_API_RE.match(line)
        or _DEBUG_API_RE.match(line)
    )


def test_app_log_contains_only_api_notices(win, qapp):
    """After a normal offscreen app start, the log holds only API lines.

    The `win` fixture creates a MainWindow and shows it (which runs
    `_apply_dwm_frame` via `showEvent`), so any DWM frame notice would be
    captured here. Other non-API notices (config warnings, dashboard
    metrics, updater lines, help-page lines) are also caught.
    """
    from curation.applog import clear, lines

    clear()

    # Re-show to exercise showEvent -> _apply_dwm_frame and pump the event
    # loop so any deferred logging surfaces.
    win.show()
    for _ in range(10):
        qapp.processEvents()

    logged = lines()
    non_api = [line for line in logged if not _is_api_line(line)]

    assert not non_api, (
        "Non-API notices found in the app log. The log is for API calls "
        f"and responses only. Offending lines: {non_api}"
    )
