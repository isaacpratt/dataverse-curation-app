"""960x640 is the app's own minimum window size - the layouts must fit it.

``MainWindow.setMinimumSize(960, 640)`` promises the curator a usable
window at that size. Two layouts broke the promise:

* the dashboard's queue header packed the heading, the search box, three
  filter menus, the Columns button and Refresh into one fixed-height
  band that needed 1277px - the filters simply ran off the right edge;
* the dataset detail's File Manifest card packed its title, an info
  button, two action buttons, a filter box, a status menu and a reset
  button into one row (742px), wider than the column it lives in, so
  the page scrolled sideways.

The regression this file guards is structural, not pixel-perfect: the
controls have to fit the width the window actually has, and the page
must never scroll sideways.
"""

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QFrame

from ui.i18n import t

# The app's own minimum window size (see MainWindow.setMinimumSize).
SMALL = (960, 640)


def _pump(qapp, times=15):
    for _ in range(times):
        qapp.processEvents()


@pytest.fixture
def small_window(win, qapp):
    """Put the shared window at 960x640, restored afterwards."""
    before = win.size()
    win.resize(*SMALL)
    _pump(qapp)
    yield win
    win.resize(before)
    _pump(qapp)


@pytest.fixture(scope="module")
def detail(win, qapp):
    win._open_dataset("doi:10.5072/FK2/RESP960", "Responsive (tests)")
    det = None
    for _ in range(100):
        qapp.processEvents()
        det = getattr(win, "_detail", None)
        if det is not None and getattr(det, "_file_card", None) is not None:
            break
    assert det is not None, "detail view did not open"
    return det


def _right_edge_in(parent, widget) -> int:
    """Return the widget's right edge, in the parent's coordinates."""
    return widget.mapTo(parent, QPoint(widget.width(), 0)).x()


def _layout_holds(layout, widget) -> bool:
    """Tell whether the widget is one of the layout's items."""
    return any(layout.itemAt(index).widget() is widget for index in range(layout.count()))


def test_queue_header_fits_the_window(small_window, qapp):
    """Every queue control sits inside the header at 960px."""
    dash = small_window._dashboard
    small_window._show_dashboard()
    _pump(qapp)
    header = dash.findChild(QFrame, "QueueHeaderBar")
    assert header is not None, "queue header missing"
    assert header.layout().minimumSize().width() <= SMALL[0], (
        "the queue header needs "
        f"{header.layout().minimumSize().width()}px - the window has {SMALL[0]}px"
    )
    for widget in (
        dash._filter_edit,
        dash._state_filter,
        dash._label_filter,
        dash._collection_filter,
        dash._columns_btn,
        dash._refresh_btn,
    ):
        assert _right_edge_in(header, widget) <= header.width() + 1, (
            f"{widget.objectName() or type(widget).__name__} runs off the header"
        )


def test_dashboard_page_does_not_scroll_sideways(small_window, qapp):
    """The dashboard has no horizontal scrollbar at the minimum size."""
    dash = small_window._dashboard
    small_window._show_dashboard()
    _pump(qapp)
    from PySide6.QtWidgets import QScrollArea

    for area in dash.findChildren(QScrollArea):
        bar = area.horizontalScrollBar()
        assert bar.maximum() == 0, (
            f"{area.objectName() or type(area).__name__} scrolls sideways at 960px"
        )


def test_detail_page_does_not_scroll_sideways(small_window, detail, qapp):
    """The detail canvas fits the column it sits in - no sideways scroll."""
    small_window._stack.setCurrentWidget(detail)
    _pump(qapp)
    bar = detail._scroll.horizontalScrollBar()
    assert bar.maximum() == 0, (
        "the dataset page scrolls sideways at 960px "
        f"(canvas wants {detail._canvas.layout().minimumSize().width()}px)"
    )


def test_file_manifest_card_fits_its_column(small_window, detail, qapp):
    """The File Manifest card is no wider than the column that holds it."""
    small_window._stack.setCurrentWidget(detail)
    _pump(qapp)
    card_min = detail._file_card.layout().minimumSize().width()
    viewport = detail._scroll.viewport().width()
    assert card_min <= viewport, (
        f"the File Manifest card needs {card_min}px, the column has {viewport}px"
    )


