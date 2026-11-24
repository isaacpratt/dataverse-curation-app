"""Settings unsaved-changes guard: baseline dirty tracking + leave paths.

Everything here is offscreen and network-free: token is blank, the package
size worker is stubbed out, and ``Config.save`` is monkeypatched so the real
``config.json`` is never touched.
"""

import pytest
from PySide6.QtGui import QCloseEvent

PRESET = "Borealis Demo \u2014 demo.borealisdata.ca"
CUSTOM = "Custom\u2026"


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
    cfg.app.tesseract = ""
    cfg.app.exiftool = ""
    widget = SettingsPane(cfg)
    yield widget
    widget.deleteLater()


@pytest.fixture
def window(win):
    """Yield the shared MainWindow with a clean, offline Settings pane."""
    pane = win._ensure_settings()
    token = pane._config.dataverse.api_token
    pane._config.dataverse.api_token = ""
    pane.reload()
    win._show_pane("settings")
    yield win, pane
    pane.reload()
    win._show_dashboard()
    pane._config.dataverse.api_token = token


def test_chip_is_hidden_until_an_edit_changes_the_baseline(pane):
    assert not pane.has_unsaved_changes()
    assert pane._footer.dirty_chip.isHidden()

    pane.url_edit.setText("https://example.org")
    assert pane.has_unsaved_changes()
    assert not pane._footer.dirty_chip.isHidden()

    # Edit then restore clears the chip again.
    pane.url_edit.setText("https://demo.borealisdata.ca")
    assert not pane.has_unsaved_changes()
    assert pane._footer.dirty_chip.isHidden()


def test_trailing_slash_is_not_a_change(pane):
    pane.url_edit.setText("https://demo.borealisdata.ca/")
    assert not pane.has_unsaved_changes()


@pytest.mark.parametrize(
    ("attr", "value"),
    [
        ("token_edit", "a-token"),
        ("subtree_edit", "another"),
        ("workspace_edit", "D:/tmp/workspace"),
    ],
)
def test_each_field_marks_and_clears_dirty(pane, attr, value):
    edit = getattr(pane, attr)
    original = edit.text()
    edit.setText(value)
    assert pane.has_unsaved_changes(), attr
    edit.setText(original)
    assert not pane.has_unsaved_changes(), attr


def test_tool_path_change_marks_dirty(pane):
    pane._tool_paths["tesseract"] = "C:/tools/tesseract.exe"
    pane._refresh_dirty()
    assert pane.has_unsaved_changes()
    pane._tool_paths["tesseract"] = ""
    pane._refresh_dirty()
    assert not pane.has_unsaved_changes()


def test_preset_change_that_rewrites_the_url_marks_dirty(qapp, tmp_path, monkeypatch):
    from curation.config import Config
    from ui.settings_dialog import SettingsPane

    monkeypatch.setattr(SettingsPane, "_start_size_worker", lambda self: None)
    cfg = Config()
    cfg.dataverse.base_url = "https://example.org"
    cfg.dataverse.api_token = ""
    cfg.app.workspace = tmp_path
    widget = SettingsPane(cfg)
    try:
        assert widget.preset_combo.currentText() == CUSTOM
        widget.preset_combo.setCurrentText(PRESET)
        assert widget.has_unsaved_changes()
        assert not widget._footer.dirty_chip.isHidden()
    finally:
        widget.deleteLater()


def test_persist_writes_clears_and_emits_configuration_changed(pane, monkeypatch):
    writes = []
    changes = []
    saves = []
    monkeypatch.setattr(pane._config, "save", lambda *a, **k: writes.append(1))
    pane.configurationChanged.connect(lambda: changes.append(True))
    pane.saved.connect(lambda: saves.append(True))

    pane.url_edit.setText("https://example.org")
    assert pane.persist() is True

    assert writes == [1]
    assert pane._config.dataverse.base_url == "https://example.org"
    assert not pane.has_unsaved_changes()
    assert pane._footer.dirty_chip.isHidden()
    assert changes == [True]
    assert saves == [], "persist() must not close the pane"


def test_persist_failure_keeps_dirty(pane, monkeypatch):
    def boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(pane._config, "save", boom)
    monkeypatch.setattr("ui.settings_dialog.show_critical", lambda *a, **k: None)

    pane.token_edit.setText("a-token")
    assert pane.persist() is False
    assert pane.has_unsaved_changes()


@pytest.mark.parametrize("bad_url", ["ftp://example.org", "http://example.org", "httpx://x.test"])
def test_persist_rejects_an_invalid_url(pane, monkeypatch, bad_url):
    warnings = []
    monkeypatch.setattr(
        "ui.settings_dialog.show_warning",
        lambda *a, **k: warnings.append(True),
    )
    pane.url_edit.setText(bad_url)
    assert pane.persist() is False
    assert warnings == [True]
    assert pane.has_unsaved_changes()


