"""dv-r0z / dv-dcd: human check names, prose verdicts, prose tooltips.

The File Manifest must never show a check id, a PASS/WARN badge in the Scan
column, or a filename the row already names. The Auto-Checks card must name
a check the same way and say what was found.
"""

import ast
from pathlib import Path
from typing import Any

from engine.checks.base import CheckResult
from engine.report import DatasetReport, FileEntry


def _report(checks: Any, path: Any = "CA-TP4-HH.csv"):
    return DatasetReport(
        persistent_id="doi:10.5072/FK2/EXAMPLE",
        label="Example",
        engine_version="test",
        files=[FileEntry(path=path, size_bytes=10, mime_type="text/csv", checks=checks)],
    )


def _tree(report: Any, dispositions: Any = None):
    from ui.checks_tree import build_tree_model

    rows = [(f.path, f.size_bytes, "CSV", "") for f in report.files]
    return build_tree_model(rows, report=report, dispositions=dispositions)


# -- naming (the engine registry is the single source of titles) -------------


def test_check_title_reads_the_engine_registry():
    from ui.check_titles import check_title

    assert check_title("format.csv.openable") == "CSV Openable"
    assert check_title("format.images.valid") == "Image Validity"
    assert check_title("inventory.executables") == "Executable Files"
    assert check_title("inventory.zero_byte") == "Zero-Byte Files"


def test_check_title_is_total_for_unknown_ids():
    from ui.check_titles import check_title

    text = check_title("format.unseen.thing")
    assert "format.unseen.thing" in text


def test_every_check_title_covers_every_guidance_entry():
    """One registry: a check with guidance always has a name too."""
    from engine.checks import guidance

    assert set(guidance.TITLES) == set(guidance.GUIDANCE)


# -- the verdict sentence ----------------------------------------------------


def test_summary_strips_the_filename_the_engine_prefixes():
    from ui.check_titles import check_summary

    result = CheckResult(
        check_id="format.csv.openable",
        level="info",
        passed=True,
        message="CA-TP4-HH.csv: parsed (ascii)",
    )
    assert check_summary(result, "CA-TP4-HH.csv") == "Parsed (ascii)"


def test_summary_collapses_whitespace_and_capitalises():
    from ui.check_titles import check_summary

    result = CheckResult("format.csv.openable", "info", True, "   parsed   (ascii)  ")
    assert check_summary(result) == "Parsed (ascii)"


def test_summary_keeps_a_sentence_intact_without_a_path():
    from ui.check_titles import check_summary

    result = CheckResult("inventory.extensions", "info", True, "12 files; .csv: 5, .png: 7")
    assert check_summary(result) == "12 files; .csv: 5, .png: 7"


# -- tooltips ---------------------------------------------------------------


def test_tooltip_is_prose_never_raw_json_or_the_id():
    from ui.check_titles import format_details_tooltip

    result = CheckResult(
        check_id="format.images.valid",
        level="info",
        passed=True,
        message="CA-TP4.png: valid PNG image (875x656, RGB)",
        details={"width": 875, "height": 656, "mode": "RGB"},
    )
    tip = format_details_tooltip(result, "CA-TP4.png")
    assert "Image Validity" in tip
    assert "Valid PNG image (875x656, RGB)" in tip
    assert "Width: 875" in tip
    assert "Height: 656" in tip
    assert "format.images.valid" not in tip
    assert "{" not in tip
    assert "}" not in tip


def test_tooltip_keeps_the_why_and_how_of_a_finding():
    """dv-lfn's guidance survives the prose rewrite (it used to sit after JSON)."""
    from ui.check_titles import format_details_tooltip

    result = CheckResult(
        check_id="format.csv.pii",
        level="error",
        passed=False,
        message="a.csv: 2 email addresses found",
    )
    tip = format_details_tooltip(result, "a.csv")
    assert "Why this matters:" in tip
    assert "How to fix:" in tip


def test_skipped_tooltip_carries_the_reason():
    from ui.check_titles import format_details_tooltip

    result = CheckResult(
        check_id="format.spss.openable",
        level="info",
        passed=True,
        message="a.sav: label scan skipped (pyreadstat not installed)",
        details={"skipped": True, "reason": "pyreadstat not installed"},
    )
    assert "Skipped: pyreadstat not installed" in format_details_tooltip(result, "a.sav")


