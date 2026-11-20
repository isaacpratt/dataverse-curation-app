"""Header actions and the three-button rail (dv-gs5).

The dataset header is reorganised around the three things a curator navigates
to. These tests pin the exact labels and the state rules behind them:

- the DOI chip is the Dataverse link (DRAFT-aware), with the curation-label
  chip beside the publication-status chip;
- Download Dataset / Verify Files lives in the File checks section header;
- Load / Reload Metadata lives in the Dataset checks section header;
- the primary button says Run / Run File / Re-run Automatic Checks based on
  how far the check pass has got, and stages the dataset first if needed;
- the old Export reports button is gone.
"""

from pathlib import Path
from typing import Any

import pytest
from PySide6.QtWidgets import QPushButton, QToolButton

PID = "doi:10.5072/FK2/HEADER"


def _report(with_dataset: bool, with_files: bool) -> Any:
    from engine.checks.base import CheckResult
    from engine.report import DatasetReport, FileEntry

    def result(check_id: str) -> CheckResult:
        return CheckResult(
            check_id=check_id, level="warning", passed=True, message="ok", details={}
        )

    return DatasetReport(
        persistent_id=PID,
        label="Header",
        engine_version="t",
        dataset_checks=[result("metadata.license")] if with_dataset else [],
        files=[
            FileEntry(
                path="a.csv",
                size_bytes=10,
                mime_type="text/csv",
                checks=[result("format.csv.openable")] if with_files else [],
            )
        ],
    )


@pytest.fixture
def view(qapp, tmp_path):
    from curation.config import Config
    from ui.dataset import DatasetDetailView

    cfg = Config()
    cfg.dataverse.base_url = "https://demo.borealisdata.ca"
    cfg.dataverse.api_token = ""
    cfg.app.workspace = tmp_path
    v = DatasetDetailView(
        cfg,
        PID,
        "Header dataset",
        cached_metadata={"latestVersion": {"versionState": "DRAFT"}},
        cached_inventory=[{"path": "a.csv", "size_bytes": 10, "mimeType": "text/csv"}],
    )
    v.show()
    for _ in range(4):
        qapp.processEvents()
    yield v, tmp_path
    v.deleteLater()


def test_rail_buttons_are_real_buttons(view):
    v, _ = view
    rail = v._rail
    assert isinstance(rail.buttons["dataset_checks"], (QPushButton, QToolButton))
    assert list(rail.buttons) == ["dataset_checks", "file_checks", "response"]
    assert rail.buttons["dataset_checks"].text() == "Dataset Checks"
    assert rail.buttons["file_checks"].text() == "File Checks"
    assert rail.buttons["response"].text() == "Response"


def test_doi_chip_is_the_dataverse_link(view):
    v, _ = view
    text = v._id_badge.text()
    assert "<a href=" in text
    assert PID in text
    assert "https://demo.borealisdata.ca/dataset.xhtml?persistentId=" in text
    assert "version=DRAFT" in text
    assert v._id_badge.openExternalLinks()


def test_curation_pill_sits_beside_the_status_pill(view):
    v, _ = view
    assert v._curation_pill.parent() is v._status_pill.parent()
    parent = v._status_pill.parent()
    assert parent is not None
    layout = parent.layout()
    assert layout is not None
    indexes = [layout.indexOf(w) for w in (v._id_badge, v._status_pill, v._curation_pill)]
    assert indexes == sorted(indexes), indexes


def test_download_button_states(view):
    v, tmp_path = view
    staged = Path(tmp_path) / "downloads" / PID.replace(":", "_").replace("/", "_") / "files"
    assert v._dl_btn.text() == "Download Dataset"
    staged.mkdir(parents=True, exist_ok=True)
    (staged / "a.csv").write_text("a,b\n1,2\n")
    v._refresh_download_state()
    assert v._dl_btn.text() == "Verify Files"


def test_metadata_button_states(view):
    v, _ = view
    assert v._load_meta_btn.text() == "Reload Metadata"  # cached metadata
    v._metadata = None
    v._refresh_header_actions()
    assert v._load_meta_btn.text() == "Load metadata"


def test_check_button_label_matrix(view):
    v, _ = view
    v._report = None
    assert v._check_button_text() == "Run Automatic Checks"
    v._report = _report(with_dataset=True, with_files=False)
    assert v._check_button_text() == "Run File Checks"
    v._report = _report(with_dataset=True, with_files=True)
    assert v._check_button_text() == "Re-run Automatic Checks"
    v._refresh_check_button()
    assert v._check_btn.text() == "Re-run Automatic Checks"


def test_run_checks_stages_the_dataset_first(view, monkeypatch):
    v, _ = view
    calls = []
    monkeypatch.setattr(v, "_on_download", lambda: calls.append("download"))
    # Nothing is staged, so the primary action must stage rather than warn.
    v._run_after_download = False
    v._on_run_checks()
    assert calls == ["download"]
    assert v._run_after_download is True


def test_export_reports_button_is_gone(view):
    v, _ = view
    labels = [w.text() for w in v.findChildren(QPushButton)]
    assert not any("Export reports" in label for label in labels)


def test_status_widget_starts_hidden_and_shows_three_faces(view):
    v, _ = view
    w = v._status_widget
    assert not w.isVisible()

    w.set_running("Running checks…", "14/21", 14 / 21)
    assert w.isVisible()
    assert w._title.text() == "Running checks…"
    assert w._detail.text() == "14/21"
    assert w._bar.value() == 66
    assert "cancel" in w._action.toolTip().lower()

    w.set_complete("All checks complete", "21/21")
    assert w._title.text() == "All checks complete"
    assert w._bar.value() == 100
    assert "dismiss" in w._action.toolTip().lower()

    w.set_error("Check error", "Checksum mismatch")
    assert w._title.text() == "Check error"
    assert w._detail.text() == "Checksum mismatch"
    assert "retry" in w._action.toolTip().lower()

    w.clear()
    assert not w.isVisible()


def test_rail_buttons_carry_lucide_icons(view):
    v, _ = view
    rail = v._rail
    for key in ("dataset_checks", "file_checks", "response"):
        assert not rail.buttons[key].icon().isNull(), key


def test_action_buttons_carry_lucide_icons(view):
    v, _ = view
    assert not v._check_btn.icon().isNull()
    assert not v._record_btn.icon().isNull()


def test_stage_chip_sits_after_the_status_pill(view):
    v, _ = view
    parent = v._status_pill.parent()
    layout = parent.layout()
    indexes = [layout.indexOf(w) for w in (v._status_pill, v._stage_pill, v._curation_pill)]
    assert indexes == sorted(indexes), indexes
    assert v._stage_pill.text() == "Submitted for Review"


def test_check_finished_feeds_the_status_widget(view, monkeypatch):
    v, _ = view
    v._show_status_complete("All checks complete", "12 passed · 2 warnings")
    assert v._status_widget.isVisible()
    assert v._status_widget._detail.text() == "12 passed · 2 warnings"
