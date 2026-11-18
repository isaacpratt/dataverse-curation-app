"""Auto-Checks affordances (dv-bph): findings filter, skipped-row aggregation.

W2: the Auto-Checks card carries the same class of filter as the metadata
card (All / Errors / Warnings). W1: identical "skipped — missing library"
rows for one check collapse into a single count row. W3: the card's (i)
text is split into short labelled lines (see test_section_info).
"""

from PySide6.QtWidgets import QLabel


def _report():
    from engine.checks.base import CheckResult
    from engine.report import DatasetReport, FileEntry

    def skip(path):
        return CheckResult(
            check_id="format.spss",
            level="warning",
            passed=True,
            message="Optional library pyreadstat is not installed",
            details={"skipped": True},
        )

    def err(path):
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
        ],
        files=[
            FileEntry(path=f"data/{n}.sav", size_bytes=10,
                      mime_type="application/x-spss-sav", checks=[skip(f"data/{n}.sav")])
            for n in range(5)
        ] + [
            FileEntry(path="data/bad.xml", size_bytes=10,
                      mime_type="application/xml", checks=[err("data/bad.xml")]),
        ],
    )


def _view(qapp, tmp_path):
    from pathlib import Path

    from config import Config
    from ui.dataset_detail import DatasetDetailView

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


def _rows(view):
    """Return the Auto-Checks rows, in card order (the card body is a layout)."""
    out = []
    lay = view._auto_body
    for i in range(lay.count()):
        item = lay.itemAt(i)
        widget = item.widget() if item is not None else None
        if widget is not None and widget.objectName() == "AutoCheckRow":
            out.append(widget)
    return out


def _shown_kinds(view):
    """Return the severity classes of the rows the filter leaves on show."""
    return sorted(
        str(r.property("auto_class") or "?")
        for r in _rows(view)
        if not r.isHidden()
    )


def test_skipped_rows_collapse_into_one_affordances(qapp, tmp_path):
    view = _view(qapp, tmp_path)
    view.show()
    for _ in range(5):
        qapp.processEvents()
    view._refresh_curation_preview()
    rows = [
        r for r in _rows(view)
        if r.property("auto_class") == "skipped"
    ]
    assert len(rows) == 1, "five identical skipped rows must collapse into one"
    text = " ".join(label.text() for label in rows[0].findChildren(QLabel))
    assert "5" in text, "collapsed row carries the count"
    tip = rows[0].toolTip()
    assert "data/0.sav" in tip and "data/4.sav" in tip, "the files stay in the tooltip"
    err_rows = [
        r for r in _rows(view)
        if r.property("auto_class") == "failed-error"
    ]
    assert len(err_rows) == 1
    view.deleteLater()


def test_findings_filter_narrows_and_restores(qapp, tmp_path):
    view = _view(qapp, tmp_path)
    view.show()
    for _ in range(5):
        qapp.processEvents()
    view._refresh_curation_preview()

    assert sorted(_shown_kinds(view)) == ["failed-error", "passed", "skipped"]

    view._auto_filter.setCurrentIndex(1)  # Errors
    assert sorted(_shown_kinds(view)) == ["failed-error"]

    view._auto_filter.setCurrentIndex(2)  # Warnings
    assert sorted(_shown_kinds(view)) == ["skipped"]

    view._auto_filter.setCurrentIndex(0)  # All
    assert sorted(_shown_kinds(view)) == ["failed-error", "passed", "skipped"]
    view.deleteLater()


def test_filter_keeps_the_card_rows_intact(qapp, tmp_path):
    """Filtering hides rows; it never drops them (the count stays put)."""
    view = _view(qapp, tmp_path)
    view.show()
    for _ in range(5):
        qapp.processEvents()
    view._refresh_curation_preview()
    before = len(_rows(view))
    view._auto_filter.setCurrentIndex(1)  # Errors
    assert len(_rows(view)) == before
    view._auto_filter.setCurrentIndex(0)  # All
    assert len(_rows(view)) == before
    view.deleteLater()


def test_planned_rows_are_hidden_by_a_severity_filter(qapp, tmp_path):
    """Before a run the card lists planned checks.

    A severity filter narrows the card to findings, so the planned rows
    fold away.
    """
    from config import Config
    from ui.dataset_detail import DatasetDetailView

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
    view._auto_filter.setCurrentIndex(1)  # Errors
    assert "planned" not in _shown_kinds(view)
    view._auto_filter.setCurrentIndex(0)  # All
    assert "planned" in _shown_kinds(view)
    view.deleteLater()


def test_filter_combo_is_labelled(qapp, tmp_path):
    """The filter reads like the metadata card's: a labelled dropdown."""
    from ui.i18n import t

    view = _view(qapp, tmp_path)
    combo = view._auto_filter
    assert combo.count() == 3
    assert combo.itemText(0) == t("detail.auto_checks.filter_all")
    assert combo.itemData(1) == "error"
    assert combo.itemData(2) == "warning"
    assert combo.toolTip(), "the filter explains itself"
    view.deleteLater()
