"""Complexity report: the advisory view over the C901 gate."""

from __future__ import annotations

from tools.complexity_report import BUDGET, render_report

BLOCKS = [
    {
        "file": "ui/workers.py",
        "name": "run",
        "type": "function",
        "line": 148,
        "complexity": 82,
        "rank": "F",
    },
    {
        "file": "ui/dashboard.py",
        "name": "small",
        "type": "function",
        "line": 10,
        "complexity": 3,
        "rank": "A",
    },
]

MI = {"ui/workers.py": 12.5, "ui/dashboard.py": 74.2}


def test_report_lists_over_budget_blocks() -> None:
    text = render_report(BLOCKS, MI)
    assert "blocks over the budget (> 12): **1**" in text
    assert "`run`" in text
    assert "82" in text


def test_report_marks_the_budget() -> None:
    text = render_report(BLOCKS, MI)
    assert str(BUDGET) in text


def test_report_handles_an_empty_tree() -> None:
    text = render_report([], {})
    assert "blocks analysed: **0**" in text
    assert "None" in text


def test_report_explains_the_radon_ruff_difference() -> None:
    text = render_report(BLOCKS, MI)
    assert "radon" in text
    assert "ruff" in text
