"""Variable-dictionary draft + manifest coverage suffix (dv-tfy)."""

import csv

import pytest


def _coverage_report():
    from engine.checks.base import CheckResult
    from engine.report import DatasetReport

    result = CheckResult(
        check_id="metadata.var_coverage",
        level="warning",
        passed=False,
        message="1 tabular file(s) without variable documentation: data/x.tab",
        details={
            "coverage": {"data/survey.tab": {"labeled": 2, "total": 3}},
            "variables": {
                "data/survey.tab": {
                    "age": {"label": "Age in years", "type": "numeric"},
                    "sex": {"label": "Sex", "type": "categorical"},
                }
            },
        },
    )
    return DatasetReport(
        persistent_id="doi:1",
        label="x",
        engine_version="t",
        dataset_checks=[result],
    )


def test_variable_coverage_reads_report_details(qapp):
    from ui.checks_tree import variable_coverage

    coverage = variable_coverage(_coverage_report())
    assert coverage["data/survey.tab"] == {"labeled": 2, "total": 3}
    assert variable_coverage(None) == {}


def test_manifest_scan_column_shows_coverage(qapp):
    from ui.checks_tree import build_tree_model

    report = _coverage_report()
    model = build_tree_model(
        [("data/survey.tab", 12, "TAB", "")], report, lambda _p: True
    )
    # "data/survey.tab" gets a folder node; the file row is its child.
    folder = model.item(0, 0)
    scan = folder.child(0, 3).text()
    assert "2/3 variables documented" in scan
    assert "2 of 3 variables have labels" in folder.child(0, 0).toolTip()


@pytest.fixture()
def view(qapp, tmp_path):
    from config import Config
    from ui.dataset_detail import DatasetDetailView

    try:
        cfg = Config.load(None)
    except Exception:
        cfg = Config()
    cfg.app.workspace = tmp_path
    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir()
    staged = dataset_dir / "files"
    staged.mkdir()
    (staged / "survey.tab").write_text("a,b\n1,2\n", encoding="utf-8")

    v = DatasetDetailView.__new__(DatasetDetailView)
    v._pid = "doi:10.5072/FK2/DICT"
    v._config = cfg
    v._ruleset = {}
    v._report = _coverage_report()
    v._inventory = [{"path": "data/survey.tab", "tabular": True}]
    v._client = None
    v._logged = []

    class _StubDl:
        def dataset_dir(self, pid):
            return dataset_dir

        def files_dir(self, pid):
            return staged

        def reports_dir(self, pid):
            return dataset_dir / "reports"

    v._dl_mgr = _StubDl()

    def _log(action, notes="", details=None):
        v._logged.append((action, notes, details))

    v._log_action = _log
    v._status_msgs = []
    v._set_status = lambda msg: v._status_msgs.append(msg)
    return v


def test_draft_dictionary_writes_csv(view, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    target = view._dl_mgr.dataset_dir(view._pid) / "survey-dictionary.csv"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), ""))
    )
    view._on_draft_dictionary()
    assert target.exists()
    with open(target, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == ["variable", "label", "type"]
    assert ["age", "Age in years", "numeric"] in rows
    assert any(a == "dictionary_drafted" for a, _n, _d in view._logged)
    assert view._status_msgs and "draft written" in view._status_msgs[-1]


def test_draft_dictionary_without_variables_is_a_noop(view, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    view._report = None
    called = []
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        staticmethod(lambda *a, **k: called.append(1) or ("", "")),
    )
    monkeypatch.setattr("ui.dialogs.show_info", lambda *a, **k: None)
    view._on_draft_dictionary()
    assert called == []
