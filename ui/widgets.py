"""Shared UI component kit: one source of truth for buttons, tables, cards.

Every view builds its controls through these factories so shape, font,
spacing, hover, and table behaviors stay identical app-wide.

Intentional one-offs (NOT kit violations):
- dataset header actions + Commit + Open folder + log Clear buttons:
  AppButton instances with inline action_button_style() — app-level QSS
  demonstrably fails to paint button faces inside some main-window
  subtrees, so the style must be inline.
- dashboard queue card / metric cards: bespoke headers (tinted banner,
  accent bars) that make_card's plain header cannot express.
- about card: header-less plain card (the pane already carries its heading).
- log strip + Live toggle + dataset chips: stateful split/toggle controls
  with no kit equivalent.
"""

import textwrap

from PySide6.QtCore import QEvent, QObject, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTextEdit,
    QToolButton,
    QToolTip,
    QTreeView,
    QTreeWidget,
    QVBoxLayout,
    QWidget,
)

from ui.i18n import t
from ui.theme import (
    ACCENT_FOCUS_RING,
    ACCENT_PRIMARY,
    BORDER_CONTROL,
    BORDER_SUBTLE,
    BUTTON_OBJECTS,
    FONT_BODY,
    FONT_CAPTION,
    FONT_MICRO,
    FONT_SMALL,
    MONO_FAMILY,
    ON_SURFACE_VARIANT,
    PRIMARY_FIXED,
    RADIUS_LG,
    SURFACE_CARD,
    SURFACE_PAGE,
    SURFACE_RAISED,
    SURFACE_SUBTLE,
    SURFACE_TINT,
    TEXT_BLOCKED,
    TEXT_DANGER,
    TEXT_DISABLED,
    TEXT_MUTED,
    TEXT_ON_TINT,
    TEXT_PLACEHOLDER,
    TEXT_PRIMARY,
    TEXT_SUCCESS,
    badge_qss,
    button_qss,
    enable_table_copy,
    header_section_qss,
    input_qss,
    label_badge_style,
    scrollbar_lane_qss,
    transparent_qss,
    transparent_surface_qss,
    workflow_step_qss,
)
from ui.workflow import STEP_ORDER, Workflow

__all__ = [
    "AppButton",
    "AppTable",
    "AppTree",
    "AppTreeWidget",
    "SortArrowHeaderView",
    "PaneFooter",
    "WorkflowRail",
    "flush_table_style",
    "flush_list_style",
    "tree_style",
    "make_card",
    "add_info_tip",
    "make_action_button",
    "make_badge",
    "make_checkbox",
    "make_list",
    "make_multiline_input",
    "make_page_heading",
    "make_split_chip",
    "make_plain_text_view",
    "make_progress_bar",
    "make_section_heading",
    "make_body_label",
    "make_caption_label",
    "make_field_label",
    "make_small_body_label",
    "make_card_title",
    "make_metric_value",
    "make_elided_label",
    "ElidedLabel",
    "make_reset_columns_button",
    "make_search_field",
    "make_line_edit",
    "make_combo",
    "BUTTON_HEIGHTS",
]

# Button heights (px) by size token.
# "sm" is 32px, not 28: WCAG 2.5.8 asks for a 24px target, but the
# platform's own menus and toolbars land on 32, and a 28px chip is easy
# to miss with a mouse or a stylus. Every button in the app clears 32.
BUTTON_HEIGHTS = {"sm": 32, "md": 36, "lg": 40}

# The kinds and the object name each paints under live in the theme,
# next to the rules that style them.
_BUTTON_OBJECTS = BUTTON_OBJECTS


class AppButton(QPushButton):
    """Standard button.

    kind: primary | secondary | ghost | chip | cell | link | nav-active | nav.
    size: sm (32) | md (36) | lg (40) | None (natural height, e.g. nav bar).
    """

    def __init__(
        self,
        text: str = "",
        kind: str = "secondary",
        size: str | None = "md",
        parent: QWidget | None = None,
        tip: str = "",
    ) -> None:
        super().__init__(text, parent)
        self.setObjectName(_BUTTON_OBJECTS.get(kind, "SecondaryButton"))
        if size in BUTTON_HEIGHTS:
            self.setFixedHeight(BUTTON_HEIGHTS[size])
        self.setCursor(Qt.PointingHandCursor)
        if tip:
            self.setToolTip(tip)

    def clicked_to(self, slot) -> "AppButton":
        """Chainable connect: AppButton("Save").clicked_to(self._on_save)."""
        self.clicked.connect(slot)
        return self


def _section_is_user_resizable(header, logical: int) -> bool:
    """Tell whether the user could have dragged this section's edge.

    A section the layout owns is never a user gesture, however Qt
    reports the resize: a Stretch or Fixed section, or the last section
    of a header that stretches its last section. Without this check a
    window resize (which re-stretches those sections) would look like a
    user drag and would be persisted as one.
    """
    try:
        if header.sectionResizeMode(logical) != QHeaderView.Interactive:
            return False
    except Exception:
        return True
    try:
        if header.stretchLastSection():
            last = header.count() - 1
            while last >= 0 and header.isSectionHidden(last):
                last -= 1
            if logical == last:
                return False
    except Exception:
        pass
    return True


class _HeaderTooltipFilter(QObject):
    """Give a header section its full column title back on hover.

    A narrow column elides its title ("SUBMITTING AUTH…"), so the mouse
    has to carry the name the section cannot show.
    """

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (Qt naming)
        if event.type() == QEvent.ToolTip:
            header = obj
            try:
                index = header.logicalIndexAt(event.pos())
                label = header.model().headerData(
                    index, Qt.Horizontal, Qt.DisplayRole
                )
            except Exception:
                return False
            if index >= 0 and label:
                QToolTip.showText(event.globalPos(), str(label), header)
                return True
        return super().eventFilter(obj, event)


