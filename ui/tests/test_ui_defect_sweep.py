"""Regressions for the 2026-11-25 UI defect sweep.

One place for the layout contracts that were reported together: rail chrome,
sidebar card/height/overlap, full-width status block, top-aligned logs,
Tailwind theme switch, and the log highlighter following the live palette.
"""

from typing import Any

import pytest

PID = "doi:10.5072/FK2/SWEEP"


def _view(qapp: Any, tmp_path: Any) -> Any:
    from curation.config import Config
    from ui.dataset import DatasetDetailView

    cfg = Config()
    cfg.app.workspace = tmp_path
    view = DatasetDetailView(cfg, PID, "Sweep", cached_metadata={"id": 1}, cached_inventory=[])
    view.resize(1200, 800)
    view.show()
    for _ in range(8):
        qapp.processEvents()
    return view


# -- item 1: first-load dashboard fit ----------------------------------------


def test_dashboard_first_load_keeps_content_autofit(win, qapp, tmp_path):
    """Default column hiding must not be mistaken for a user drag (dv-81l)."""
    from curation.config import Config as _Config
    from ui.main_window import MainWindow as _MainWindow

    cfg = _Config()
    cfg.app.workspace = tmp_path
    fresh = _MainWindow(cfg)
    try:
        fresh.resize(1200, 800)
        fresh.show()
        for _ in range(10):
            qapp.processEvents()
        dash = fresh._dashboard
        assert dash._table._auto_fit, "constructing the queue disabled content fit"
        rows = [
            {
                "title": "A Study With A Long Descriptive Title",
                "persistent_id": "doi:10.5072/FK2/ABCDEFG",
                "contact": "Ada Lovelace",
                "date_created": "2026-11-24T16:54:20Z",
                "file_count": 12,
                "total_size_bytes": 1234567890,
                "state": "DRAFT",
                "curation_label": "Ready for review",
                "downloaded_at": "2026-11-24",
            }
        ]
        dash._all_datasets = rows
        dash._paint_rows(rows)
        for _ in range(10):
            qapp.processEvents()
        hdr = dash._table.horizontalHeader()
        first = [hdr.sectionSize(i) for i in range(hdr.count()) if not hdr.isSectionHidden(i)]
        dash._reset_queue_layout()
        for _ in range(10):
            qapp.processEvents()
        after_reset = [hdr.sectionSize(i) for i in range(hdr.count()) if not hdr.isSectionHidden(i)]
        assert first == after_reset, (first, after_reset)
    finally:
        fresh.close()
        fresh.deleteLater()


# -- item 2: the section rail ------------------------------------------------


def test_rail_is_a_white_band_with_rule_spacing_and_shadow(qapp, tmp_path):
    from PySide6.QtWidgets import QGraphicsDropShadowEffect

    view = _view(qapp, tmp_path)
    try:
        rail = view._rail
        assert isinstance(rail.graphicsEffect(), QGraphicsDropShadowEffect)
        sheet = rail.styleSheet().lower()
        assert "border-bottom" in sheet
        top = view._rail.parentWidget()
        assert top is not None
        assert top.layout() is not None
        assert top.layout().contentsMargins().top() > 0
    finally:
        view.close()
        view.deleteLater()


# -- item 3: full-width status block -----------------------------------------


def test_status_widget_stacks_text_bar_then_findings(qapp):
    from PySide6.QtWidgets import QVBoxLayout

    from ui.widgets import StatusWidget

    widget = StatusWidget()
    widget.set_running("Running", "7/21", 7 / 21)
    try:
        rows = widget._rows
        assert isinstance(rows, QVBoxLayout)
        items = []
        for i in range(rows.count()):
            item = rows.itemAt(i)
            assert item is not None
            items.append(item)
        # line (words), bar, chips — in that order.
        assert items[0].layout() is not None
        assert items[1].widget() is widget._bar
        assert items[2].layout() is widget._chips
        line = items[0].layout()
        assert line is not None
        nested = []
        for i in range(line.count()):
            child = line.itemAt(i)
            assert child is not None
            nested.append(child.layout())
        assert widget._chips not in nested
        assert StatusWidget._clean_detail("*/*") == ""
        assert StatusWidget._clean_detail("* / *") == ""
        assert StatusWidget._clean_detail("7/21") == "7/21"
    finally:
        widget.deleteLater()


def test_status_widget_owns_a_full_width_row(qapp, tmp_path):
    from PySide6.QtWidgets import QLayout

    view = _view(qapp, tmp_path)
    try:
        canvas_lay = view._canvas.layout()
        assert isinstance(canvas_lay, QLayout)
        direct = [
            item.widget()
            for i in range(canvas_lay.count())
            if (item := canvas_lay.itemAt(i)) is not None
        ]
        assert view._status_widget in direct, "status must not share the title row"
    finally:
        view.close()
        view.deleteLater()