def test_revert_restores_every_field(pane, monkeypatch):
    monkeypatch.setattr("ui.settings_dialog.confirm", lambda *a, **k: True)
    original_url = pane.url_edit.text()
    original_ws = pane.workspace_edit.text()

    pane.url_edit.setText("https://example.org")
    pane.workspace_edit.setText("D:/tmp/elsewhere")
    pane._on_revert()

    assert pane.url_edit.text() == original_url
    assert pane.workspace_edit.text() == original_ws
    assert not pane.has_unsaved_changes()
    assert "Reverted" in pane._footer.status.text()


def test_confirm_leave_is_free_when_clean(pane, monkeypatch):
    monkeypatch.setattr(
        "ui.settings_dialog.confirm_save_discard_cancel",
        lambda *a, **k: pytest.fail("must not prompt when clean"),
    )
    assert pane.confirm_leave() is True


def test_confirm_leave_cancel_keeps_the_edit(pane, monkeypatch):
    monkeypatch.setattr(
        "ui.settings_dialog.confirm_save_discard_cancel",
        lambda *a, **k: "cancel",
    )
    pane.url_edit.setText("https://example.org")
    assert pane.confirm_leave() is False
    assert pane.url_edit.text() == "https://example.org"
    assert pane.has_unsaved_changes()


def test_confirm_leave_discard_resets(pane, monkeypatch):
    monkeypatch.setattr(
        "ui.settings_dialog.confirm_save_discard_cancel",
        lambda *a, **k: "discard",
    )
    pane.url_edit.setText("https://example.org")
    assert pane.confirm_leave() is True
    assert pane.url_edit.text() == "https://demo.borealisdata.ca"
    assert not pane.has_unsaved_changes()


def test_confirm_leave_save_persists(pane, monkeypatch):
    monkeypatch.setattr(
        "ui.settings_dialog.confirm_save_discard_cancel",
        lambda *a, **k: "save",
    )
    writes = []
    monkeypatch.setattr(pane._config, "save", lambda *a, **k: writes.append(1))
    pane.url_edit.setText("https://example.org")

    assert pane.confirm_leave() is True
    assert writes == [1]
    assert not pane.has_unsaved_changes()


def test_confirm_leave_save_failure_blocks_navigation(pane, monkeypatch):
    def boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(
        "ui.settings_dialog.confirm_save_discard_cancel",
        lambda *a, **k: "save",
    )
    monkeypatch.setattr(pane._config, "save", boom)
    monkeypatch.setattr("ui.settings_dialog.show_critical", lambda *a, **k: None)
    pane.url_edit.setText("https://example.org")

    assert pane.confirm_leave() is False
    assert pane.has_unsaved_changes()


# -- MainWindow guard -----------------------------------------------------


def test_show_pane_cancel_keeps_settings(window, monkeypatch):
    win, pane = window
    pane.url_edit.setText("https://example.org")
    monkeypatch.setattr(pane, "confirm_leave", lambda parent=None: False)

    assert win._show_pane(None) is False
    assert win._content_role() == "settings"


def test_dashboard_cancel_keeps_settings(window, monkeypatch):
    win, pane = window
    pane.url_edit.setText("https://example.org")
    monkeypatch.setattr(pane, "confirm_leave", lambda parent=None: False)

    win._show_dashboard()
    assert win._content_role() == "settings"


def test_dashboard_discard_leaves_settings(window, monkeypatch):
    win, pane = window
    pane.url_edit.setText("https://example.org")
    monkeypatch.setattr(pane, "confirm_leave", lambda parent=None: True)

    win._show_dashboard()
    assert win._content_role() == "dashboard"


def test_open_dataset_cancel_does_not_replace_the_detail_view(window, monkeypatch):
    win, pane = window
    before = win._detail
    pane.url_edit.setText("https://example.org")
    monkeypatch.setattr(pane, "confirm_leave", lambda parent=None: False)

    win._open_dataset("doi:10.5072/FK2/GUARDED", "Guarded dataset")
    assert win._content_role() == "settings"
    assert win._detail is before


def test_review_config_cancel_keeps_settings(window, monkeypatch):
    win, pane = window
    pane.url_edit.setText("https://example.org")
    monkeypatch.setattr(pane, "confirm_leave", lambda parent=None: False)

    win._show_review_config()
    assert win._content_role() == "settings"


def test_window_close_cancel_is_ignored(window, monkeypatch):
    win, pane = window
    pane.url_edit.setText("https://example.org")
    monkeypatch.setattr(pane, "confirm_leave", lambda parent=None: False)

    event = QCloseEvent()
    win.closeEvent(event)
    assert not event.isAccepted()