class SortArrowHeaderView(QHeaderView):
    """QHeaderView that draws its own sort arrow, inside the section.

    The style's native CE_HeaderSortIndicator paints at the wrong place
    under this app's header QSS on this Qt build — instead of sitting
    beside the label it floats at the top-centre of the section, a stray
    glyph in the seam above the header. No
    ``QHeaderView::section::sort-indicator`` rule can position it
    (QSS image paints centred over the text, the vector arrow floats),
    and no painter can be opened for the extra glyph (paintEvent already
    runs with one active, so a nested QPainter on the widget silently
    fails). The arrow therefore rides on a child label positioned over
    the section, refreshed on every paint — a paint is exactly when
    section positions may have changed.

    All Qt state semantics stay stock: views set/read
    sortIndicatorSection/order/shown exactly as before (the dashboard's
    toggle logic, the saved-sort restore and the mirror header keep
    working). The native indicator is suppressed only for the paint
    pass; the flag visible to callers stays as they set it, and the
    label is the arrow.
    """

    _ARROW_PX = 14
    _ARROW_MARGIN = 8

    def __init__(self, orientation: Qt.Orientation, parent: QWidget | None = None) -> None:
        super().__init__(orientation, parent)
        self._arrow = QLabel(self)
        self._arrow.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._arrow.setFocusPolicy(Qt.NoFocus)
        self._arrow.setMouseTracking(False)
        self._arrow.setStyleSheet(transparent_qss("QLabel"))
        self._arrow.hide()
        self._painting = False
        # setSortIndicator / setSortIndicatorShown update the
        # view's viewport, not the header — without this, the label
        # would lag one paint behind the sorted order.
        self.sortIndicatorChanged.connect(self._on_sort_indicator_changed)

    def _on_sort_indicator_changed(self, *_args) -> None:
        if not self._painting:
            self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        section = self.sortIndicatorSection()
        active = (
            self.orientation() == Qt.Horizontal
            and self.isSortIndicatorShown()
            and 0 <= section < self.count()
            and not self.isSectionHidden(section)
        )
        if active:
            # Suppress the native arrow for this one paint, then
            # restore the flag. Updates stay disabled across the
            # toggle so the two setter calls cannot post repaint
            # requests; the label below is synced onto the paint
            # that just happened.
            self._painting = True
            self.setUpdatesEnabled(False)
            try:
                self.setSortIndicatorShown(False)
                super().paintEvent(event)
                self.setSortIndicatorShown(True)
            finally:
                self.setUpdatesEnabled(True)
                self._painting = False
            self._sync_arrow()
            return
        super().paintEvent(event)
        self._arrow.hide()

    def _sync_arrow(self) -> None:
        section = self.sortIndicatorSection()
        if (
            self.orientation() != Qt.Horizontal
            or not self.isSortIndicatorShown()
            or not (0 <= section < self.count())
            or self.isSectionHidden(section)
        ):
            self._arrow.hide()
            return
        try:
            from ui.icons import icon

            name = (
                "chevron-down" if self.sortIndicatorOrder() == Qt.DescendingOrder else "chevron-up"
            )
            pixmap = icon(
                name, color=ON_SURFACE_VARIANT, size=self._ARROW_PX
            ).pixmap(QSize(self._ARROW_PX, self._ARROW_PX))
            if pixmap.isNull():
                self._arrow.hide()
                return
            x = (
                self.sectionViewportPosition(section)
                + self.sectionSize(section)
                - self._ARROW_MARGIN
                - self._ARROW_PX
            )
            y = (self.height() - self._ARROW_PX) // 2
            self._arrow.setPixmap(pixmap)
            self._arrow.resize(self._ARROW_PX, self._ARROW_PX)
            self._arrow.move(x, y)
            self._arrow.show()
        except Exception:
            self._arrow.hide()


class AppTable(QTableWidget):
    """Build a standard table (sortable columns, row selection, no grid).

    Hidden vertical header and Ctrl+C copy support. headers: ordered column
    titles. widths: {index: px} initial widths (default 120). row_height:
    vertical default section size. sortable: leave True unless the view
    depends on insertion order.

    Emits columns_fitted after a successful content fit so split-header
    views (dashboard queue) can mirror the new section sizes, and
    user_layout_changed when the *user* resizes or moves a column — the
    only layout change that may be persisted (see ui.table_layout).
    """

    columns_fitted = Signal()
    user_layout_changed = Signal()

    def setHorizontalHeaderLabels(self, labels) -> None:  # noqa: N802 (Qt naming)
        """Set the column titles in sentence case, as painted.

        Headers read as the catalogue writes them ("Dataset Title",
        "Persistent ID"), never force-uppercased. Qt's style sheets cannot
        apply ``text-transform`` safely: it is applied when the label is
        painted but not when it is measured, so a narrow section elided
        against the smaller mixed-case metrics and the paint overflowed
        the section. Keeping the stored label identical to the painted
        label keeps measurement and paint in step.
        """
        super().setHorizontalHeaderLabels([str(label) for label in labels])

    def __init__(
        self,
        headers: list,
        parent: QWidget | None = None,
        *,
        sortable: bool = True,
        row_height: int = 40,
        stretch_last: bool = True,
        widths: dict | None = None,
    ) -> None:
        super().__init__(0, len(headers), parent)
        # The kit header draws the sort arrow itself (see
        # SortArrowHeaderView): the style's native indicator floats in
        # the seam above the header on this Qt build.
        self.setHorizontalHeader(SortArrowHeaderView(Qt.Horizontal, self))
        self.setHorizontalHeaderLabels(list(headers))
        hdr = self.horizontalHeader()
        hdr.setStretchLastSection(stretch_last)
        hdr.setSectionsMovable(True)
        hdr.setSectionsClickable(True)
        # A narrow section elides its label instead of clipping it: a
        # centred label clipped on both sides loses its first letter
        # ("SUBMITTING AUTHOR" read as "UBMITTING AUTHOR").
        hdr.setTextElideMode(Qt.ElideRight)
        # Hovering an elided column gives the full title back.
        self._header_tip = _HeaderTooltipFilter(hdr)
        hdr.installEventFilter(self._header_tip)
        for i in range(len(headers)):
            width = (widths or {}).get(i, 120)
            self.setColumnWidth(i, width)
            hdr.setSectionResizeMode(i, QHeaderView.Interactive)
        self.setShowGrid(False)
        # NoFrame: the 1px StyledPanel frame would inset every flush table
        # 1px inside its card (770px table in a 772px card); the card border
        # already provides the outline.
        self.setFrameStyle(QFrame.NoFrame)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.setAlternatingRowColors(False)
        self.setWordWrap(False)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(row_height)
        # StrongFocus (not NoFocus): the copy KeyPress filter is installed
        # on the table itself, so it only sees events when the table has
        # focus. Visual outline stays off via the stylesheet.
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSortingEnabled(sortable)
        self._auto_fit = True
        self._fitting = False
        self._fitted = False
        hdr.sectionResized.connect(self._on_user_section_resized)
        hdr.sectionMoved.connect(self._on_user_section_moved)
        enable_table_copy(self)

    def showEvent(self, event) -> None:
        """First visible paint: fit once the viewport has a real width.

        Populates often run during __init__ (cached dashboard, settings
        reload) when the widget is still hidden — viewport().width() is
        meaningless there, so fit defers to here.
        """
        super().showEvent(event)
        if self._auto_fit and not self._fitted and self.rowCount() > 0:
            QTimer.singleShot(0, self._fit_after_show)

    def _fit_after_show(self) -> None:
        if self._auto_fit and not self._fitted and self.isVisible():
            self.fit_columns_to_content()

    def populate_guarded(self, row_count: int) -> None:
        """SetRowCount with sorting suppressed so inserts stay in order."""
        was = self.isSortingEnabled()
        self.setSortingEnabled(False)
        self.setRowCount(row_count)
        self.setSortingEnabled(was)

    def _on_user_section_resized(self, logical: int, *_args) -> None:
        """Lock content auto-fit once the user drags a column edge."""
        if self._fitting:
            return
        if not _section_is_user_resizable(self.horizontalHeader(), logical):
            return
        self._auto_fit = False
        self.user_layout_changed.emit()

    def _on_user_section_moved(self, *_args) -> None:
        """Note that the user dragged a column to a new position."""
        if self._fitting:
            return
        self.user_layout_changed.emit()

    def disable_auto_fit(self) -> None:
        """Disable auto-fit after saved widths are restored — never overwrite the user's layout."""
        self._auto_fit = False

    def enable_auto_fit(self) -> None:
        """Clear restore/manual locks so the next populate re-fits content."""
        self._auto_fit = True
        self._fitted = False

    def fit_columns_to_content(
        self,
        *,
        min_width: int = 48,
        max_width: int = 520,
    ) -> None:
        """Size Interactive columns to their header/cell/widget content.

        Stretch columns and a stretched last section keep absorbing slack.
        No-ops when already fitted, when the user resized a column, when a
        saved view was restored, or while hidden (showEvent retries).
        If fitted widths overflow the viewport, every fitted column scales
        down by one ratio so nothing is clipped — required where the
        horizontal scrollbar is off (dashboard queue, meta table). Header
        signals stay blocked so the fit is not persisted as a manual
        resize; columns_fitted fires afterwards for split-header sync.
        """
        if not self._auto_fit or self._fitted or self.rowCount() <= 0:
            return
        if not self.isVisible():
            return
        hdr = self.horizontalHeader()
        was_sorting = self.isSortingEnabled()
        was_stretch_last = hdr.stretchLastSection()
        self._fitting = True
        hdr.blockSignals(True)
        try:
            self.setSortingEnabled(False)
            hdr.setStretchLastSection(False)
            count = self.columnCount()
            targets: dict[int, int] = {}
            # Stretch sections are not content-sized; reserve their current
            # width so the downscale below never crushes them to zero.
            stretch_reserve = 0
            for i in range(count):
                if hdr.isSectionHidden(i):
                    continue
                mode = hdr.sectionResizeMode(i)
                if mode == QHeaderView.Stretch:
                    stretch_reserve += max(
                        min_width, min(max_width, int(hdr.sectionSize(i)))
                    )
                    continue
                if mode != QHeaderView.Interactive:
                    continue
                hint = 0
                try:
                    hint = int(hdr.sectionSizeFromContents(i))
                except Exception:
                    hint = 0
                try:
                    col_hint = int(self.sizeHintForColumn(i))
                    if col_hint > hint:
                        hint = col_hint
                except Exception:
                    pass
                for row in range(self.rowCount()):
                    cell = self.cellWidget(row, i)
                    if cell is None:
                        continue
                    try:
                        w = int(cell.sizeHint().width()) + 8
                        if w > hint:
                            hint = w
                    except Exception:
                        continue
                if hint <= 0:
                    continue
                targets[i] = max(min_width, min(max_width, hint))
            usable = self.viewport().width() - stretch_reserve
            total = sum(targets.values())
            if usable > 0 and total > usable:
                ratio = usable / total
                for i, w in list(targets.items()):
                    targets[i] = max(min_width, int(round(w * ratio)))
            for i, w in targets.items():
                hdr.resizeSection(i, w)
            hdr.setStretchLastSection(was_stretch_last)
        except Exception:
            pass
        finally:
            hdr.blockSignals(False)
            self._fitting = False
            try:
                self.setSortingEnabled(was_sorting)
            except Exception:
                pass
            self._fitted = True
            self.columns_fitted.emit()


