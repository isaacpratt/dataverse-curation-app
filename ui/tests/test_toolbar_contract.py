"""Card contract: the title row carries only title + (i) + summary.

Every other control - search fields, filter combos, reset buttons and
actions - lives on the tools row below it. The regression this guards is
real: the File Manifest's Open folder / Expand all and the queue's
Columns / Refresh had drifted back into the title row.
"""

from typing import Any, cast

import pytest
from PySide6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QHBoxLayout,
    QLabel,
    QWidget,
)

from ui.i18n import t


def _pump(qapp: Any, times: int = 15) -> None:
    for _ in range(times):
        qapp.processEvents()


def _layout_holds(layout, widget) -> bool:
    return any(layout.itemAt(index).widget() is widget for index in range(layout.count()))


def _title_row(card) -> QHBoxLayout:
    bar = card.findChild(QFrame, "CardTopBar")
    assert bar is not None, "card has no top bar"
    return cast(QHBoxLayout, bar.layout())


def _tools_row(card, name: str) -> QWidget:
    tools = card.findChild(QWidget, name)
    assert tools is not None, f"{name} row missing"
    return cast(QWidget, tools)


def _buttons_in(layout) -> list[QAbstractButton]:
    return [
        layout.itemAt(i).widget()
        for i in range(layout.count())
        if isinstance(layout.itemAt(i).widget(), QAbstractButton)
    ]


@pytest.fixture(scope="module")
def detail(win, qapp):
    win._open_dataset("doi:10.5072/FK2/TOOLROW", "Tool rows (tests)")
    det = None
    for _ in range(100):
        qapp.processEvents()
        det = getattr(win, "_detail", None)
        if det is not None and getattr(det, "_file_card", None) is not None:
            break
    assert det is not None, "detail view did not open"
    return det


# -- dashboard queue -------------------------------------------------------


def test_queue_title_row_holds_only_the_title(win, qapp):
    dash = win._dashboard
    win._show_dashboard()
    _pump(qapp)
    header = dash.findChild(QFrame, "QueueHeaderBar")
    outer = header.layout()
    title_row = outer.itemAt(0).layout()
    assert title_row is not None, "title row missing"
    widgets = [
        title_row.itemAt(i).widget()
        for i in range(title_row.count())
        if title_row.itemAt(i).widget() is not None
    ]
    assert len(widgets) == 1, (
        "the queue title row must carry only the title, found "
        f"{[type(w).__name__ for w in widgets]}"
    )
    assert isinstance(widgets[0], QLabel)
    assert widgets[0].objectName() == "HeadlineMD"


def test_queue_tools_row_holds_every_tool(win, qapp):
    dash = win._dashboard
    win._show_dashboard()
    _pump(qapp)
    tools = dash._filter_wrap.layout()
    for widget in (
        dash._filter_edit,
        dash._state_filter,
        dash._label_filter,
        dash._collection_filter,
        dash._columns_btn,
        dash._refresh_btn,
    ):
        assert _layout_holds(tools, widget), (
            f"{type(widget).__name__} must live on the queue tools row"
        )


def test_queue_search_has_no_visible_label(win, qapp):
    """The field's placeholder + accessible name carry the label."""
    dash = win._dashboard
    win._show_dashboard()
    _pump(qapp)
    assert dash._filter_edit.accessibleName() == t("dashboard.queue.search")
    tools = dash._filter_wrap
    labels = tools.findChildren(QLabel)
    assert labels == [], "no visible search label on the queue tools row"


def test_queue_refine_toggle_is_gone(win):
    """The tools row fits at 960, so the fold toggle has no job."""
    dash = win._dashboard
    assert not hasattr(dash, "_refine_btn")
    assert not hasattr(dash, "_update_refine_visibility")


# -- dataset detail cards --------------------------------------------------


def test_file_manifest_actions_live_on_the_tools_row(detail):
    card = detail._file_card
    tools = _tools_row(card, "FileManifestTools")
    for widget in (
        detail._file_filter,
        detail._scan_filter,
        detail._dl_btn,
        detail._open_folder_btn,
        detail._expand_btn,
        detail._dictionary_btn,
        detail._file_reset_btn,
    ):
        assert _layout_holds(tools.layout(), widget), (
            f"{type(widget).__name__} must live on the File Manifest tools row"
        )
    # One header line per card (dv-gfx.5): only title + (i) + stretch.
    title_row = _title_row(card)
    actions = _buttons_in(title_row)
    assert [b.objectName() for b in actions] == ["InfoTip"], (
        "File Manifest title row must hold no action buttons"
    )


def test_metadata_title_row_keeps_title_tip_and_summary(detail):
    card = detail._meta_card
    title_row = _title_row(card)
    assert _layout_holds(title_row, detail._meta_summary), (
        "the completeness summary belongs in the metadata title row"
    )
    assert _layout_holds(title_row, detail._load_meta_btn), (
        "Load metadata belongs on the card's title row"
    )
    tools = _tools_row(card, "MetadataCheckTools")
    for widget in (detail._meta_filter, detail._profile_combo):
        assert _layout_holds(tools.layout(), widget)


def test_version_reset_lives_on_the_title_row(detail):
    card = detail._version_card
    assert _layout_holds(_title_row(card), detail._version_reset_btn)


def test_auto_checks_title_row_keeps_the_summary(detail):
    # The automated checks are now a section inside the Dataset checks card,
    # not a separate card. The section has its own head with title and summary.
    head = detail._auto_card.findChild(QWidget, "AutoChecksHead")
    assert head is not None, "AutoChecksSection has no head"
    head_lay = head.layout()
    assert isinstance(head_lay, QHBoxLayout)
    # Only title and info tip on the head row; summary is also there.
    assert _layout_holds(head_lay, detail._auto_summary)


# -- review configuration --------------------------------------------------


def test_review_checks_tools_live_below_the_title(win, qapp):
    win._show_review_config()
    _pump(qapp)
    rc = win._review_config
    tools = _tools_row(rc, "FieldRulesTools")
    for widget in (
        rc._field_filter,
        rc._level_filter,
        rc._blocks_btn,
    ):
        assert _layout_holds(tools.layout(), widget), (
            f"{type(widget).__name__} must live on the Checks tools row"
        )
    assert not hasattr(rc, "_fields_reset_btn"), (
        "the rules table has no column resizing left to reset (dv-7zv)"
    )
    card = tools.parentWidget()
    assert isinstance(card, QFrame)
    actions = _buttons_in(_title_row(card))
    assert [b.objectName() for b in actions] == ["InfoTip"], (
        "Checks title row must hold no action buttons"
    )
