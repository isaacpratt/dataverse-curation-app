"""The Access column and the EXPECTED log tone.

Two halves of one promise: an API refusal that is the server's
documented answer is not a bug. The Log says EXPECTED (and keeps the raw
call and response), and the queue says what could not be read and why.
"""

from typing import Any

from ui.i18n import t


def _row(pid: Any = "doi:10.5072/FK2/A", **facts: Any):
    row = {"title": "T", "persistent_id": pid, "state": "DRAFT"}
    row.update(facts)
    return row


def test_access_column_is_quiet_when_everything_read(win):
    from ui.dashboard import _access_text, _access_tooltip

    row = _row(
        access={"state": "readable", "reason": "", "detail": "", "status": 200, "version": ":draft"}
    )
    assert _access_text(row) == ""
    assert _access_tooltip(row) == ""


def test_access_column_names_the_refusal(win):
    from ui.dashboard import _access_text

    row = _row(
        access={
            "state": "restricted",
            "reason": "draft_not_readable",
            "detail": "User @pratti is not permitted",
            "status": 401,
        }
    )
    assert _access_text(row) == t("dashboard.access.draft_not_readable")


def test_access_column_names_a_missing_published_version(win):
    from ui.dashboard import _access_text

    row = _row(
        access={
            "state": "metadata_only",
            "reason": "no_readable_version",
            "detail": "",
            "status": 404,
        }
    )
    assert _access_text(row) == t("dashboard.access.no_readable_version")


def test_access_tooltip_carries_the_reason_and_the_server_message(win):
    from ui.dashboard import _access_tooltip

    row = _row(
        access={
            "state": "restricted",
            "reason": "draft_not_readable",
            "detail": "User @pratti is not permitted",
            "status": 401,
        }
    )
    tip = _access_tooltip(row)
    assert t("dashboard.access.tip_draft_not_readable") in tip
    assert "User @pratti is not permitted" in tip


def test_hidden_curation_state_is_reported(win):
    from ui.dashboard import _access_text, _access_tooltip

    row = _row(
        curation_access={
            "state": "unreadable",
            "reason": "not_under_curation",
            "detail": "You are not permitted to view the curation status",
            "status": 403,
        }
    )
    assert _access_text(row) == t("dashboard.access.not_under_curation")
    assert "not permitted" in _access_tooltip(row)


def test_queue_paints_the_access_cell(win):
    dash = win._dashboard
    dash._all_datasets = [
        _row(
            "p1",
            access={
                "state": "restricted",
                "reason": "draft_not_readable",
                "detail": "User @pratti is not permitted",
                "status": 401,
            },
        ),
        _row(
            "p2",
            access={
                "state": "readable",
                "reason": "",
                "detail": "",
                "status": 200,
                "version": ":draft",
            },
        ),
    ]
    dash._state_filter.setCurrentIndex(0)
    dash._apply_filter()
    col = dash._col_index.get("access")
    pid_col = dash._col_index.get("persistent_id")
    assert col is not None
    assert pid_col is not None
    # A curator's saved queue layout may sort by any column, so locate the
    # rows by id instead of assuming insertion order.
    rows = {
        dash._table.item(row, pid_col).text(): row
        for row in range(dash._table.rowCount())
        if dash._table.item(row, pid_col) is not None
    }
    assert set(rows) == {"p1", "p2"}, f"unexpected queue rows: {sorted(rows)}"
    first = dash._table.item(rows["p1"], col)
    second = dash._table.item(rows["p2"], col)
    assert first.text() == t("dashboard.access.draft_not_readable")
    assert "not permitted" in first.toolTip()
    assert second.text() == ""


def _highlighter() -> Any:
    from PySide6.QtWidgets import QPlainTextEdit

    from ui.log_panel import LogHighlighter

    view = QPlainTextEdit()
    return LogHighlighter(view.document())


def test_log_highlighter_treats_expected_lines_as_expected(win):
    highlighter = _highlighter()
    line = (
        "[15:04:05] EXPECTED: GET https://demo.example/api/datasets/:persistentId/"
        "versions/:draft → 401 (42 ms) — EXPECTED: this account may not read "
        'the draft version of this dataset — {"status":"ERROR"}'
    )
    assert highlighter._severity(line) == "expected"


def test_raw_call_line_with_the_expected_context_is_muted(win):
    """The raw call line keeps the call and the status; only its tone changes."""
    highlighter = _highlighter()
    line = (
        "[15:04:05] GET https://demo.example/api/datasets/:persistentId/versions/"
        ":draft → 401 (42 ms) — EXPECTED: this account may not read the draft"
    )
    assert highlighter._severity(line) == "expected"


def test_log_highlighter_keeps_real_errors_red(win):
    highlighter = _highlighter()
    line = "[15:04:05] ERROR: GET https://demo.example/api/search → 500 (12 ms)"
    assert highlighter._severity(line) == "error"


def test_an_error_line_that_mentions_expected_stays_an_error(win):
    """The server's words in a body never decide the app's verdict."""
    highlighter = _highlighter()
    line = (
        "[15:04:05] ERROR: GET https://demo.example/api/search → 500 — "
        "the response was not what we expected"
    )
    assert highlighter._severity(line) == "error"


def test_expected_word_is_a_severity_word(win):
    highlighter = _highlighter()
    # The severity word must be recognised, or it is painted like any
    # other word instead of the muted expected tone.
    match = highlighter._re_level.search("EXPECTED: a refusal")
    assert match is not None
    assert match.group(1) == "EXPECTED"
