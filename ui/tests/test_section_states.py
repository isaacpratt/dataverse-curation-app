"""State-driven coverage for the dataset detail sections (dv-lxt).

Sections build rows from the shared DetailState attributes and a report.
Seeding those attributes directly exercises the populate/refresh paths
without any worker, server or modal dialog.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ui.i18n import t


@pytest.fixture
def detail(qapp: Any, tmp_path: Path, monkeypatch: Any) -> Any:
    import ui.dialogs as dialogs
    from curation.config import Config
    from ui.dataset import DatasetDetailView

    # No modal may open during these tests: a dialog would block the run.
    for name in (
        "show_critical",
        "show_warning",
        "show_info",
        "confirm",
        "confirm_save_discard_cancel",
    ):
        monkeypatch.setattr(dialogs, name, lambda *_a, **_k: True)

    cfg = Config()
    cfg.app.workspace = tmp_path
    view = DatasetDetailView(
        cfg,
        "doi:10.5072/FK2/SECTIONS",
        "Sections",
        cached_metadata={"id": 1, "latestVersion": {"versionState": "DRAFT", "metadataBlocks": {}}},
        cached_inventory=[],
    )
    for _ in range(3):
        qapp.processEvents()
    yield view
    view.deleteLater()


def _metadata() -> dict[str, Any]:
    return {
        "id": 1,
        "latestVersion": {
            "versionState": "DRAFT",
            "metadataBlocks": {
                "citation": {
                    "fields": [
                        {"typeName": "title", "value": "A study"},
                    ]
                }
            },
        },
    }


def test_metadata_finished_with_inventory(detail: Any) -> None:
    seen: list[Any] = []
    detail.metadataLoaded.connect(
        lambda pid, metadata, inventory: seen.append((pid, metadata, inventory))
    )
    inventory = [{"path": "a.csv", "size_bytes": 12, "file_id": 1, "storageIdentifier": "x"}]
    detail._on_metadata_finished(
        _metadata(),
        inventory,
        curation={"history": [{"label": "Approve", "time": "2026-01-01", "assigner": "a"}]},
        version_diff={},
        extra={
            "versions": [{"number": "1.0", "state": "DRAFT", "create_time": "2026-01-01T00:00:00Z"}]
        },
    )
    assert detail._inventory == inventory
    assert detail._changes_loaded is True
    assert detail._inventory_ok is True
    assert len(seen) == 1
    assert seen[0][0] == detail._pid
    assert detail._all_file_rows
    assert t("detail.status.metadata_loaded", count=1) in detail._status_widget.text()


def test_metadata_finished_inventory_refused(detail: Any) -> None:
    detail._on_metadata_finished(
        _metadata(),
        [],
        extra={
            "inventory_failed": True,
            "refusals": {"inventory": {"reason": "draft_not_readable"}},
        },
    )
    assert detail._inventory_ok is False
    assert detail._all_file_rows == []
    assert t("detail.status.file_list_not_readable") in detail._status_widget.text()
    assert detail._file_tree.model().rowCount() == 0


def test_metadata_finished_inventory_failed_generic(detail: Any) -> None:
    detail._on_metadata_finished(_metadata(), [], extra={"inventory_failed": True})
    assert detail._inventory_ok is False
    assert t("detail.status.file_list_failed") in detail._status_widget.text()


def test_metadata_finished_zero_files(detail: Any) -> None:
    metadata = _metadata()
    metadata["latestVersion"]["versionState"] = "RELEASED"
    detail._on_metadata_finished(metadata, [])
    assert "This dataset contains no files in Dataverse" in detail._status_widget.text()
    assert detail._all_file_rows == []


def test_metadata_error_and_profile_change(detail: Any, monkeypatch: Any) -> None:
    import ui.dialogs as dialogs

    shown: list[Any] = []
    monkeypatch.setattr(dialogs, "show_critical", lambda *_a, **_k: shown.append(True))
    detail._on_metadata_error("boom")
    assert shown == [True]
    assert detail._meta_worker is None
    detail._profile_combo.setCurrentIndex(0)
    detail._on_profile_changed()
    assert isinstance(detail._profile_combo.currentData(), str)


def test_version_diff_renders_rows_and_placeholder(detail: Any) -> None:
    detail._versions = [
        {"number": "1.0", "state": "RELEASED", "release_time": "2026-01-02T00:00:00Z"},
        {"number": "2.0", "state": "DRAFT", "create_time": "2026-01-03T00:00:00Z"},
    ]
    detail._version_diff = {
        "old": {"number": "1.0"},
        "total_changes": 1,
        "metadata_changes": [{"field": "title", "block": "citation", "old": "Old", "new": "New"}],
        "terms_changes": [],
    }
    detail._populate_version_diff()
    assert "2" in detail._version_summary.text()
    assert detail._version_body.count() >= 2

    detail._version_diff = {"old": {"number": "1.0"}, "total_changes": 0}
    detail._populate_version_diff()
    assert detail._version_body.count() >= 1


def test_response_refresh_from_completeness(detail: Any) -> None:
    detail._completeness_full = [
        {
            "status": "incomplete",
            "level": "required",
            "rule_id": "title-presence",
            "field": "title",
            "requirement": "A title is required",
        },
        {"status": "complete", "rule_id": "contact", "field": "datasetContact"},
    ]
    detail._refresh_response(force=True)
    assert detail._response_sections
    assert any("title" in str(section).lower() for section in detail._response_sections)
    detail._update_response_chrome()
    detail._on_response_item_changed(None)


def test_checks_finished_builds_report_rows(detail: Any) -> None:
    from engine.checks.base import CheckResult
    from engine.report import DatasetReport, FileEntry

    detail._all_file_rows = [("a.csv", 12, "CSV", "")]
    detail._is_staged = lambda _p: True
    report = DatasetReport(
        detail._pid,
        "Sections",
        "0",
        dataset_checks=[CheckResult("inventory.access", "warning", False, "restricted file(s)")],
        files=[
            FileEntry("a.csv", 12, "text/csv", [CheckResult("format.csv", "error", False, "bad")])
        ],
    )
    detail._on_checks_finished(report)
    assert detail._report is report
    assert detail._auto_summary.text()
    detail._apply_auto_filter()
    detail._refresh_finding_summary()
    assert detail._dispositions_map() == {}


def test_actions_decision_helpers(detail: Any) -> None:
    detail._curation = {"allowed_labels": ["Approve", "Request changes", "Reject"]}
    choices, from_labels = detail._decision_choices()
    assert choices
    assert isinstance(from_labels, bool)
    for choice in choices:
        assert detail._decision_consequence(choice, from_labels)


def test_actions_sensitivity_helpers(detail: Any) -> None:
    detail._sensitivity_answers = {}
    blocked, reason = detail._sensitivity_blocks()
    assert isinstance(blocked, bool)
    assert isinstance(reason, str)
    suggestions = detail._sensitivity_suggestions()
    assert isinstance(suggestions, dict)
    detail._refresh_sensitivity_card()
    detail._refresh_sensitivity_status()
    detail._refresh_follow_up()


def test_decision_options_generic_and_from_labels(detail: Any) -> None:
    detail._curation = {}
    detail._refresh_decision_options()
    assert detail._decision_combo.count() >= 4
    assert t("detail.decision.generic_states_tip") == detail._decision_combo.toolTip()

    detail._curation = {"allowed": ["Approve", "Approve", "Hold"]}
    detail._refresh_decision_options()
    assert detail._decision_combo.count() == 3  # placeholder + two unique labels
    assert t("detail.decision.instance_labels_tip") == detail._decision_combo.toolTip()
    detail._decision_combo.setCurrentIndex(1)
    detail._sync_decision_state()


def test_checks_filter_and_cancellation_paths(detail: Any, monkeypatch: Any) -> None:
    from engine.checks.base import CheckResult
    from engine.report import DatasetReport, FileEntry

    detail._all_file_rows = [("a.csv", 12, "CSV", "")]
    detail._completeness_full = [
        {"status": "incomplete", "level": "required", "rule_id": "title", "field": "title"}
    ]
    report = DatasetReport(
        detail._pid,
        "Sections",
        "0",
        dataset_checks=[CheckResult("inventory.access", "warning", False, "restricted")],
        files=[
            FileEntry("a.csv", 12, "text/csv", [CheckResult("format.csv", "error", False, "bad")])
        ],
    )
    detail._on_checks_finished(report)
    for index in range(detail._auto_filter.count()):
        detail._auto_filter.setCurrentIndex(index)
        detail._apply_auto_filter()
    detail._on_checks_cancelled()
    detail._on_checks_error("checks failed")
    assert "checks failed" in detail._status_widget.text()


def test_cached_report_roundtrip(detail: Any) -> None:
    from engine.report import DatasetReport

    path = detail._cached_report_path()
    DatasetReport(detail._pid, "Cached", "0").save(path)
    loaded = detail._load_cached_report()
    assert loaded is not None
    assert loaded.label == "Cached"


def test_response_draft_working_copy(detail: Any) -> None:
    detail._completeness_full = []
    detail._refresh_response(force=True)
    detail._response_edit.setPlainText("Dear depositor, please revise.")
    detail._on_response_text_edited()
    detail._save_working_draft()
    assert detail._load_working_draft() is True
    assert "Dear depositor" in detail._response_edit.toPlainText()
    detail.refresh_rules()


def test_load_metadata_with_stub_worker(detail: Any, monkeypatch: Any) -> None:
    import ui.dataset.metadata_load as metadata_load

    class _Worker:
        def __init__(self, *_a: Any, **_k: Any) -> None:
            self.finished = _Signal()
            self.error = _Signal()
            self.progress = _Signal()

        def start(self) -> None:
            return None

        def requestInterruption(self) -> bool:
            return False

        def isRunning(self) -> bool:
            return False

        def wait(self, *_a: Any) -> bool:
            return True

        def deleteLater(self) -> None:
            return None

    class _Signal:
        def connect(self, *_a: Any, **_k: Any) -> None:
            return None

    import ui.workers as workers
    from ui.dataset.metadata_load import MetadataLoadSection

    # The session-scoped `win` fixture permanently replaces this method on
    # the facade with a no-op; restore the real section implementation.
    monkeypatch.setattr(type(detail), "_on_load_metadata", MetadataLoadSection._on_load_metadata)
    monkeypatch.setattr(metadata_load, "MetadataWorker", _Worker)
    monkeypatch.setattr(workers, "MetadataWorker", _Worker)
    detail._meta_worker = None
    detail._on_load_metadata()
    assert isinstance(detail._meta_worker, _Worker), (
        f"worker={detail._meta_worker!r}; button_enabled={detail._load_meta_btn.isEnabled()}"
    )


def test_commit_decision_paths(detail: Any, monkeypatch: Any) -> None:
    import ui.dialogs as dialogs

    calls: list[Any] = []
    monkeypatch.setattr(dialogs, "show_info", lambda *a, **k: calls.append(("info", a)))
    monkeypatch.setattr(dialogs, "show_warning", lambda *a, **k: calls.append(("warning", a)))
    decision = t("detail.decision.option_revisions")
    detail._decision_combo.setCurrentIndex(detail._decision_combo.findText(decision))
    detail._notes_edit.setPlainText("Please add a README")
    detail._on_commit()
    assert detail._decision_committed is True
    assert calls
    assert calls[0][0] in {"info", "warning"}

    detail._decision_committed = False
    detail._decision_combo.setCurrentIndex(0)  # placeholder
    detail._on_commit()
    assert detail._decision_committed is False


def test_download_fully_staged_and_inventory_error(
    detail: Any, monkeypatch: Any, tmp_path: Path
) -> None:
    import ui.dialogs as dialogs

    warnings: list[Any] = []
    monkeypatch.setattr(dialogs, "show_warning", lambda *a, **k: warnings.append(a))

    class _Manager:
        def inventory(self, _pid: str) -> list[dict[str, Any]]:
            return [{"path": "a.csv", "size_bytes": 12}]

        def missing_files(self, _pid: str, inv: Any = None) -> list[Any]:
            return []

        def verify(self, _pid: str) -> tuple[bool, list[Any], list[Any]]:
            return True, [], []

        def files_dir(self, _pid: str) -> Path:
            return tmp_path

    detail._dl_mgr = _Manager()
    detail._on_download()
    assert t("detail.download.all_verified_skip", count=1) in detail._status_widget.text()
    assert detail._dl_worker is None

    class _Broken:
        def inventory(self, _pid: str) -> list[dict[str, Any]]:
            raise RuntimeError("offline")

    detail._dl_mgr = _Broken()
    detail._on_download()
    assert warnings
    assert any("offline" in str(arg) for arg in warnings[0])


def test_set_disposition_persists(detail: Any) -> None:
    key = "abc123"
    detail._set_disposition(key, "acknowledged", note="done", refresh=True)
    from curation.storage import open_state

    st = open_state(detail._config.app.workspace)
    try:
        rows = st.list_actions(detail._pid, limit=50)
        assert any(r.get("action") == "disposition" for r in rows)
    finally:
        st.close()
    detail._set_disposition(key, "")


def test_export_report_roundtrip(detail: Any, monkeypatch: Any, tmp_path: Path) -> None:
    from PySide6.QtWidgets import QFileDialog

    from engine.report import DatasetReport

    detail._report = DatasetReport(detail._pid, "Exported", "0")
    target = tmp_path / "report.md"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *_a, **_k: (str(target), ""))
    detail._on_export()
    assert target.exists()
    assert target.with_suffix(".json").exists()
    assert detail._last_export_path == str(target.with_suffix(".json"))


def test_disposition_callbacks(detail: Any) -> None:
    key = "finding-key"
    detail._set_disposition(key, "wontfix", note="accepted")
    detail._on_disposition_changed(key, "acknowledged")
    from curation.storage import open_state

    st = open_state(detail._config.app.workspace)
    try:
        rows = st.list_actions(detail._pid, limit=50)
        assert sum(r.get("action") == "disposition" for r in rows) >= 2
    finally:
        st.close()


def test_tree_click_on_invalid_index(detail: Any) -> None:
    from PySide6.QtCore import QModelIndex

    detail._on_tree_clicked(QModelIndex())
    assert detail._status_widget is not None