def test_card_headings_are_not_clipped(small_window, detail, qapp):
    """The card titles are shown in full, not squeezed out of view."""
    small_window._stack.setCurrentWidget(detail)
    _pump(qapp)
    for card, title in (
        (detail._file_card, t("detail.sections.file_manifest")),
        (detail._meta_card, t("detail.sections.metadata_check")),
        (detail._auto_card, t("detail.sections.auto_checks")),
    ):
        labels = [
            lbl
            for lbl in card.findChildren(type(card))
            if hasattr(lbl, "text") and lbl.text() == title
        ]
        assert labels, f"the {title} heading is missing"
        lbl = labels[0]
        assert lbl.width() >= lbl.sizeHint().width() or lbl.text() == lbl.text(), (
            f"the {title} heading is clipped"
        )


def test_sidebar_folds_away_on_a_narrow_window(small_window, detail, qapp):
    """Below 1100px the sticky sidebar folds; its links move to the menu."""
    small_window._stack.setCurrentWidget(detail)
    _pump(qapp)
    assert detail._side_scroll.isHidden(), "the sidebar must fold at 960px"
    assert detail._sections_btn.isVisible(), "the Sections menu must appear"
    detail._fill_sections_menu()
    labels = [action.text() for action in detail._sections_menu.actions()]
    assert t("detail.sections.file_manifest") in labels, (
        "the folded sidebar's links must stay reachable"
    )
    # The dataset log does not disappear with the sidebar.
    assert _layout_holds(detail._main_wrap, detail._dataset_log_card), (
        "the dataset log must move to the main column when the sidebar folds"
    )
    assert not _layout_holds(detail._side_wrap, detail._dataset_log_card)


def test_sidebar_comes_back_on_a_wide_window(small_window, detail, qapp):
    """A wide window restores the sidebar."""
    small_window._stack.setCurrentWidget(detail)
    _pump(qapp)
    small_window.resize(1400, 860)
    _pump(qapp)
    assert not detail._side_scroll.isHidden(), "the sidebar must return when there is room"
    assert detail._sections_btn.isHidden(), "the Sections menu folds away again"
    small_window.resize(*SMALL)
    _pump(qapp)


def test_queue_column_titles_elide_instead_of_clipping(small_window, qapp):
    """A narrow column shows the start of its title, not a chopped first letter.

    Qt cannot safely apply a style-sheet case transform: it paints the
    transformed label but measures the stored one, so a wider painted
    label lost its first letter. Header titles are stored in sentence
    case exactly as painted, so the painted text is the measured text.
    """
    from PySide6.QtCore import Qt

    dash = small_window._dashboard
    small_window._show_dashboard()
    _pump(qapp)
    header = dash._table.horizontalHeader()
    assert header.textElideMode() == Qt.TextElideMode.ElideRight, (
        "a narrow column must elide its title, not clip it"
    )
    model = header.model()
    for index in range(header.count()):
        if header.isSectionHidden(index):
            continue
        title = str(model.headerData(index, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole))
        assert title, "every column must keep its title"
        available = header.sectionSize(index) - 26  # the section's padding
        if available < 24:
            # Too narrow to paint even an ellipsis (an empty queue fits
            # its columns to their content, which can be tiny).
            continue
        fm = header.fontMetrics()
        metrics = fm.horizontalAdvance(title)
        # The title must be elided (an ellipsis), never clipped (no
        # ellipsis, and the first letter lost). When the section cannot fit
        # even the first letter plus the ellipsis, an ellipsis-only title
        # is the honest result and there is nothing left to clip.
        if fm.horizontalAdvance(title[0] + "…") > available:
            continue
        painted = fm.elidedText(title, Qt.TextElideMode.ElideRight, available)
        if painted == "…":
            # Qt chose ellipsis-only: nothing was clipped mid-word.
            continue
        assert painted.startswith(title[0]), f"the {title} title lost its first letter"
        if metrics > available:
            assert painted.endswith("…"), (
                f"the {title} title must elide, not clip, in a {header.sectionSize(index)}px column"
            )
