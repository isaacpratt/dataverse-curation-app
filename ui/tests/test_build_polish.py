"""Regressions for the 2026-11-26 current-build defect list.

Covers painted (not just stylesheet) rail chrome, one-line status text,
sidebar card corners, palette-token re-resolution on a theme switch, and the
standard window caption glyphs.
"""

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette

PID = "doi:10.5072/FK2/POLISH"


def _pump(qapp: Any, turns: int = 20) -> None:
    for _ in range(turns):
        qapp.processEvents()


def _meta() -> dict[str, Any]:
    return {
        "latestVersion": {
            "versionState": "DRAFT",
            "metadataBlocks": {
                "citation": {
                    "fields": [
                        {"typeName": "title", "value": "A dataset with metadata"},
                        {"typeName": "depositor", "value": "Ada Lovelace"},
                    ]
                }
            },
        }
    }


def _view(qapp: Any, tmp_path: Any) -> Any:
    from curation.config import Config
    from ui.dataset import DatasetDetailView

    cfg = Config()
    cfg.app.workspace = tmp_path
    view = DatasetDetailView(cfg, PID, "A dataset", cached_metadata=_meta(), cached_inventory=[])
    view.resize(1320, 900)
    view.show()
    _pump(qapp)
    return view


# -- 1: rail paints white with a bottom rule ----------------------------------


def test_rail_paints_white_with_a_bottom_rule(qapp, tmp_path):
    from ui.theme import role

    view = _view(qapp, tmp_path)
    try:
        rail = view._rail
        rect = rail.rect().translated(rail.mapTo(view, rail.rect().topLeft()))
        image = view.grab().toImage()
        x = (rect.left() + rect.right()) // 2
        fill = image.pixelColor(x, rect.top() + 2).name().lower()
        assert fill == role("SURFACE_CARD").lower(), (fill, role("SURFACE_CARD"))
        near_bottom = [
            image.pixelColor(x, y).name().lower()
            for y in range(rect.bottom() - 3, rect.bottom() + 2)
        ]
        assert role("BORDER_SUBTLE").lower() in near_bottom, near_bottom
    finally:
        view.close()
        view.deleteLater()


# -- 2: one-line status, no bare count ----------------------------------------


def test_status_is_one_full_width_line_without_a_count(qapp, tmp_path):
    from ui.widgets import StatusWidget

    view = _view(qapp, tmp_path)
    try:
        widget = view._status_widget
        title = widget._title
        assert title.height() <= title.fontMetrics().height() + 2
        assert title.width() > 600, title.width()
        assert not widget._detail.isVisible()
        assert widget._detail.text() == ""
        assert StatusWidget._clean_detail("20/20") == ""
    finally:
        view.close()
        view.deleteLater()


# -- 3: sidebar card corners ---------------------------------------------------


def test_nested_card_headers_have_square_top_corners(qapp, tmp_path):
    view = _view(qapp, tmp_path)
    try:
        for card in (view._preview_card, view._version_card, view._dataset_log_card):
            header = card.findChild(type(view._side_card), "CardTopBar")
            assert header is not None
            sheet = header.styleSheet()
            assert "border-top-left-radius: 0px" in sheet, sheet
            assert "border-top-right-radius: 0px" in sheet, sheet
        assert "border-radius: 8px" in view._side_card.styleSheet()
    finally:
        view.close()
        view.deleteLater()


# -- 4/5: palette tokens + dark surfaces --------------------------------------


def test_theme_switch_repolishes_palette_tokens_and_pages(win, qapp):
    from ui import theme

    original = theme.ACTIVE_THEME
    try:
        for name, surface, page in (
            ("light", theme.role("SURFACE_CARD", "light"), theme.role("SURFACE_PAGE", "light")),
            ("dark", theme.role("SURFACE_CARD", "dark"), theme.role("SURFACE_PAGE", "dark")),
            ("light", theme.role("SURFACE_CARD", "light"), theme.role("SURFACE_PAGE", "light")),
        ):
            theme.set_active_theme(name)
            theme.apply_theme(qapp, name, retheme=True)
            _pump(qapp)
            assert win._topnav.palette().color(QPalette.ColorRole.Base).name().lower() == (
                surface.lower()
            )
            image = win.grab().toImage()
            assert image.pixelColor(600, 10).name().lower() == surface.lower()
            assert image.pixelColor(600, 60).name().lower() == page.lower()
            # Nav buttons follow too (the About/Help dark hover report).
            light = win._nav_help.palette().color(QPalette.ColorRole.Light).name().lower()
            assert light == theme.role("SURFACE_RAISED", name).lower(), (name, light)
    finally:
        theme.set_active_theme(original)
        theme.apply_theme(qapp, original, retheme=True)
        _pump(qapp)


