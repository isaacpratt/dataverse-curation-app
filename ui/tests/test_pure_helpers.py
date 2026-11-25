"""Table-driven coverage for the pure helpers around the views (dv-ni3)."""

from __future__ import annotations

from typing import Any

import pytest
from PySide6.QtGui import QColor, QTextCharFormat, QTextDocument

from engine.checks.base import CheckResult
from ui.i18n import t


def _result(
    level: str,
    passed: bool,
    check_id: str = "format.csv.structure",
    details: dict[str, Any] | None = None,
) -> CheckResult:
    return CheckResult(check_id, level, passed, "a message", details=details or {})


@pytest.mark.parametrize(
    ("checks", "label"),
    [
        ([], "No automated check"),
        ([_result("error", False)], "Error"),
        ([_result("warning", False)], "Warning"),
        ([_result("info", False, details={"skipped": True})], "Skipped"),
        (
            [_result("info", True), _result("info", False, details={"skipped": True})],
            "Clean",
        ),
        ([_result("info", True)], "Clean"),
    ],
)
def test_status_text_selects_the_summary(checks: list[CheckResult], label: str) -> None:
    from ui.status_text import status_text

    assert status_text(checks).startswith(label)


@pytest.mark.parametrize(
    ("level", "passed", "token"),
    [
        ("error", False, "status.badges.error"),
        ("warning", False, "status.badges.warning"),
        ("skipped", False, "status.badges.skipped"),
        ("info", True, "status.badges.passed"),
    ],
)
def test_badge_text(level: str, passed: bool, token: str) -> None:
    from ui.status_text import badge_text

    result = (
        _result("info", False, details={"skipped": True})
        if level == "skipped"
        else _result(level, passed)
    )
    assert badge_text(result) == t(token)


def test_check_titles_and_tooltips() -> None:
    from ui.check_titles import check_summary, check_title, format_details_tooltip

    assert check_title("format.csv.structure") == "CSV Structure"
    assert "unrecognised" in check_title("does.not.exist").lower()
    summary = check_summary(_result("error", False), "a.csv")
    assert summary
    assert "a.csv" not in summary
    tip = format_details_tooltip(_result("error", False), "a.csv")
    assert "a message" in tip.lower()
    assert format_details_tooltip(_result("info", True, "does.not.exist"), "b.csv")


@pytest.mark.parametrize(
    ("wanted", "state", "expected"),
    [
        ("All", "DRAFT", True),
        ("PENDING", "DRAFT", True),
        ("PENDING", "IN REVIEW", True),
        ("PENDING", "RELEASED", False),
        ("PUBLISHED", "RELEASED", True),
        ("DRAFT", "DRAFT", True),
        ("IN REVIEW", "IN REVIEW", True),
        ("DEACCESSIONED", "DEACCESSIONED", True),
        ("CUSTOM", "CUSTOM", True),
        ("CUSTOM", "DRAFT", False),
    ],
)
def test_dashboard_state_predicate(wanted: str, state: str, expected: bool) -> None:
    from ui.dashboard import DashboardView

    assert DashboardView._matches_state({"state": state}, wanted.upper(), wanted) is expected


def test_dashboard_size_cell_tooltips(qapp: Any) -> None:
    from ui.dashboard import DashboardView

    class _Item:
        def __init__(self) -> None:
            self.tip = ""
            self.dimmed = False

        def setToolTip(self, text: str) -> None:
            self.tip = text

        def setForeground(self, brush: Any) -> None:
            self.dimmed = True

    unknown = t("dashboard.display_state.unknown")
    plain = _Item()
    DashboardView._decorate_size_cell({}, plain, unknown)
    assert plain.tip == t("dashboard.table.size_unknown")

    enriched = _Item()
    DashboardView._decorate_size_cell({"size_enriched": True}, enriched, "1.0 KB")
    assert "1.0 KB" in enriched.tip

    cached = _Item()
    DashboardView._decorate_size_cell({"size_from_cache": True}, cached, "2.0 KB")
    assert "2.0 KB" in cached.tip

    pending = _Item()
    DashboardView._decorate_size_cell({"size_pending": True}, pending, unknown)
    assert pending.tip == t("dashboard.table.size_pending")
    assert not pending.dimmed


def test_log_highlighter_colours(qapp: Any) -> None:
    from ui.log_panel import LogHighlighter

    doc = QTextDocument()
    highlighter = LogHighlighter(doc)
    doc.setPlainText("[12:00:00] ERROR: broken\n[12:00:01] EXPECTED: allowed\n[12:00:02] a line")
    highlighter.rehighlight()
    colours: set[str] = set()
    count = 0
    for block_num in range(doc.blockCount()):
        for fmt in doc.findBlockByNumber(block_num).layout().formats():
            count += 1
            if isinstance(fmt.format, QTextCharFormat):
                colours.add(QColor(fmt.format.foreground().color()).name())
    assert colours
    assert count >= 3


def test_i18n_placeholder_fallback() -> None:
    rendered = t("app.cli.run_failed", exc="boom")
    assert "boom" in rendered
    assert rendered != "app.cli.run_failed"