def flush_table_style(
    last: bool = True,
    *,
    header_background: str | None = None,
    item_padding: str | None = None,
) -> str:
    """Edge-to-edge QTableWidget face for tables flush inside cards/panes.

    Qt never clips children to a parent's border-radius, so a flush table
    paints its own corners: square top (meets the header/content above
    flush), 8px bottom when `last` (meets the card/pane border) else square
    (more flush content follows). Header end-caps stay square for the same
    reason — the global 8px section radius would notch unfilled.
    The background is explicit (not inherited from the app rule): without
    it, a styled lavender ancestor makes the whole table body transparent
    and rows render page-colored instead of white.

    The header rules and the scrollbar lanes come from the theme's shared
    mixins: a widget-level stylesheet replaces the app-level rules for
    that subtree, so they have to be repeated here — from one source, so
    they cannot drift.
    """
    bottom = "8px" if last else "0px"
    return (
        "QTableWidget { background: " + SURFACE_CARD + "; border: none; "
        "border-top-left-radius: 0px; border-top-right-radius: 0px; "
        "border-bottom-left-radius: " + bottom + "; "
        "border-bottom-right-radius: " + bottom + "; } "
        + header_section_qss(flush=True)
        + scrollbar_lane_qss("QTableWidget")
        + (f" QHeaderView {{ background: {header_background}; }}" if header_background else "")
        + (f" QTableWidget::item {{ padding: {item_padding}; }}" if item_padding else "")
    )


_FRAMED_LIST_STYLE = (
    f"QListWidget {{ background: {SURFACE_CARD}; "
    f"border: 1px solid {SURFACE_RAISED}; border-radius: {RADIUS_LG}; "
    f"font-size: {FONT_SMALL}px; color: {TEXT_MUTED}; }}"
)


def flush_list_style(last: bool = True) -> str:
    """Edge-to-edge QListWidget face, same corner contract as flush tables."""
    bottom = "8px" if last else "0px"
    return (
        f"QListWidget {{ background: {SURFACE_CARD}; border: none; "
        "border-top-left-radius: 0px; border-top-right-radius: 0px; "
        "border-bottom-left-radius: " + bottom + "; "
        "border-bottom-right-radius: " + bottom + "; "
        f"font-size: {FONT_SMALL}px; color: {TEXT_MUTED}; }}"
        + scrollbar_lane_qss("QListWidget")
    )