def test_state_words():
    from ui.check_titles import check_state

    assert check_state(CheckResult("format.csv.openable", "info", True, "ok")) == "Complete"
    assert (
        check_state(CheckResult("inventory.zero_byte", "error", False, "oops")) == "Needs attention"
    )
    assert (
        check_state(
            CheckResult("format.spss.openable", "info", True, "s", details={"skipped": True})
        )
        == "Skipped"
    )


# -- the File Manifest rows --------------------------------------------------


def test_manifest_row_names_the_check_and_explains_the_verdict(qapp):
    from ui.checks_tree import COLUMNS

    model = _tree(
        _report(
            [
                CheckResult(
                    check_id="format.images.valid",
                    level="info",
                    passed=True,
                    message="CA-TP4-HH.csv: valid PNG image (875x656, RGB)",
                )
            ]
        )
    )
    file_item = model.item(0, 0)
    check_name = file_item.child(0, 0)
    check_scan = file_item.child(0, 3)
    assert check_name.text() == "Image Validity"
    assert check_scan.text() == "Valid PNG image (875x656, RGB)"
    assert "PASS" not in check_scan.text()
    assert "CA-TP4-HH.csv" not in check_scan.text()
    assert COLUMNS[3] == "Scan"


def test_manifest_check_row_keeps_its_status_icon(qapp):
    from ui.checks_tree import _KIND_ROLE

    model = _tree(_report([CheckResult("inventory.zero_byte", "error", False, "a.csv: empty")]))
    item = model.item(0, 0).child(0, 0)
    assert item.icon().isNull() is False
    assert item.data(_KIND_ROLE)["check_id"] == "inventory.zero_byte"


def test_manifest_disposition_still_joins_the_scan_text(qapp):
    """dv-32x: the resolved label rides after the verdict, not instead of it."""
    from curation.storage import finding_key

    result = CheckResult("format.csv.structure", "warning", False, "a.csv: ragged rows")
    key = finding_key(result.check_id, "a.csv", result.message)
    model = _tree(
        _report([result], path="a.csv"),
        dispositions={key: {"disposition": "wontfix", "note": ""}},
    )
    scan = model.item(0, 0).child(0, 3).text()
    assert scan.startswith("Ragged rows")
    assert scan != "Ragged rows"


# -- the Auto-Checks card ----------------------------------------------------


class _Bare:
    """Just enough object for ``_auto_row``: no dispositions in these rows."""

    def _dispositions_map(self):
        return {}

    def _finding_overflow_button(self, text):
        from ui.dataset import DatasetDetailView

        return DatasetDetailView._finding_overflow_button(self, text)  # type: ignore[arg-type]


def _auto_row(title: Any, desc: Any, passed: Any, level: Any, badge: Any = None):
    from ui.dataset import DatasetDetailView

    return DatasetDetailView._auto_row(_Bare(), title, desc, passed, level, badge)  # type: ignore[arg-type]


def test_auto_row_renders_the_name_as_the_heading(qapp):
    from PySide6.QtWidgets import QLabel

    frame = _auto_row("Zero-Byte Files", "2 file(s) are empty: a.txt, b.txt", False, "error")
    texts = [w.text() for w in frame.findChildren(QLabel)]
    assert "Zero-Byte Files" in texts
    assert any("2 file(s) are empty" in text for text in texts)


def test_auto_checks_name_every_row_with_check_title():
    """dv-dcd regression: no call site may pass a raw check id as the name."""
    package = Path(__file__).resolve().parents[1] / "dataset"
    offenders = []
    for source in sorted(package.glob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            if getattr(fn, "attr", "") != "_auto_row" or not node.args:
                continue
            first = node.args[0]
            named = isinstance(first, ast.Call) and getattr(first.func, "id", "") == "check_title"
            if not named:
                offenders.append(f"{source.name}:{node.lineno}")
    assert offenders == [], (
        f"Auto-Checks rows must be named with check_title(); raw ids at {offenders}"
    )
