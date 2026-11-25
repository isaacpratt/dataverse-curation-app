"""Automated checks affordances (dv-bph, dv-yg6): the findings filter.

After the two-section split this card holds only dataset-level results;
per-file findings live in File checks. The severity filter narrows the
card to findings (All / Errors / Warnings).
"""

from typing import Any

from PySide6.QtWidgets import QLabel


def _report() -> Any:
    from engine.checks.base import CheckResult
    from engine.report import DatasetReport, FileEntry

    def skip(path: Any):
        return CheckResult(
            check_id="format.spss",
            level="warning",
            passed=True,
            message="Optional library pyreadstat is not installed",
            details={"skipped": True},
        )

    def err(path: Any):
        return CheckResult(
            check_id="format.xml",
            level="error",
            passed=False,
            message="malformed XML",
            details={},
        )

    return DatasetReport(
        persistent_id="doi:1",
        label="study",
        engine_version="t",
        dataset_checks=[
            CheckResult(
                check_id="metadata.license",
                level="warning",
                passed=True,
                message="ok",
                details={},
            ),
            CheckResult(
                check_id="inventory.executables",
                level="error",
                passed=False,
                message="1 executable found",
                details={},
            ),
            CheckResult(
                check_id="inventory.unchecked_types",
                level="warning",
                passed=False,
                message="2 files with no automated check",
                details={},
            ),
        ],
        files=[
            FileEntry(
                path=f"data/{n}.sav",
                size_bytes=10,
                mime_type="application/x-spss-sav",
                checks=[skip(f"data/{n}.sav")],
            )
            for n in range(5)
        ]
        + [
            FileEntry(
                path="data/bad.xml",
                size_bytes=10,
                mime_type="application/xml",
                checks=[err("data/bad.xml")],
            ),
        ],
    )


def _view(qapp: Any, tmp_path: Any):
    from pathlib import Path

    from curation.config import Config
    from ui.dataset import DatasetDetailView

    cfg = Config()
    cfg.app.workspace = tmp_path
    # The refresh's file list comes from the staged directory; materialize
    # the same files the report covers so the report branch runs.
    staged = Path(tmp_path) / "downloads" / "doi_10.5072_FK2_AF" / "files"
    staged.mkdir(parents=True, exist_ok=True)
    for n in range(5):
        (staged / f"{n}.sav").write_bytes(b"")
    (staged / "bad.xml").write_bytes(b"<")
    v = DatasetDetailView(
        cfg,
        "doi:10.5072/FK2/AF",
        "Affordances test",
        cached_metadata={"id": 1},
        cached_inventory=[],
    )
    v._report = _report()
    return v


def _rows(view: Any):
    """Return the Auto-Checks rows, in card order (the card body is a layout)."""
    out = []
    lay = view._auto_body
    for i in range(lay.count()):
        item = lay.itemAt(i)
        widget = item.widget() if item is not None else None
        if widget is not None and widget.objectName() == "AutoCheckRow":
            out.append(widget)
    return out


def _shown_kinds(view: Any):
    """Return the severity classes of the rows the filter leaves on show."""
    return sorted(str(r.property("auto_class") or "?") for r in _rows(view) if not r.isHidden())


def test_per_file_findings_stay_in_file_checks(qapp, tmp_path):
    """The dataset card lists dataset results only — no file paths."""
    view = _view(qapp, tmp_path)
    view.show()
    for _ in range(5):
        qapp.processEvents()
    view._refresh_curation_preview()
    kinds = [str(r.property("auto_class") or "?") for r in _rows(view)]
    assert sorted(kinds) == ["failed-error", "failed-warning", "passed"]
    labels = [label.text() for r in _rows(view) for label in r.findChildren(QLabel)]
    assert not [text for text in labels if ".sav" in text or ".xml" in text]
    view.deleteLater()


