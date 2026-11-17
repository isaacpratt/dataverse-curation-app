"""Progressive startup: pages build on first use, the cache paints after show.

The window must not construct Settings/About/Requirements/Log or apply the
dashboard cache before its first frame. These tests pin that contract and
the idempotency of the lazy builders / background load.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _cfg(tmp_path: Path):
    from curation.config import Config

    cfg = Config()
    cfg.dataverse.base_url = "https://example.invalid"
    cfg.dataverse.collection = "demo"
    cfg.dataverse.api_token = ""  # no network path in these tests
    cfg.app.workspace = tmp_path
    return cfg


@pytest.fixture
def lazy_win(qapp, tmp_path):
    from ui.main_window import MainWindow

    window = MainWindow(_cfg(tmp_path))
    yield window
    window.close()
    window.deleteLater()
    qapp.processEvents()


def test_only_the_dashboard_is_built_at_construction(lazy_win):
    win = lazy_win
    assert win._stack.count() == 1
    assert win._stack.currentWidget() is win._dashboard
    assert win._settings is None
    assert win._settings_page is None
    assert win._about is None
    assert win._about_page is None
    assert win._review_config is None
    assert win._log_page is None
    # The cache is only read for the "restoring" state, never painted yet.
    assert win._dashboard._cache_loaded is False
    assert win._dashboard._startup_started is False


def test_panes_build_on_first_navigation(lazy_win):
    win = lazy_win

    win._show_pane("settings")
    assert win._settings is not None
    assert win._stack.currentWidget() is win._settings_page

    win._show_pane("log")
    assert win._log_page is not None
    assert win._stack.currentWidget() is win._log_page

    win._show_pane("about")
    assert win._about is not None
    assert win._stack.currentWidget() is win._about_page

    win._show_pane(None)
    assert win._stack.currentWidget() is win._dashboard

    # Builders are idempotent: navigation never rebuilds a pane.
    first = win._settings
    assert win._ensure_settings() is first
    assert win._ensure_log() is win._log_page
    assert win._ensure_about() is win._about


def test_dashboard_background_load_paints_cache_once(tmp_path):
    from ui.dashboard import DashboardView

    dash = DashboardView(_cfg(tmp_path))
    try:
        dash._startup_cache_entry = {
            "saved_at": "2026-01-01T00:00:00",
            "labels": [],
            "datasets": [
                {
                    "persistent_id": "doi:10.5072/FK2/A",
                    "title": "Alpha",
                    "state": "DRAFT",
                    "collection": "demo",
                }
            ],
        }
        dash._restoring = True
        assert dash._table.rowCount() == 0

        dash.start_background_load()
        assert dash._cache_loaded is True
        assert dash._table.rowCount() == 1
        assert dash._status_lbl.text().endswith(": 1/1 datasets shown")

        # Second call must not repaint or duplicate rows.
        dash.start_background_load()
        assert dash._table.rowCount() == 1
    finally:
        dash.deleteLater()


def test_main_window_background_load_is_safe(lazy_win):
    win = lazy_win
    win.start_background_load()
    assert win._dashboard._startup_started is True
    assert win._dashboard._cache_loaded is False  # nothing cached in tmp_path
    win.start_background_load()  # idempotent
    assert win._dashboard._table.rowCount() == 0
