"""Two top-level check sections on the dataset page (dv-yg6).

Dataset checks holds the metadata and automated cards; File checks is the
renamed manifest and owns every per-file result. No finding is printed in
both places, and each section has its own summary.
"""

from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QLabel

_EXE = "inventory.executables"
_CSV = "format.csv.openable"


def _result(check_id: Any, level: Any, passed: Any, message: Any, path: Any = ""):
    from engine.checks.base import CheckResult

    return CheckResult(
        check_id=check_id,
        level=level,
        passed=passed,
        message=message,
        details={} if not path else {"path": path},
    )


def _report() -> Any:
    from engine.report import DatasetReport, FileEntry

    return DatasetReport(
        persistent_id="doi:1",
        label="study",
        engine_version="t",
        dataset_checks=[
            _result("metadata.license", "warning", True, "license present"),
            _result(_EXE, "error", False, "1 executable found"),
        ],
        files=[
            FileEntry(
                path="a.csv",
                size_bytes=10,
                mime_type="text/csv",
                checks=[
                    _result(_CSV, "error", False, "ragged rows", path="data/a.csv"),
                ],
            ),
            FileEntry(
                path="b.csv",
                size_bytes=10,
                mime_type="text/csv",
                checks=[
                    _result("format.csv.structure", "warning", True, "missing column"),
                ],
            ),
        ],
    )


def _view(qapp: Any, tmp_path: Any):
    from curation.config import Config
    from ui.dataset import DatasetDetailView

    cfg = Config()
    cfg.app.workspace = tmp_path
    staged = Path(tmp_path) / "downloads" / "doi_10.5072_FK2_AF" / "files"
    staged.mkdir(parents=True, exist_ok=True)
    (staged / "a.csv").write_text("a,b\n1,2\n")
    (staged / "b.csv").write_text("a,b\n3,4\n")
    view = DatasetDetailView(
        cfg,
        "doi:10.5072/FK2/AF",
        "Two sections",
        cached_metadata={"id": 1},
        cached_inventory=[],
    )
    view._report = _report()
    view.show()
    for _ in range(6):
        qapp.processEvents()
    view._refresh_curation_preview()
    view._refresh_files_placeholder()
    for _ in range(4):
        qapp.processEvents()
    return view


def _headings(view: Any):
    return [
        view._dataset_checks_heading.text(),
        view._file_checks_heading.text(),
    ]


def _auto_rows(view: Any):
    out: list[Any] = []
    for i in range(view._auto_body.count()):
        widget = view._auto_body.itemAt(i).widget()
        if widget is not None and widget.objectName() == "AutoCheckRow":
            out.append(widget)
    return out


def _tree_texts(view: Any):
    from PySide6.QtCore import QModelIndex

    texts: list[str] = []
    model = view._file_tree.model()

    def walk(parent: Any = None) -> None:
        if parent is None:
            parent = QModelIndex()
        for row in range(model.rowCount(parent)):
            for column in range(model.columnCount(parent)):
                texts.append(str(model.index(row, column, parent).data() or ""))
            walk(model.index(row, 0, parent))

    walk()
    return texts


def test_two_headings_in_order(qapp, tmp_path):
    view = _view(qapp, tmp_path)
    try:
        assert _headings(view) == ["Dataset checks", "File checks"]
        # The cards sit under their heading, in the same order.
        widgets = [view._main_wrap.itemAt(i).widget() for i in range(view._main_wrap.count())]
        assert widgets.index(view._dataset_checks_header) < widgets.index(view._meta_card)
        assert widgets.index(view._meta_card) < widgets.index(view._auto_card)
        assert widgets.index(view._file_checks_header) < widgets.index(view._file_card)
    finally:
        view.deleteLater()


def test_no_finding_is_listed_twice(qapp, tmp_path):
    view = _view(qapp, tmp_path)
    try:
        dataset_text = " ".join(
            label.text() for row in _auto_rows(view) for label in row.findChildren(QLabel)
        )
        file_text = " ".join(_tree_texts(view))
        assert "executable" in dataset_text.lower()
        assert "executable" not in file_text.lower(), "dataset finding stays out of File checks"
        assert "ragged" not in dataset_text.lower(), "per-file finding stays out of Dataset checks"
        assert "ragged" in file_text.lower(), "the file finding is in File checks"
        # The failed CSV check appears once, in the file tree only.
        assert sum("ragged" in text.lower() for text in _tree_texts(view)) >= 1
        assert sum("ragged" in text for text in [dataset_text]) == 0
    finally:
        view.deleteLater()


def test_each_section_has_its_own_summary(qapp, tmp_path):
    from engine.status import summarize

    view = _view(qapp, tmp_path)
    try:
        report = view._report
        dataset = summarize(report.dataset_checks)
        files = summarize([c for f in report.files for c in f.checks])
        assert str(dataset["failed-error"]) in view._auto_summary.text()
        file_summary = view._file_checks_summary.text()
        assert f"{files['passed']} passed" in file_summary
        assert f"{files['failed-error']} errors" in file_summary
        assert f"{files['failed-warning']} warn" in file_summary
        assert f"{files['skipped']} skipped" in file_summary
        assert "0 passed" not in view._auto_summary.text() or dataset["passed"] == 0
    finally:
        view.deleteLater()


def test_filters_stay_separate(qapp, tmp_path):
    view = _view(qapp, tmp_path)
    try:
        before = len(_auto_rows(view))
        view._auto_filter.setCurrentIndex(1)  # Errors
        assert len(_auto_rows(view)) == before, "filtering hides, never drops"
        visible = [row for row in _auto_rows(view) if not row.isHidden()]
        assert len(visible) == 1
        assert "executable" in " ".join(label.text() for label in visible[0].findChildren(QLabel))
        view._scan_filter.setCurrentIndex(1)  # File checks issues filter
        for _ in range(3):
            qapp.processEvents()
        assert view._auto_filter.currentIndex() == 1, "the two filters are independent"
    finally:
        view.deleteLater()


def test_the_rail_checks_step_targets_dataset_checks(qapp, tmp_path):
    view = _view(qapp, tmp_path)
    try:
        anchors = []
        original = view._goto_section

        def capture(attr):
            anchors.append(attr)
            original(attr)

        view._goto_section = capture
        view._on_workflow_step("checks")
        assert anchors == ["_dataset_checks_heading"]
    finally:
        view.deleteLater()