def test_unknown_file_types_row_wears_the_warning_face(qapp, tmp_path):
    """inventory.unchecked_types must read as a warning, never an error (dv-gc9)."""
    from engine.status import classify

    view = _view(qapp, tmp_path)
    try:
        view.show()
        for _ in range(5):
            qapp.processEvents()
        view._refresh_curation_preview()
        rows = _rows(view)
        # Locate the row by its title label instead of message text matching.
        target = None
        for r in rows:
            labels = [lbl.text() for lbl in r.findChildren(QLabel)]
            if any("Unknown File Types" in text for text in labels):
                target = r
                break
        assert target is not None, "the unknown-file-types row must be present"
        sheet = target.styleSheet()
        from ui.theme import (
            STATE_WARNING_BORDER,
            STATE_WARNING_SURFACE,
        )

        assert STATE_WARNING_SURFACE in sheet, sheet
        assert STATE_WARNING_BORDER in sheet, sheet
        badges = [
            lbl.text()
            for lbl in target.findChildren(QLabel)
            if lbl.text() in ("Warning", "Error", "Passed")
        ]
        assert "Warning" in badges, badges
        assert "Error" not in badges, badges
        # The engine result itself is a warning.
        result = next(
            c
            for c in view._report.dataset_checks
            if c.check_id == "inventory.unchecked_types"
        )
        assert classify(result) == "failed-warning"
    finally:
        view.deleteLater()


def test_findings_filter_narrows_and_restores(qapp, tmp_path):
    view = _view(qapp, tmp_path)
    view.show()
    for _ in range(5):
        qapp.processEvents()
    view._refresh_curation_preview()

    assert sorted(_shown_kinds(view)) == ["failed-error", "failed-warning", "passed"]

    view._auto_filter.setCurrentIndex(4)  # Error
    assert sorted(_shown_kinds(view)) == ["failed-error"]

    view._auto_filter.setCurrentIndex(3)  # Warning
    assert sorted(_shown_kinds(view)) == ["failed-warning"]

    view._auto_filter.setCurrentIndex(1)  # Complete
    assert sorted(_shown_kinds(view)) == ["passed"]

    view._auto_filter.setCurrentIndex(2)  # Incomplete
    assert sorted(_shown_kinds(view)) == ["failed-error", "failed-warning"]

    view._auto_filter.setCurrentIndex(0)  # All
    assert sorted(_shown_kinds(view)) == ["failed-error", "failed-warning", "passed"]
    view.deleteLater()


def test_filter_keeps_the_card_rows_intact(qapp, tmp_path):
    """Filtering hides rows; it never drops them (the count stays put)."""
    view = _view(qapp, tmp_path)
    view.show()
    for _ in range(5):
        qapp.processEvents()
    view._refresh_curation_preview()
    before = len(_rows(view))
    view._auto_filter.setCurrentIndex(4)  # Error
    assert len(_rows(view)) == before
    view._auto_filter.setCurrentIndex(0)  # All
    assert len(_rows(view)) == before
    view.deleteLater()


def test_planned_rows_are_hidden_by_a_severity_filter(qapp, tmp_path):
    """Before a run the card lists planned checks.

    A severity filter narrows the card to findings, so the planned rows
    fold away.
    """
    from curation.config import Config
    from ui.dataset import DatasetDetailView

    cfg = Config()
    cfg.app.workspace = tmp_path
    staged = tmp_path / "downloads" / "doi_10.5072_FK2_AF" / "files"
    staged.mkdir(parents=True, exist_ok=True)
    (staged / "a.sav").write_bytes(b"")
    view = DatasetDetailView(
        cfg,
        "doi:10.5072/FK2/AF",
        "Planned rows",
        cached_metadata={"id": 1},
        cached_inventory=[],
    )
    view.show()
    for _ in range(5):
        qapp.processEvents()
    view._refresh_curation_preview()
    assert "planned" in _shown_kinds(view)
    assert view._auto_filter is not None
    view._auto_filter.setCurrentIndex(4)  # Error
    assert "planned" not in _shown_kinds(view)
    view._auto_filter.setCurrentIndex(0)  # All
    assert "planned" in _shown_kinds(view)
    view.deleteLater()


def test_filter_combo_is_labelled(qapp, tmp_path):
    """The filter reads like the metadata card's: a labelled dropdown."""
    from ui.i18n import t

    view = _view(qapp, tmp_path)
    combo = view._auto_filter
    # Unified filter (dv-3d0.3): 6 entries including All issues, Complete,
    # Incomplete, Warning, Error, Skipped.
    assert combo.count() == 6
    assert combo.itemText(0) == t("detail.checks.filter_all")
    assert combo.itemData(1) == "complete"
    assert combo.itemData(2) == "incomplete"
    assert combo.itemData(3) == "warning"
    assert combo.itemData(4) == "error"
    assert combo.itemData(5) == "skipped"
    assert combo.toolTip() == t("detail.checks.filter_tip")
    view.deleteLater()