def tree_style(*, flush: bool = True, row_height: int | None = 30) -> str:
    """Build the standard tree chrome (file manifest, metadata field list).

    flush=True: square corners and no frame — the tree sits flush inside
    a card, its header meeting the card's top bar. flush=False: the tree
    keeps its own 8px frame (trees that live inside a card body).

    row_height=None leaves the row height to the tree (rows that host
    their own widgets, e.g. the per-field status combo).

    The header rules and scrollbar lanes come from the theme mixins, so
    every tree in the app wears the same header.
    """
    frame = (
        "border: none;"
        if flush
        else f"border: 1px solid {SURFACE_RAISED}; border-radius: 8px;"
    )
    item = (
        f"QTreeView::item {{ height: {row_height}px; border: none; }} "
        if row_height
        else "QTreeView::item { border: none; } "
    )
    try:
        from ui.icons import tree_branch_qss as _branch_qss

        branch = _branch_qss()
    except Exception:
        branch = ""
    return (
        f"QTreeView {{ background: {SURFACE_CARD}; {frame} "
        f"font-size: {FONT_SMALL}px; color: {TEXT_PRIMARY}; }} "
        + item
        + f"QTreeView::item:hover {{ background: {SURFACE_SUBTLE}; }} "
        f"QTreeView::item:selected {{ background: {SURFACE_TINT}; "
        f"color: {TEXT_PRIMARY}; }} "
        + header_section_qss(flush=flush)
        + scrollbar_lane_qss("QTreeView")
        + branch
    )


class AppTree(QTreeView):
    """Standard tree view — the tree sibling of AppTable.

    Same contract as AppTable: themed header with square end caps when
    flush inside a card, transparent scrollbar lanes, no grid, movable
    and resizable columns.

    A view (not a QTreeWidget): the trees in the app are model-driven
    (the file manifest builds its own model with header data), so the
    column titles come from the model. Models store titles in sentence
    case exactly as painted, so Qt measures the text it draws.
    """

    user_layout_changed = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        row_height: int = 30,
        flush: bool = True,
    ) -> None:
        super().__init__(parent)
        self.setHeader(SortArrowHeaderView(Qt.Horizontal, self))
        self.setHeaderHidden(False)
        self.setUniformRowHeights(False)
        self.setExpandsOnDoubleClick(True)
        self.setAnimated(True)
        self.setIndentation(18)
        self.setRootIsDecorated(True)
        self.setFrameStyle(QFrame.NoFrame)
        self.setStyleSheet(tree_style(flush=flush, row_height=row_height))
        self._fitting = False
        hdr = self.header()
        hdr.setSectionsMovable(True)
        hdr.setSectionsClickable(True)
        # A narrow section elides its label instead of clipping it.
        hdr.setTextElideMode(Qt.ElideRight)
        # Hovering an elided column gives the full title back.
        self._header_tip = _HeaderTooltipFilter(hdr)
        hdr.installEventFilter(self._header_tip)
        hdr.sectionResized.connect(self._on_user_section_resized)
        hdr.sectionMoved.connect(self._on_user_section_moved)

    def _on_user_section_resized(self, logical: int, *_args) -> None:
        if self._fitting:
            return
        if not _section_is_user_resizable(self.header(), logical):
            return
        self.user_layout_changed.emit()

    def _on_user_section_moved(self, *_args) -> None:
        if self._fitting:
            return
        self.user_layout_changed.emit()

    def fit_columns_to_contents(self, *, floors: dict | None = None) -> None:
        """Size every column to its content, honouring per-column floors.

        Signals stay blocked: a content fit is the app's doing, not the
        user's, so it must never be persisted as a user resize (the
        file manifest used to lose its saved widths on every refresh for
        exactly this reason).
        """
        floors = floors or {}
        hdr = self.header()
        self._fitting = True
        hdr.blockSignals(True)
        try:
            for i in range(hdr.count()):
                try:
                    self.resizeColumnToContents(i)
                except Exception:
                    continue
                floor = int(floors.get(i, 0) or 0)
                if floor and self.columnWidth(i) < floor:
                    try:
                        self.setColumnWidth(i, floor)
                    except Exception:
                        pass
        finally:
            hdr.blockSignals(False)
            self._fitting = False


class AppTreeWidget(QTreeWidget):
    """Standard tree widget — the QTreeWidget sibling of AppTree.

    Same contract as AppTree: themed chrome and user_layout_changed
    when the *user* resizes or moves a column (the only layout change
    that may be persisted).

    A QTreeWidget (not a QTreeView): the trees that host their own cell
    widgets — the metadata field rules with their per-field combo —
    build their items directly.
    """

    user_layout_changed = Signal()

    def setHeaderLabels(self, labels) -> None:  # noqa: N802 (Qt naming)
        """Set the column titles in sentence case, as painted.

        Same rule as AppTable: the stored label is the painted label, so
        Qt measures exactly what it draws and a narrow section elides.
        """
        super().setHeaderLabels([str(label) for label in labels])

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        row_height: int | None = None,
        flush: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setHeader(SortArrowHeaderView(Qt.Horizontal, self))
        self.setUniformRowHeights(False)
        self.setExpandsOnDoubleClick(True)
        self.setAnimated(True)
        self.setIndentation(18)
        self.setRootIsDecorated(True)
        self.setFrameStyle(QFrame.NoFrame)
        self.setStyleSheet(tree_style(flush=flush, row_height=row_height))
        self._fitting = False
        hdr = self.header()
        hdr.setSectionsMovable(True)
        hdr.setSectionsClickable(True)
        # A narrow section elides its label instead of clipping it.
        hdr.setTextElideMode(Qt.ElideRight)
        # Hovering an elided column gives the full title back.
        self._header_tip = _HeaderTooltipFilter(hdr)
        hdr.installEventFilter(self._header_tip)
        hdr.sectionResized.connect(self._on_user_section_resized)
        hdr.sectionMoved.connect(self._on_user_section_moved)

    def _on_user_section_resized(self, logical: int, *_args) -> None:
        if self._fitting:
            return
        if not _section_is_user_resizable(self.header(), logical):
            return
        self.user_layout_changed.emit()

    def _on_user_section_moved(self, *_args) -> None:
        if self._fitting:
            return
        self.user_layout_changed.emit()


def make_action_button(
    text: str,
    *,
    kind: str = "secondary",
    size: str | None = "md",
    tip: str = "",
    parent: QWidget | None = None,
) -> AppButton:
    """Build an action button carrying the scoped button sheet.

    A widget-level stylesheet replaces the application sheet for that
    subtree, so a button inside a styled panel does not paint its face
    from the app-level rules. The scoped sheet comes from the same
    generator as the app-level rules (``theme.button_qss``), so the two
    cannot drift - and a view never writes button CSS itself.
    """
    btn = AppButton(text, kind=kind, size=size, parent=parent, tip=tip)
    btn.setStyleSheet(button_qss(kind, selector="QPushButton"))
    return btn


