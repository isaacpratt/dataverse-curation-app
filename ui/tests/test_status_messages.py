"""Success and error confirmations read as unmissable at a glance (dv-3wc).

The detail status strip, the settings connection verdict and the dashboard
counter used to render confirmations at caption size in a muted ink. They now
wear body-size high-contrast text (SuccessMD/DangerMD) and an icon prefix for
success/error tones; the message persists until the next action.
"""

from pathlib import Path

import pytest


@pytest.fixture
def view(qapp, tmp_path):
    from curation.config import Config
    from ui.dataset import DatasetDetailView

    def _fv(value):
        return {"typeName": "text", "multiple": False, "typeClass": "primitive", "value": value}

    metadata = {
        "latestVersion": {
            "metadataBlocks": {
                "citation": {
                    "fields": [
                        {"typeName": "title", "value": "A study"},
                        {"typeName": "depositor", "value": "Ada Lovelace"},
                        {"typeName": "dateOfDeposit", "value": "2026-01-02"},
                    ]
                }
            }
        }
    }
    cfg = Config()
    cfg.app.workspace = Path(tmp_path)
    v = DatasetDetailView(
        cfg, "doi:10.5072/FK2/STATUS", "Status test", cached_metadata=metadata, cached_inventory=[]
    )
    v.show()
    for _ in range(5):
        qapp.processEvents()
    yield v
    v.close()
    v.deleteLater()


def test_success_strip_is_loud_and_persists(view):
    view._set_status("Reports saved", tone="success")
    assert view._status.isVisible()
    assert view._status_row.isVisible()
    assert not view._status_icon.isHidden(), "success wears a check icon"
    # Persistence: stays until the next action overwrites it.
    for _ in range(5):
        QApplication_process()
    assert view._status.isVisible()
    assert "Reports saved" in view._status.text()
    # Empty message hides the strip again.
    view._set_status("")
    assert not view._status.isVisible()
    assert not view._status_row.isVisible()


def QApplication_process():
    from PySide6.QtWidgets import QApplication

    QApplication.processEvents()


def test_error_strip_is_distinct_from_success(view):
    view._set_status("Failed", tone="error")
    err_sheet = view._status.styleSheet()
    view._set_status("Done", tone="success")
    ok_sheet = view._status.styleSheet()
    assert err_sheet != ok_sheet, "error and success must not share a face"
    assert "font-weight: 600" in err_sheet
    assert "font-weight: 600" in ok_sheet
    assert not view._status_icon.isHidden()


def test_info_strip_stays_quiet(view):
    view._set_status("loading…")
    assert view._status_icon.isHidden(), "info tone carries no icon"
    assert "font-weight: 600" not in view._status.styleSheet()


@pytest.fixture
def pane(qapp, tmp_path, monkeypatch):
    from curation.config import Config
    from ui.settings_dialog import SettingsPane

    monkeypatch.setattr(SettingsPane, "_start_size_worker", lambda self: None)
    cfg = Config()
    cfg.dataverse.base_url = "https://demo.borealisdata.ca"
    cfg.dataverse.api_token = ""
    cfg.dataverse.collection = "dv"
    cfg.app.workspace = tmp_path
    widget = SettingsPane(cfg)
    yield widget
    widget.deleteLater()


def test_settings_connection_verdict_is_body_size_and_iconed(pane):
    pane._set_conn_status(True, "Connected.", tip="tip info")
    assert pane._conn_status.objectName() == "SuccessMD"
    assert not pane._conn_icon.isHidden(), "success verdict wears a check icon"
    pane._set_conn_status(False, "Failed to reach.")
    assert pane._conn_status.objectName() == "DangerMD"
    assert not pane._conn_icon.isHidden(), "error verdict wears an x icon"
    pane._set_conn_status(None, "Checking…")
    assert pane._conn_status.objectName() == "HintSM"
    assert pane._conn_icon.isHidden()


def test_dashboard_counter_wears_the_primary_ink_token(win):
    assert win._dashboard._status_lbl.objectName() == "ValueMD"
