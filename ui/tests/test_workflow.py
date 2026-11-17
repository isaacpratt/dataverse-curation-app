"""Workflow-rail state: pure derivation matrix + offscreen rail behaviour.

The derivation is Qt-free, so most tests build one dataclass and assert the
states. The rail tests construct a ``DatasetDetailView`` from cached metadata
and inventory only — no metadata worker, no network.
"""

import pytest

from ui.workflow import (
    AVAILABLE,
    BLOCKED,
    CURRENT,
    DONE,
    STEP_ORDER,
    WorkflowInput,
    derive_workflow,
)


def _states(inp):
    return {s.key: s.state for s in derive_workflow(inp).steps}


def test_empty_dataset_marks_metadata_current():
    states = _states(WorkflowInput())
    assert states["metadata"] == CURRENT
    assert states["changes"] == BLOCKED
    assert states["download"] == BLOCKED
    assert states["checks"] == BLOCKED
    assert states["export"] == BLOCKED
    assert states["respond"] == AVAILABLE


def test_metadata_loaded_moves_to_changes():
    states = _states(WorkflowInput(metadata_loaded=True, total_files=12))
    assert states["metadata"] == DONE
    assert states["changes"] == CURRENT
    assert states["download"] == AVAILABLE
    assert states["respond"] == AVAILABLE


def test_partial_staging_shows_the_count_as_current():
    flow = derive_workflow(
        WorkflowInput(
            metadata_loaded=True,
            changes_loaded=True,
            staged=3,
            total_files=12,
        )
    )
    states = {s.key: s.state for s in flow.steps}
    assert states["download"] == CURRENT
    assert states["checks"] == AVAILABLE
    assert flow.hint == "3/12 staged"


def test_full_staging_moves_to_checks():
    states = _states(
        WorkflowInput(
            metadata_loaded=True,
            changes_loaded=True,
            staged=12,
            total_files=12,
        )
    )
    assert states["download"] == DONE
    assert states["checks"] == CURRENT


def test_report_ready_moves_to_export():
    states = _states(
        WorkflowInput(
            metadata_loaded=True,
            changes_loaded=True,
            staged=12,
            total_files=12,
            report_ready=True,
        )
    )
    assert states["checks"] == DONE
    assert states["export"] == CURRENT


def test_exported_moves_to_respond():
    states = _states(
        WorkflowInput(
            metadata_loaded=True,
            changes_loaded=True,
            staged=12,
            total_files=12,
            report_ready=True,
            exported=True,
        )
    )
    assert states["export"] == DONE
    assert states["respond"] == CURRENT


def test_response_open_is_current_even_with_earlier_steps_outstanding():
    flow = derive_workflow(WorkflowInput(metadata_loaded=False, response_open=True))
    states = {s.key: s.state for s in flow.steps}
    assert states["respond"] == CURRENT
    assert states["metadata"] == AVAILABLE
    assert flow.hint == "Next: Metadata"


def test_decision_committed_finishes_the_workflow():
    flow = derive_workflow(
        WorkflowInput(
            metadata_loaded=True,
            changes_loaded=True,
            staged=12,
            total_files=12,
            report_ready=True,
            exported=True,
            response_open=True,
            decision_committed=True,
        )
    )
    assert all(s.state == DONE for s in flow.steps)
    assert flow.current is None
    assert flow.hint == "Workflow complete"


def test_zero_file_dataset_skips_download_but_still_runs_checks():
    states = _states(WorkflowInput(metadata_loaded=True, changes_loaded=True, total_files=0))
    assert states["download"] == DONE
    assert states["checks"] == CURRENT


def test_unknown_inventory_is_not_mistaken_for_zero_files():
    states = _states(WorkflowInput(metadata_loaded=True, inventory_ok=False, total_files=0))
    assert states["download"] != DONE


def test_step_order_and_accessible_names_are_stable():
    flow = derive_workflow(WorkflowInput(metadata_loaded=True))
    assert [s.key for s in flow.steps] == list(STEP_ORDER)
    assert flow.steps[0].accessible == "Metadata, done step"
    changes_step = flow.step_of("changes")
    assert changes_step is not None
    assert changes_step.accessible == "Changes, current step"


# -- rail widget ----------------------------------------------------------


@pytest.fixture
def detail(qapp, tmp_path):
    from curation.config import Config
    from ui.dataset import DatasetDetailView

    cfg = Config()
    cfg.dataverse.base_url = "https://demo.borealisdata.ca"
    cfg.dataverse.api_token = ""
    cfg.app.workspace = tmp_path
    view = DatasetDetailView(
        cfg,
        "doi:10.5072/FK2/RAIL",
        "Rail dataset",
        cached_metadata={"latestVersion": {"versionState": "DRAFT"}},
        cached_inventory=[{"path": "tables/a.csv", "size": 10}],
    )
    yield view
    view.deleteLater()


def test_rail_renders_six_steps_in_order(detail):
    rail = detail._rail
    assert list(rail.buttons.keys()) == list(STEP_ORDER)
    assert all(rail.buttons[key].text() for key in STEP_ORDER)
    assert rail.buttons["metadata"].accessibleName() == "Metadata, done step"
    assert rail.buttons["changes"].accessibleName() == "Changes, current step"


def test_rail_steps_scroll_the_review_page_without_running_actions(detail, monkeypatch):
    anchors = []
    monkeypatch.setattr(detail, "_goto_section", lambda attr: anchors.append(attr))

    detail._rail.buttons["checks"].click()
    assert detail._pages.currentIndex() == 0
    assert anchors[-1] == "_auto_card"

    detail._rail.buttons["changes"].click()
    assert anchors[-1] == "_version_card"


def test_rail_download_and_export_only_focus_their_buttons(detail, monkeypatch):
    called = []
    monkeypatch.setattr(detail, "_on_download", lambda: called.append("download"))
    monkeypatch.setattr(detail, "_on_export", lambda: called.append("export"))
    focused = []
    monkeypatch.setattr(detail._dl_btn, "setFocus", lambda *a, **k: focused.append("download"))
    monkeypatch.setattr(detail._history_btn, "setFocus", lambda *a, **k: focused.append("export"))
    monkeypatch.setattr(detail, "_goto_section", lambda attr: None)

    detail._rail.buttons["download"].click()
    detail._rail.buttons["export"].click()

    assert called == [], "rail steps must never start a download or export"
    assert focused == ["download", "export"]


def test_rail_respond_switches_to_the_response_page(detail):
    detail._rail.buttons["respond"].click()
    assert detail._pages.currentIndex() == 1
    detail._rail.buttons["metadata"].click()
    assert detail._pages.currentIndex() == 0


def test_rail_repaints_when_report_and_staging_change(detail):
    detail._changes_loaded = True
    detail._staged_n = 1
    detail._staged_total = 1
    detail._report = object()
    detail._refresh_workflow()

    assert detail._rail.buttons["download"].accessibleName() == "Download, done step"
    assert detail._rail.buttons["checks"].accessibleName() == "Checks, done step"
    assert detail._rail.buttons["export"].accessibleName() == "Export, current step"

    detail._report = None
    detail._refresh_workflow()
    assert detail._rail.buttons["export"].accessibleName() == "Export, blocked step"