# -- items 4, 9, 10: sidebar card, height, overlap ---------------------------


def test_sidebar_is_a_card_inside_a_spaced_host(qapp, tmp_path):
    from PySide6.QtWidgets import QFrame

    view = _view(qapp, tmp_path)
    try:
        card = view._side_card
        assert isinstance(card, QFrame)
        assert card.objectName() == "Card"
        assert view._side_tabs.parent() is card
        host_lay = view._side_host.layout()
        assert host_lay.contentsMargins().left() > 0
        assert host_lay.contentsMargins().right() > 0
        assert card.maximumHeight() <= max(360, view.height() // 2 + 1)
    finally:
        view.close()
        view.deleteLater()


@pytest.mark.parametrize("width", [960, 1200, 1600])
def test_sidebar_never_draws_over_the_main_column(qapp, tmp_path, width):
    view = _view(qapp, tmp_path)
    try:
        view.resize(width, 760)
        for _ in range(4):
            qapp.processEvents()
        main = view._scroll
        side = view._side_host
        if side.isHidden():
            assert True  # folded away below the collapse width
            return
        main_rect = main.rect().translated(main.mapTo(view, main.rect().topLeft()))
        side_rect = side.rect().translated(side.mapTo(view, side.rect().topLeft()))
        assert not main_rect.intersects(side_rect), (main_rect, side_rect)
    finally:
        view.close()
        view.deleteLater()


# -- item 13: top-aligned sidebar logs ---------------------------------------


def test_version_and_dataset_logs_are_top_aligned(qapp, tmp_path):
    from PySide6.QtCore import Qt

    view = _view(qapp, tmp_path)
    try:
        assert view._version_body.alignment() & Qt.AlignmentFlag.AlignTop
        body = view._dataset_log.parentWidget()
        assert body is not None
        assert body.layout() is not None
        assert body.layout().alignment() & Qt.AlignmentFlag.AlignTop
    finally:
        view.close()
        view.deleteLater()


# -- item 6: log colours follow the active theme -----------------------------


def test_log_highlighter_resolves_colours_from_live_roles(qapp, monkeypatch):
    from PySide6.QtWidgets import QPlainTextEdit

    from ui import theme
    from ui.log_panel import LogHighlighter

    original = theme.ACTIVE_THEME
    try:
        monkeypatch.setattr(theme, "ACTIVE_THEME", "light")
        view = QPlainTextEdit()
        highlighter = LogHighlighter(view.document())
        assert highlighter.line_error_format.foreground().color().name().lower() == (
            theme.role("STATE_ERROR_GRAPHIC", "light").lower()
        )
        monkeypatch.setattr(theme, "ACTIVE_THEME", "dark")
        highlighter.set_theme()
        assert highlighter.line_error_format.foreground().color().name().lower() == (
            theme.role("STATE_ERROR_GRAPHIC", "dark").lower()
        )
    finally:
        monkeypatch.setattr(theme, "ACTIVE_THEME", original)


# -- item 7: the theme switch -------------------------------------------------


def test_settings_uses_one_light_dark_switch(win, monkeypatch):
    from ui.settings_dialog import SettingsPane
    from ui.widgets import ToggleSwitch

    monkeypatch.setattr(SettingsPane, "_apply_theme", lambda self: None)
    pane = win._ensure_settings()
    assert isinstance(pane.theme_toggle, ToggleSwitch)
    assert not hasattr(pane, "theme_mode_combo")
    assert not hasattr(pane, "auto_theme_checkbox")
    original = pane.theme_toggle.isChecked()
    pane.theme_toggle.setChecked(not original)
    assert pane._config.app.theme_mode in ("light", "dark")
    # Leave the shared window clean: a dirty Settings pane blocks teardown
    # with the Save/Discard dialog.
    pane.theme_toggle.setChecked(original)
    pane._refresh_dirty()


# -- item 8: no forced page scrollbar on General -----------------------------


def test_settings_general_fits_without_a_page_scrollbar(win, qapp):
    # The shared window is resized by geometry tests; fix a standard size so
    # this measures the layout, not whatever the previous test left behind.
    win.resize(1320, 900)
    win._show_pane("settings")
    for _ in range(10):
        qapp.processEvents()
    scroll = win._settings_page
    assert scroll.verticalScrollBar().maximum() == 0, (
        f"Settings forces a page scrollbar: viewport {scroll.viewport().height()}, "
        f"pane {win._settings.sizeHint().height()}"
    )
