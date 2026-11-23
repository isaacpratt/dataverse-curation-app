"""Two top-level check sections on the dataset page (dv-yg6, dv-gfx.5).

Dataset checks holds the metadata checklist and the automated checks in one
card; File checks is the manifest and owns every per-file result. No finding
is printed in both places, and each section has its own summary.
"""

from pathlib import Path
from typing import Any

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


def _headings(view: Any) -> list[str]:
    """Return the two section titles from the cards' own header labels."""
    return [
        view._meta_card.findChildren(type(view._title_lbl))[0].text(),
        view._file_checks_heading.text(),
    ]


def _auto_rows(view: Any):
    out: list[Any] = []
    for i in range(view._auto_body.count()):
        widget = view._auto_body.itemAt(i).widget()
        if widget is not None and widget.objectName() == "AutoCheckRow":
            out.append(widget)
    return out


def test_two_headings_in_order(qapp, tmp_path):
    view = _view(qapp, tmp_path)
    try:
        # One header line per card (dv-gfx.5): the titles are the cards' own.
        assert _headings(view) == ["Dataset checks", "File checks"]
        widgets = [view._main_wrap.itemAt(i).widget() for i in range(view._main_wrap.count())]
        assert widgets.index(view._meta_card) < widgets.index(view._file_card)
        # Metadata checks and automated checks share one card (item 9).
        meta_layout = view._meta_card.layout()
        assert meta_layout is not None
        children = [meta_layout.itemAt(i).widget() for i in range(meta_layout.count())]
        children = [w for w in children if w is not None]
        assert view._auto_card in children
        assert view._auto_card.parent() is view._meta_card
    finally:
        view.deleteLater()


def test_no_finding_is_listed_twice(qapp, tmp_path):
    from PySide6.QtWidgets import QLabel

    view = _view(qapp, tmp_path)
    try:
        dataset_text = " ".join(
            lbl.text() for row in _auto_rows(view) for lbl in row.findChildren(QLabel)
        )
        file_text = " ".join(_tree_texts(view))
        assert "executable" in dataset_text.lower(), dataset_text
        assert "executable" not in file_text.lower(), "dataset finding stays out of File checks"
        assert "ragged" not in dataset_text.lower(), "per-file finding stays out of Dataset checks"
        assert "ragged" in file_text.lower(), "the file finding is in File checks"
    finally:
        view.deleteLater()


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


def test_each_section_has_its_own_summary(qapp, tmp_path):
    from engine.status import summarize

    view = _view(qapp, tmp_path)
    try:
        report = view._report
        assert report is not None
        dataset_summary = summarize(list(report.dataset_checks))
        file_summary = summarize([c for f in report.files for c in f.checks])
        assert view._auto_summary.text()
        assert view._file_checks_summary.text()
        # Dataset checks counts the dataset-level results only.
        assert str(dataset_summary["passed"]) in view._auto_summary.text() or "will run" in (
            view._auto_summary.text()
        )
        # File checks counts the per-file results only.
        assert str(file_summary["passed"]) in view._file_checks_summary.text()
    finally:
        view.deleteLater()