def make_multiline_input(
    placeholder: str = "",
    *,
    height: int = 120,
    font_size: int = FONT_SMALL,
    read_only: bool = False,
    mono: bool = False,
    plain: bool = False,
    fixed: bool = True,
    min_height: int | None = None,
    parent: QWidget | None = None,
) -> QTextEdit | QPlainTextEdit:
    """Build the standard multi-line text input.

    The sheet repeats the app-level input rules (a widget-level sheet
    replaces them for that widget), from the theme's mixin.

    ``plain`` builds a QPlainTextEdit (the lighter widget, for a form
    field); ``fixed`` gives the field a fixed height, ``min_height`` only
    a floor (for a dialog that grows with its content).
    """
    selector = "QPlainTextEdit" if plain else "QTextEdit"
    field = QPlainTextEdit(parent) if plain else QTextEdit(parent)
    field.setPlaceholderText(placeholder)
    if min_height is not None:
        field.setMinimumHeight(min_height)
    elif fixed:
        field.setFixedHeight(height)
    field.setReadOnly(read_only)
    field.setStyleSheet(
        input_qss(
            selector,
            font_size=font_size,
            family=MONO_FAMILY if mono else None,
        )
    )
    return field


def make_plain_text_view(
    placeholder: str = "",
    *,
    font_size: int = FONT_SMALL,
    parent: QWidget | None = None,
) -> QPlainTextEdit:
    """Build the standard read-only plain-text view (the log page)."""
    view = QPlainTextEdit(parent)
    view.setPlaceholderText(placeholder)
    view.setReadOnly(True)
    view.setStyleSheet(
        input_qss("QPlainTextEdit", font_size=font_size, family=MONO_FAMILY)
    )
    return view


def make_list(
    *,
    flush: bool = False,
    last: bool = True,
    parent: QWidget | None = None,
) -> QListWidget:
    """Build the standard list (findings checklist, dataset timeline).

    flush=True paints the list edge to edge inside a card. ``last`` says
    whether the list is the last thing in that card, so the list paints
    the card's bottom corners.
    """
    lst = QListWidget(parent)
    lst.setStyleSheet(flush_list_style(last=last) if flush else _FRAMED_LIST_STYLE)
    return lst


def make_checkbox(
    text: str,
    *,
    checked: bool = False,
    parent: QWidget | None = None,
) -> QCheckBox:
    """Build the standard check box (a response checklist item)."""
    box = QCheckBox(text, parent)
    box.setChecked(checked)
    box.setStyleSheet(
        f"QCheckBox {{ color: {TEXT_PRIMARY}; font-size: {FONT_BODY}px; spacing: 8px; }} "
        # The indicator's edge is a control boundary: 3:1, like every
        # other control in the app.
        f"QCheckBox::indicator {{ width: 16px; height: 16px; "
        f"border: 1px solid {BORDER_CONTROL}; border-radius: {RADIUS_LG}; "
        f"background: {SURFACE_CARD}; }} "
        f"QCheckBox::indicator:checked {{ background: {ACCENT_PRIMARY}; "
        f"border: 1px solid {ACCENT_PRIMARY}; }} "
        f"QCheckBox:disabled {{ color: {TEXT_DISABLED}; }}"
    )
    return box


def make_progress_bar(
    *,
    height: int = 6,
    parent: QWidget | None = None,
) -> QProgressBar:
    """Build the standard progress bar (a thin fill, no text)."""
    bar = QProgressBar(parent)
    bar.setTextVisible(False)
    bar.setFixedHeight(height)
    bar.setStyleSheet(
        f"QProgressBar {{ background: {SURFACE_SUBTLE}; "
        f"border: 1px solid {BORDER_SUBTLE}; border-radius: {RADIUS_LG}; }} "
        f"QProgressBar::chunk {{ background: {ACCENT_PRIMARY}; "
        f"border-radius: {RADIUS_LG}; }}"
    )
    return bar


def set_badge_label(
    badge: QLabel,
    text: str,
    *,
    label: str = "",
    background: str | None = None,
    foreground: str | None = None,
    border: str | None = None,
    mono: bool = False,
    font_size: int = FONT_MICRO,
    padding: str = "0 6px",
) -> QLabel:
    """Re-dress a live badge: new text, new face, same kit rule.

    A badge whose words change (a status pill that flips from
    "Loading" to "In Review") has to change its colours with them. The
    kit owns that, so a view never reaches into the theme for the
    badge's colours - and the badge cannot end up wearing a different
    face from the one the kit built.
    """
    badge.setText(text)
    if background and foreground:
        badge.setStyleSheet(
            badge_qss(
                background,
                foreground,
                border or BORDER_SUBTLE,
                font_size=font_size,
                padding=padding,
            )
        )
    else:
        badge.setStyleSheet(label_badge_style(label or text))
    if mono:
        badge.setStyleSheet(
            badge.styleSheet() + f" QLabel {{ font-family: {MONO_FAMILY}; }}"
        )
    return badge


def make_badge(
    text: str,
    *,
    label: str = "",
    background: str | None = None,
    foreground: str | None = None,
    border: str | None = None,
    mono: bool = False,
    font_size: int = FONT_MICRO,
    padding: str = "0 6px",
    parent: QWidget | None = None,
) -> QLabel:
    """Build a status badge wearing the role colours of its label.

    The label drives the colour (a curation label picks a role), so two
    badges of the same family never drift apart. A caller that already
    knows its role (a check result: PASS / FAIL / SKIP) may pass the
    three role colours explicitly.
    """
    return set_badge_label(
        QLabel("", parent),
        text,
        label=label,
        background=background,
        foreground=foreground,
        border=border,
        mono=mono,
        font_size=font_size,
        padding=padding,
    )


class _ElidedChipButton(QPushButton):
    """Chip label half that elides its title instead of clipping it.

    A dataset title runs well past the chip's max width. QPushButton
    clips the text mid-glyph and the last letters collide with the close
    half; eliding keeps a readable title with an ellipsis and the full
    title stays in the tooltip.
    """

    # Horizontal text inset from _split_chip_qss (12px each side + frame).
    _TEXT_INSET = 28

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._full_text = text
        self._shown_text = text

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().resizeEvent(event)
        self._apply_elide()

    def _apply_elide(self) -> None:
        width = max(0, self.width() - self._TEXT_INSET)
        shown = self.fontMetrics().elidedText(
            self._full_text, Qt.ElideRight, width
        )
        if shown != self._shown_text:
            self._shown_text = shown
            self.setText(shown)


