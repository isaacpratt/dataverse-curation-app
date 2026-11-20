"""Probe: Dataset checks above File checks at 1440 and 960 (dv-yg6).

Loads a cached report with one dataset-level finding and two per-file
findings, then checks the two headings are visible in order, the file tree
is painted, neither card clips, and no finding text appears in both
sections. Screenshots of the main column at both widths are saved.

Run: python tools/probes/probe_check_sections.py
"""

from __future__ import annotations

import sys

from _common import Report, boot, save_artifact


def _result(check_id, level, passed, message):
    from engine.checks.base import CheckResult

    return CheckResult(check_id=check_id, level=level, passed=passed, message=message, details={})


def _report():
    from engine.report import DatasetReport, FileEntry

    return DatasetReport(
        persistent_id="doi:10.5072/FK2/SECTIONS",
        label="Two sections",
        engine_version="t",
        dataset_checks=[
            _result("metadata.license", "warning", True, "license present"),
            _result("inventory.executables", "error", False, "executable file found"),
        ],
        files=[
            FileEntry(
                path="a.csv",
                size_bytes=10,
                mime_type="text/csv",
                checks=[_result("format.csv.openable", "error", False, "ragged rows")],
            ),
            FileEntry(
                path="b.csv",
                size_bytes=10,
                mime_type="text/csv",
                checks=[_result("format.csv.structure", "warning", True, "missing column")],
            ),
        ],
    )


def _tree_texts(view):
    from PySide6.QtCore import QModelIndex

    model = view._file_tree.model()
    out = []

    def walk(parent=None):
        if parent is None:
            parent = QModelIndex()
        for row in range(model.rowCount(parent)):
            for column in range(model.columnCount(parent)):
                out.append(str(model.index(row, column, parent).data() or ""))
            walk(model.index(row, 0, parent))

    walk()
    return out


def main() -> int:
    app, cfg = boot()
    from PySide6.QtCore import QModelIndex
    from PySide6.QtWidgets import QLabel

    from ui.dataset import DatasetDetailView

    report = Report("two check sections")
    staged = cfg.app.workspace / "downloads" / "doi_10.5072_FK2_SECTIONS" / "files"
    staged.mkdir(parents=True, exist_ok=True)
    (staged / "a.csv").write_text("a,b\n1,2\n")
    (staged / "b.csv").write_text("a,b\n3,4\n")

    view = DatasetDetailView(
        cfg,
        "doi:10.5072/FK2/SECTIONS",
        "Two sections",
        cached_metadata={"id": 1},
        cached_inventory=[],
    )
    view._report = _report()
    view.resize(1440, 900)
    view.show()
    for _ in range(10):
        app.processEvents()
    view._refresh_curation_preview()
    view._refresh_files_placeholder()
    for _ in range(6):
        app.processEvents()

    headings = [
        view._dataset_checks_heading.text(),
        view._file_checks_heading.text(),
    ]
    report.check(
        headings == ["Dataset checks", "File checks"],
        "both headings are visible in order",
        f"headings={headings}",
    )

    rows = []
    for i in range(view._auto_body.count()):
        widget = view._auto_body.itemAt(i).widget()
        if widget is not None and widget.objectName() == "AutoCheckRow":
            rows.append(widget)
    dataset_text = " ".join(
        label.text() for row in rows for label in row.findChildren(QLabel)
    ).lower()
    file_text = " ".join(_tree_texts(view)).lower()
    report.check(
        "executable" in dataset_text and "executable" not in file_text,
        "the dataset finding appears only in Dataset checks",
    )
    report.check(
        "ragged" not in dataset_text and "ragged" in file_text,
        "the file finding appears only in File checks",
    )
    report.check("a.csv" in file_text and "b.csv" in file_text, "both files are painted")

    problems = []
    for width, height in ((1440, 900), (960, 720)):
        view.resize(width, height)
        for _ in range(10):
            app.processEvents()
        for card in (view._meta_card, view._auto_card, view._file_card):
            if card.width() > view._main_wrap.parentWidget().width():
                problems.append((width, type(card).__name__, card.width()))
        report.check(
            view._file_tree.model().rowCount(QModelIndex()) > 0,
            f"the file tree is painted at {width}",
        )
        path = save_artifact(view, f"check_sections_{width}x{height}.png")
        print(f"  [note] screenshot: {path.name}")
    report.check(not problems, "no card clips at either width", f"problems={problems}")

    view.deleteLater()
    for _ in range(2):
        app.processEvents()
    return report.finish()


if __name__ == "__main__":
    sys.exit(main())
