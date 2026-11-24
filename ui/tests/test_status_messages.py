"""Success and error confirmations read as unmissable at a glance (dv-3wc).

The detail status strip, the settings connection verdict and the dashboard
counter used to render confirmations at caption size in a muted ink. They now
wear body-size high-contrast text (SuccessMD/DangerMD) and an icon prefix for
success/error tones; the message persists until the next action.

The old status strip is gone (dv-3d0.4); all messages now route through the
compact StatusWidget chip.
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


def test_status_widget_shows_success_face(view):
    view._set_status("Reports saved", tone="success")
    w = view._status_widget
    assert w.isVisible(), "status chip should be visible on success"
    assert "Reports saved" in w._title.text()
    # Empty message hides the chip again.
    view._set_status("")
    assert not w.isVisible()


def QApplication_process() -> None:
    from PySide6.QtWidgets import QApplication

    QApplication.processEvents()


def test_status_widget_shows_error_face(view):
    view._set_status("Failed", tone="error")
    w = view._status_widget
    assert w.isVisible(), "status chip should be visible on error"
    assert "Failed" in w._title.text()


def test_status_widget_shows_info_face(view):
    # Cached metadata load shows the status chip (dv-3d0.4)
    w = view._status_widget
    assert w.isVisible(), "status chip should be visible on cached metadata load"
    # The message should be in the title (set_running puts msg in title for info tone)
    assert "cached" in w._title.text().lower() or "metadata" in w._title.text().lower()


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