def make_split_chip(
    label: str,
    *,
    active: bool = False,
    tip: str = "",
    close_tip: str = "",
    on_open=None,
    on_close=None,
    parent: QWidget | None = None,
) -> QFrame:
    """Build the dataset chip: a label half joined to a close half.

    The chip is two halves of one control - the label opens the dataset,
    the x closes it - so they share a border, a radius and a height.
    """
    chip = QFrame(parent)
    chip.setObjectName("DatasetChip")
    chip.setStyleSheet(transparent_surface_qss("DatasetChip"))
    lay = QHBoxLayout(chip)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)

    open_btn = _ElidedChipButton(label)
    open_btn.setCursor(Qt.PointingHandCursor)
    open_btn.setToolTip(tip or label)
    open_btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
    open_btn.setFixedHeight(32)
    open_btn.setMaximumWidth(240)
    open_btn.setMinimumWidth(72)
    open_btn.setStyleSheet(_split_chip_qss(active, "left"))
    if on_open is not None:
        open_btn.clicked.connect(on_open)
    lay.addWidget(open_btn)

    close_btn = QPushButton()
    close_btn.setCursor(Qt.PointingHandCursor)
    close_btn.setToolTip(close_tip or t("main.chip_close", label=label))
    close_btn.setAccessibleName(close_tip or t("main.chip_close", label=label))
    close_btn.setFixedSize(32, 32)
    try:
        from ui.icons import icon as _chip_icon

        close_btn.setIcon(
            _chip_icon("x", color=TEXT_PRIMARY if active else TEXT_ON_TINT)
        )
        close_btn.setIconSize(QSize(12, 12))
    except Exception:
        close_btn.setText("x")
    close_btn.setStyleSheet(_split_chip_qss(active, "right"))
    if on_close is not None:
        close_btn.clicked.connect(on_close)
    lay.addWidget(close_btn)
    return chip


def _split_chip_qss(active: bool, part: str) -> str:
    """Build the face of one half of the dataset chip."""
    if active:
        bg, fg, border = SURFACE_TINT, TEXT_PRIMARY, ACCENT_PRIMARY
    else:
        bg, fg, border = SURFACE_CARD, TEXT_PRIMARY, BORDER_SUBTLE
    if part == "left":
        edges = "border-top-left-radius: 8px; border-bottom-left-radius: 8px;"
        padding = "padding: 0 12px;"
    else:
        edges = (
            "border-left: none; border-top-right-radius: 8px; "
            "border-bottom-right-radius: 8px;"
        )
        fg = TEXT_PRIMARY if active else TEXT_ON_TINT
        padding = "padding: 0;"
    hover = (
        f"QPushButton:hover {{ color: {TEXT_DANGER}; "
        f"border-color: {TEXT_DANGER}; }}"
        if part == "right"
        else f"QPushButton:hover {{ border-color: {ACCENT_PRIMARY}; }}"
    )
    return (
        f"QPushButton {{ background: {bg}; color: {fg}; border: 1px solid {border}; "
        f"{edges} {padding} font-size: {FONT_CAPTION}px; font-weight: 700; "
        f"text-align: left; }}"
        + hover
    )


def make_page_heading(title: str, subtitle: str = "") -> tuple:
    """Build the standard full-page heading (title + optional subtitle).

    One contract for every top-level page (Settings, Review configuration,
    Log, About, dataset page): the title uses the theme's ``HeadlineLG``
    token, the subtitle the ``BodyMD`` token. No inline stylesheet — the
    theme owns the look, so the pages cannot drift apart again (each page
    used to invent its own size/weight/colour).

    Returns (title_label, subtitle_label); subtitle_label is None when no
    subtitle text was given.
    """
    head = QLabel(title)
    head.setObjectName("HeadlineLG")
    sub = None
    if subtitle:
        sub = QLabel(subtitle)
        sub.setObjectName("BodyMD")
        sub.setWordWrap(True)
    return head, sub


def make_section_heading(title: str) -> QLabel:
    """Section heading inside a page or card (``HeadlineMD`` token)."""
    lbl = QLabel(title)
    lbl.setObjectName("HeadlineMD")
    return lbl


def make_body_label(text: str = "", *, wrap: bool = True) -> QLabel:
    """Body text (``BodyMD`` token)."""
    lbl = QLabel(text)
    lbl.setObjectName("BodyMD")
    lbl.setWordWrap(wrap)
    return lbl


def make_caption_label(text: str = "", *, wrap: bool = True) -> QLabel:
    """Small caption text (``CaptionSM`` token: 11px, muted).

    The quietest text in the app: status strips, hints, footers.
    """
    lbl = QLabel(text)
    lbl.setObjectName("CaptionSM")
    lbl.setWordWrap(wrap)
    return lbl


def make_field_label(text: str = "", *, wrap: bool = True) -> QLabel:
    """Field / metric label using the LabelStrongSM token.

    11px semibold primary text colour. The label above or beside a
    value: a metric name, a field name, a section label inside a card.
    Strong, never muted: the label is what the user reads to find the
    value next to it.
    """
    lbl = QLabel(text)
    lbl.setObjectName("LabelStrongSM")
    lbl.setWordWrap(wrap)
    return lbl


def make_small_body_label(text: str = "", *, wrap: bool = True) -> QLabel:
    """Small body text (``BodySM`` token: 12px, muted)."""
    lbl = QLabel(text)
    lbl.setObjectName("BodySM")
    lbl.setWordWrap(wrap)
    return lbl


def make_card_title(text: str = "") -> QLabel:
    """Card title (``CardTitle`` token: 15px, semibold)."""
    lbl = QLabel(text)
    lbl.setObjectName("CardTitle")
    return lbl


def make_metric_value(text: str = "") -> QLabel:
    """Metric-card value (``DisplayLG`` token).

    The number slot of a dashboard metric card: 22px bold. Distinct from
    ``HeadlineLG`` (page titles are 22px semibold).
    """
    lbl = QLabel(text)
    lbl.setObjectName("DisplayLG")
    return lbl


class ElidedLabel(QLabel):
    """Label that elides its text instead of widening the layout.

    A long title (a dataset name, a metric caption) must never push the
    page wider than the window: the label keeps a minimum width of zero,
    elides the tail to whatever room it is given, and keeps the full
    text in its tooltip so nothing is lost.
    """

    def __init__(
        self,
        text: str = "",
        parent: QWidget | None = None,
        *,
        mode: "Qt.ElideMode" = Qt.ElideRight,
        object_name: str = "",
    ) -> None:
        super().__init__(parent)
        self._full_text = ""
        self._shown = ""
        self._mode = mode
        # Ignored: the widget may be squeezed; the layout must not reserve
        # the width of the full string.
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumWidth(0)
        if object_name:
            # Set before the first setText: the elide width is measured
            # with the themed font, not the default one.
            self.setObjectName(object_name)
        if text:
            self.setText(text)

    def fullText(self) -> str:
        """Return the un-elided text (the tooltip carries it as well)."""
        return self._full_text

    def setText(self, text: str) -> None:  # noqa: N802 (Qt naming)
        self._full_text = text or ""
        self.setToolTip(self._full_text)
        self._apply_elide()

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().resizeEvent(event)
        self._apply_elide()

    def _apply_elide(self) -> None:
        shown = self.fontMetrics().elidedText(
            self._full_text, self._mode, max(0, self.width())
        )
        if shown == self._shown:
            return
        self._shown = shown
        super().setText(shown)