def test_log_page_paints_its_own_background(win, qapp):
    from PySide6.QtWidgets import QWidget

    from ui import theme

    page = win._ensure_log()
    assert isinstance(page, QWidget)
    assert page.testAttribute(Qt.WidgetAttribute.WA_StyledBackground)
    assert f"QWidget#{page.objectName()}" in page.styleSheet()
    original = theme.ACTIVE_THEME
    try:
        theme.set_active_theme("dark")
        theme.apply_theme(qapp, "dark", retheme=True)
        win._show_pane("log")
        _pump(qapp)
        image = win.grab().toImage()
        assert (
            image.pixelColor(600, 60).name().lower() == theme.role("SURFACE_PAGE", "dark").lower()
        )
    finally:
        theme.set_active_theme(original)
        theme.apply_theme(qapp, original, retheme=True)


# -- 6/7: settings save/open performance contracts ----------------------------


def test_no_op_save_skips_disk_and_signals():
    from curation.config import Config
    from ui.settings_dialog import SettingsPane

    cfg = Config()
    cfg.app.workspace = Path("C:/tmp/settings-noop")
    pane = SettingsPane(cfg)
    try:
        writes: list[int] = []
        changes: list[bool] = []
        pane._config.save = lambda *a, **k: writes.append(1)  # type: ignore[method-assign]
        pane.configurationChanged.connect(lambda: changes.append(True))
        assert pane.persist() is True
        assert writes == []
        assert changes == []
    finally:
        pane.deleteLater()


def test_extensions_wait_for_background_probe(qapp, tmp_path, monkeypatch):
    from curation.config import Config
    from ui.settings_dialog import SettingsPane

    monkeypatch.setattr(SettingsPane, "_start_size_worker", lambda self: None)
    cfg = Config()
    cfg.app.workspace = tmp_path
    pane = SettingsPane(cfg)
    try:
        # Before the worker completes the table shows placeholders, never a
        # synchronous metadata probe on the GUI thread.
        before = pane.ext_table.item(0, 2)
        assert before is not None
        assert before.text() == "…"
        pane._start_probe_worker()
        assert pane._probe_worker is not None
        pane._probe_worker.wait(5000)
        _pump(qapp)
        after = pane.ext_table.item(0, 2)
        assert after is not None
        assert after.text() != "…"
    finally:
        pane.deleteLater()
        _pump(qapp, 10)


def test_refresh_sizes_forces_the_worker_instead_of_recursing(monkeypatch):
    from curation.config import Config
    from ui.settings_dialog import SettingsPane

    seen: list[bool] = []
    monkeypatch.setattr(
        SettingsPane, "_start_size_worker", lambda self, *, force=False: seen.append(force)
    )
    cfg = Config()
    cfg.app.workspace = Path("C:/tmp/settings-refresh")
    pane = SettingsPane(cfg)
    try:
        pane._refresh_sizes()
        assert seen == [True]
    finally:
        pane.deleteLater()


# -- 8: standard caption glyphs ------------------------------------------------


def test_caption_glyphs_are_thin_standard_shapes(win, qapp):
    from ui.main_window import _CaptionButton

    buttons = {b._kind: b for b in win.findChildren(_CaptionButton)}
    image = buttons["min"].grab().toImage()
    bg = image.pixelColor(0, 0).name()
    points = [
        (x, y)
        for x in range(image.width())
        for y in range(image.height())
        if image.pixelColor(x, y).name() != bg
    ]
    assert points
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    # A thin horizontal rule, not the old chunky outlined pixmap.
    assert max(ys) - min(ys) <= 2, (min(ys), max(ys))
    assert max(xs) - min(xs) >= 8
    assert buttons["close"].icon().isNull()  # painted directly, not a pixmap