def make_elided_label(
    text: str = "",
    *,
    mode: "Qt.ElideMode" = Qt.ElideRight,
    object_name: str = "",
    parent: QWidget | None = None,
) -> ElidedLabel:
    """Build a label that elides its tail rather than widening its container.

    ``object_name`` names the theme token the label wears (for example
    ``"HeadlineMD"``), so an eliding label looks exactly like the static
    one it replaces.
    """
    return ElidedLabel(text, parent, mode=mode, object_name=object_name)


def make_reset_columns_button(
    name: str,
    *,
    tip: str = "",
    accessible_name: str = "",
    fallback_text: str = "Reset",
    parent: QWidget | None = None,
) -> AppButton:
    """Ghost icon button that resets a table's columns to their defaults.

    The same affordance everywhere (file manifest, metadata fields,
    extensions): a 32px ghost button with the rotate-ccw icon, an
    accessible name and a tooltip.
    """
    btn = AppButton("", kind="ghost", size="sm", parent=parent)
    btn.setFixedSize(32, 32)
    btn.setAccessibleName(accessible_name or f"Reset {name} columns")
    try:
        from ui.icons import icon as _icon

        btn.setIcon(_icon("rotate-ccw"))
    except Exception:
        btn.setText(fallback_text)
    btn.setToolTip(tip or t("common.reset_columns_tip"))
    return btn


def make_card(title: str, parent: QWidget | None = None) -> tuple:
    """Build a standard white card (8px unified radius) with a header bar.

    Returns (card, body_layout, title_label, header_layout) — append extra
    header widgets (summaries, combos, filters) to header_layout.
    """
    card = QFrame(parent)
    card.setObjectName("Card")
    card.setStyleSheet(
        f"QFrame#Card {{ background: {SURFACE_CARD}; "
        f"border: 1px solid {BORDER_SUBTLE}; border-radius: 8px; }}"
    )
    outer = QVBoxLayout(card)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)
    top = QFrame()
    # Scoped (#id): a bare `QFrame {...}` rule would restyle every QFrame
    # below this bar — inline scope beats app-level rules subtree-wide.
    top.setObjectName("CardTopBar")
    top.setStyleSheet(
        f"QFrame#CardTopBar {{ background: {SURFACE_PAGE}; border-bottom: 1px solid {SURFACE_SUBTLE}; "
        "border-top-left-radius: 8px; border-top-right-radius: 8px; }"
    )
    top_lay = QHBoxLayout(top)
    top_lay.setContentsMargins(16, 12, 16, 12)
    top_lay.setSpacing(12)
    title_lbl = QLabel(title)
    title_lbl.setObjectName("CardTitle")
    top_lay.addWidget(title_lbl)
    top_lay.addStretch(1)
    outer.addWidget(top)
    body = QVBoxLayout()
    body.setContentsMargins(16, 12, 16, 12)
    body.setSpacing(8)
    wrap = QWidget()
    wrap.setLayout(body)
    wrap.setObjectName("CardBodyWrap")
    wrap.setStyleSheet(transparent_surface_qss("CardBodyWrap"))
    outer.addWidget(wrap)
    return card, body, title_lbl, top_lay


def _wrap_tip(*paragraphs: str, width: int = 76) -> str:
    """Join tooltip paragraphs with blank lines, wrapped for readability."""
    chunks = []
    for paragraph in paragraphs:
        text = " ".join(str(paragraph).split())
        if text:
            chunks.append(textwrap.fill(text, width=width))
    return "\n\n".join(chunks)


def add_info_tip(header_layout, *paragraphs: str, name: str = "") -> QToolButton:
    """Add a small Lucide (i) button right after a card title.

    The explanation lives in the tooltip, so section headers read as
    "Auto-Checks (i)" instead of carrying a permanent help paragraph.
    Clicking shows the same text, for touch and pen input.
    """
    from ui.icons import icon as _icon

    tip = _wrap_tip(*paragraphs)
    btn = QToolButton()
    btn.setObjectName("InfoTip")
    try:
        btn.setIcon(_icon("info", color=TEXT_ON_TINT, size=14))
    except Exception:
        btn.setText("i")
    btn.setIconSize(QSize(14, 14))
    # 32px: the help dot is a target like any other, and 24px was below
    # the app's own hit-target floor.
    btn.setFixedSize(32, 32)
    btn.setAutoRaise(True)
    btn.setCursor(Qt.WhatsThisCursor)
    btn.setToolTip(tip)
    btn.setAccessibleName(
        t("common.about_named", name=name) if name else t("common.section_help")
    )
    btn.setAccessibleDescription(tip)
    btn.setStyleSheet(
        "QToolButton#InfoTip { background: transparent; border: none; "
        "border-radius: 16px; padding: 0; }"
        f"QToolButton#InfoTip:hover {{ background: {SURFACE_TINT}; }}"
    )
    btn.clicked.connect(
        lambda: QToolTip.showText(btn.mapToGlobal(btn.rect().bottomLeft()), tip, btn)
    )
    header_layout.insertWidget(1, btn)
    return btn


def make_search_field(placeholder: str, parent: QWidget | None = None, *, height: int = 36,
                      min_width: int = 220) -> QLineEdit:
    """Build a standard search box (SearchField style: rounded, 13px text)."""
    field = QLineEdit(parent)
    field.setObjectName("SearchField")
    field.setPlaceholderText(placeholder)
    field.setFixedHeight(height)
    field.setMinimumWidth(min_width)
    field.setClearButtonEnabled(True)
    field.setStyleSheet(
        # The field's own sheet replaces the app-level input rules, so it
        # repeats them: the control edge (3:1, not the decorative card
        # edge) and the placeholder colour (4.5:1).
        f"QLineEdit#SearchField {{ background: {SURFACE_CARD}; "
        f"border: 1px solid {BORDER_CONTROL}; border-radius: 8px; "
        f"padding-left: 12px; font-size: {FONT_BODY}px; "
        f"selection-background-color: {PRIMARY_FIXED}; }} "
        f"QLineEdit#SearchField:focus {{ border: 1px solid {ACCENT_FOCUS_RING}; }} "
        f"QLineEdit#SearchField::placeholder-text {{ color: {TEXT_PLACEHOLDER}; }}"
    )
    return field


def make_line_edit(placeholder: str = "", parent: QWidget | None = None, *,
                   height: int = 36, password: bool = False) -> QLineEdit:
    """Build a standard form field: same height/focus ring as make_search_field."""
    field = QLineEdit(parent)
    field.setObjectName("SearchField")
    field.setPlaceholderText(placeholder)
    field.setFixedHeight(height)
    if password:
        field.setEchoMode(QLineEdit.Password)
    field.setStyleSheet(
        f"QLineEdit#SearchField {{ background: {SURFACE_CARD}; "
        f"border: 1px solid {BORDER_CONTROL}; border-radius: 8px; "
        f"padding-left: 12px; font-size: {FONT_BODY}px; "
        f"selection-background-color: {PRIMARY_FIXED}; }} "
        f"QLineEdit#SearchField:focus {{ border: 1px solid {ACCENT_FOCUS_RING}; }} "
        f"QLineEdit#SearchField::placeholder-text {{ color: {TEXT_PLACEHOLDER}; }}"
    )
    return field


class _NoWheelCombo(QComboBox):
    """QComboBox that ignores the mouse-wheel until it has been clicked.

    Stops scroll-over accidents: wheeling over a dropdown you never
    opened (e.g. the Required/Optional level combos while scrolling the
    page) would otherwise flip the value. First click arms the wheel
    (and opens the popup); focus-out disarms it again.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._wheel_armed = False

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        self._wheel_armed = True
        try:
            super().mousePressEvent(event)
        except Exception:
            pass

    def focusOutEvent(self, event) -> None:  # type: ignore[override]
        self._wheel_armed = False
        try:
            super().focusOutEvent(event)
        except Exception:
            pass

    def wheelEvent(self, event) -> None:  # type: ignore[override]
        try:
            if not self._wheel_armed:
                event.ignore()
                return
        except Exception:
            pass
        try:
            super().wheelEvent(event)
        except Exception:
            pass


def make_combo(items=None, parent: QWidget | None = None, *, height: int = 36,
               min_width: int = 130, tip: str = "") -> QComboBox:
    """Build a standard dropdown (themed chevron, 12px semibold entries).

    items: list of labels or (label, data) tuples. Wheel-safe: the wheel
    only scrolls the value after the dropdown has been clicked open once.
    """
    combo = _NoWheelCombo(parent)
    combo.setFixedHeight(height)
    combo.setMinimumWidth(min_width)
    combo.setCursor(Qt.PointingHandCursor)
    if tip:
        combo.setToolTip(tip)
    for entry in items or []:
        if isinstance(entry, (tuple, list)):
            combo.addItem(str(entry[0]), entry[1] if len(entry) > 1 else None)
        else:
            combo.addItem(str(entry))
    return combo


class PaneFooter(QFrame):
    """Shared Save/Revert footer for stack pages.

    One vocabulary for pages that edit durable configuration: Settings
    (General + Extensions tabs) and Review configuration. The status label
    carries the last save/revert message; the dirty chip is opt-in so each
    page can show it only while it has unsaved edits.

    Signals:
        saveRequested — the page should persist its edits.
        revertRequested — the page should discard and reload.
    """

    saveRequested = Signal()
    revertRequested = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        save_text: str = "",
        revert_text: str = "",
        save_tip: str = "",
        revert_tip: str = "",
    ) -> None:
        super().__init__(parent)
        self.setObjectName("PaneFooter")
        self.setStyleSheet(
            f"QFrame#PaneFooter {{ background: transparent; "
            f"border-top: 1px solid {BORDER_SUBTLE}; }}"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(8)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
        )
        self.status.setObjectName("CaptionSM")
        layout.addWidget(self.status, 1)
        self.dirty_chip = QLabel(t("common.dirty_chip"))
        self.dirty_chip.setObjectName("WarningSM")
        self.dirty_chip.setToolTip(t("common.dirty_tip"))
        self.dirty_chip.hide()
        layout.addWidget(self.dirty_chip)
        self.revert_btn = make_action_button(
            revert_text or t("common.revert"), kind="secondary", size="sm", tip=revert_tip
        )
        self.revert_btn.clicked.connect(self.revertRequested)
        layout.addWidget(self.revert_btn)
        self.save_btn = make_action_button(
            save_text or t("common.save"), kind="primary", size="sm", tip=save_tip
        )
        self.save_btn.clicked.connect(self.saveRequested)
        layout.addWidget(self.save_btn)

    def set_status(self, text: str) -> None:
        self.status.setText(text or "")

    def set_dirty(self, dirty: bool) -> None:
        self.dirty_chip.setVisible(bool(dirty))
        self.revert_btn.setEnabled(bool(dirty))


class WorkflowRail(QWidget):
    """Compact six-step progress rail for a dataset.

    Guidance, not a gate: every step is clickable in every state, and the
    widget itself runs nothing (it only emits the clicked step's key). State
    comes from the pure :func:`ui.workflow.derive_workflow`; the current
    step also carries bold text and an accessible name so the meaning never
    depends on colour alone.
    """

    stepClicked = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("WorkflowRail")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(4)
        self.buttons: dict[str, QPushButton] = {}
        self._indexes: dict[str, int] = {}
        for i, key in enumerate(STEP_ORDER):
            self._indexes[key] = i + 1
            btn = QPushButton("")
            btn.setObjectName("WorkflowStep")
            btn.setFlat(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setMinimumWidth(0)
            btn.clicked.connect(lambda _c, k=key: self.stepClicked.emit(k))
            layout.addWidget(btn)
            self.buttons[key] = btn
            if i < len(STEP_ORDER) - 1:
                connector = QLabel("\u203a")
                connector.setObjectName("WorkflowSeparator")
                layout.addWidget(connector)
        layout.addStretch(1)
        self.hint = QLabel("")
        self.hint.setObjectName("WorkflowHint")
        self.hint.setWordWrap(False)
        self.hint.setMinimumWidth(0)
        self.hint.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.hint.setObjectName("CaptionSM")
        layout.addWidget(self.hint)

    @staticmethod
    def _style_for(state: str) -> str:
        """Return the step's face for its state - the theme owns the rule."""
        return workflow_step_qss(state)

    def set_workflow(self, workflow: Workflow) -> None:
        """Paint each step and the next-step hint; never disables a step."""
        for step in workflow.steps:
            btn = self.buttons.get(step.key)
            if btn is None:
                continue
            number = str(self._indexes.get(step.key, 0))
            done = step.state == "done"
            # Done steps lead with the app's Lucide check, not a text
            # glyph; the number stays for every other state.
            btn.setText(f"{'  ' if done else number + '  '}{step.label}")
            btn.setIconSize(QSize(14, 14))
            # A blocked step wears a lock: the state is carried by a mark
            # as well as by colour, so it survives a greyscale print and
            # a colour-blind reader.
            try:
                from ui.icons import icon as _mark_icon

                if done:
                    btn.setIcon(_mark_icon("check", color=TEXT_SUCCESS, size=14))
                elif step.state == "blocked":
                    btn.setIcon(_mark_icon("lock", color=TEXT_BLOCKED, size=12))
                else:
                    btn.setIcon(QIcon())
            except Exception:
                btn.setIcon(QIcon())
            btn.setStyleSheet(self._style_for(step.state))
            btn.setToolTip(step.hint)
            btn.setAccessibleName(step.accessible)
            btn.setAccessibleDescription(step.hint)
        self.hint.setText(workflow.hint)
        self.hint.setToolTip(workflow.hint)
