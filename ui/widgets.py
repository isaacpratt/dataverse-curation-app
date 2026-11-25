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
from collections.abc import Callable, Iterable, Sequence
from typing import Any, cast

from PySide6.QtCore import (
    QEvent,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QEnterEvent,
    QFocusEvent,
    QHelpEvent,
    QIcon,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QResizeEvent,
    QShowEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QSpinBox,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTextEdit,
    QToolButton,
    QToolTip,
    QTreeView,
    QTreeWidget,
    QVBoxLayout,
    QWidget,
)

from ui import theme as _theme
from ui.i18n import t
from ui.ring import RingProgress
from ui.theme import (
    ACCENT_PRIMARY,
    BORDER_SUBTLE,
    BUTTON_OBJECTS,
    CHIP_SHADOW_ALPHA,
    CHIP_SHADOW_BLUR,
    CHIP_SHADOW_DY,
    FONT_BODY,
    FONT_SMALL,
    MONO_FAMILY,
    ON_SURFACE_VARIANT,
    RADIUS_LG,
    RADIUS_SM,
    STATE_ERROR_GRAPHIC,
    STATE_SUCCESS_GRAPHIC,
    SURFACE_TINT,
    apply_elevation,
    badge_qss,
    band_qss,
    button_qss,
    caption_button_qss,
    colour,
    enable_table_copy,
    header_section_qss,
    input_qss,
    label_badge_style,
    page_background_qss,
    role,
    rule_qss,
    scrollbar_lane_qss,
    selection_qss,
    surface_frame_qss,
    transparent_qss,
    transparent_surface_qss,
    workflow_rail_qss,
    workflow_step_qss,
)
from ui.workflow import STEP_ORDER, Workflow


def _active_theme() -> str:
    """Return the role table the app is painting right now.

    Read through the module, not a from-import: ``set_active_theme()``
    rebinds ``ui.theme.ACTIVE_THEME``, and a value imported here would
    stay on the palette the kit was loaded with.
    """
    return _theme.ACTIVE_THEME


def _register(widget: QWidget, name: str, *args: object, **kwargs: object) -> None:
    """Attach a scoped-sheet rebuild to ``widget`` for live theme switches.

    Every factory that bakes its own sheet calls this, so a switch can
    repaint already-built widgets (dv-4jm.7). The spec is plain data - a
    rebuilder name plus its arguments - stored on the widget itself, so it
    dies with the widget and cannot outlive it. Storing a closure here
    instead would capture the widget and form a reference cycle, which
    keeps the Python wrapper alive past the C++ object and crashes the
    process on the next call.

    Colour arguments are passed as **role names** (``"SURFACE_CARD"``), not
    resolved values, so the rebuilder resolves them in the new theme
    (dv-314). A literal is still accepted and simply stays put.
    """
    try:
        specs = getattr(widget, _theme.RETHEME_ATTR, None)
        if not isinstance(specs, list):
            specs = []
        # One spec per builder name: a badge re-dressed twice replaces its
        # own entry, while a button that also carries an icon keeps both.
        specs = [s for s in specs if not (isinstance(s, tuple) and len(s) == 3 and s[0] == name)]
        specs.append((name, args, kwargs))
        setattr(widget, _theme.RETHEME_ATTR, specs)
    except Exception:
        pass


def set_sheet(widget: QWidget, name: str, *args: object, **kwargs: object) -> None:
    """Apply a scoped sheet to ``widget`` and keep it in step with the theme.

    The one call a view makes instead of ``widget.setStyleSheet(...)``:
    it paints now and registers the repaint for the next switch (dv-314).
    An unknown builder name is a programming error and raises, so a typo
    cannot silently leave a sheet that never repaints.
    """
    rebuild = _REBUILDERS.get(name)
    if rebuild is None:
        raise KeyError(name)
    rebuild(widget, *args, **kwargs)
    _register(widget, name, *args, **kwargs)


def _reapply_card(card: QWidget) -> None:
    """Repaint a card and its top bar (one face, two widgets)."""
    theme = _active_theme()
    card.setStyleSheet(
        f"QFrame#Card {{ background: {role('SURFACE_CARD', theme)}; "
        f"border: 1px solid {role('BORDER_SUBTLE', theme)}; border-radius: 8px; }}"
    )
    top = card.findChild(QFrame, "CardTopBar")
    if top is not None:
        top.setStyleSheet(
            f"QFrame#CardTopBar {{ background: {role('SURFACE_PAGE', theme)}; "
            f"border-bottom: 1px solid {role('SURFACE_SUBTLE', theme)}; "
            "border-top-left-radius: 8px; border-top-right-radius: 8px; }"
        )


def _search_field_qss() -> str:
    """Build the shared search/line-edit face from the active role table."""
    theme = _active_theme()
    return (
        f"QLineEdit#SearchField {{ background: {role('SURFACE_CARD', theme)}; "
        f"border: 1px solid {role('BORDER_CONTROL', theme)}; border-radius: 8px; "
        f"padding-left: 12px; font-size: {FONT_BODY}px; "
        f"selection-background-color: {role('ACCENT_TINT', theme)}; }} "
        f"QLineEdit#SearchField:focus {{ border: 1px solid {role('ACCENT_FOCUS_RING', theme)}; }} "
        f"QLineEdit#SearchField::placeholder-text {{ color: {role('TEXT_PLACEHOLDER', theme)}; }}"
    )


def _text_label_qss(color: str, object_name: str) -> str:
    """Build a recoloured label rule; ``color`` may be a role name."""
    if not color:
        return ""
    return f"QLabel#{object_name} {{ color: {colour(color, _active_theme())}; }}"


def _badge_sheet(
    label: str,
    background: str | None,
    foreground: str | None,
    border: str | None,
    font_size: int,
    padding: str,
    mono: bool,
) -> str:
    """Build a badge's sheet from the active role table (kit rule, one place).

    The colours may be role names; ``badge_qss`` resolves them in the active
    theme, so a live switch repaints the badge (dv-314).
    """
    if background and foreground:
        sheet = badge_qss(
            background,
            foreground,
            border or BORDER_SUBTLE,
            font_size=font_size,
            padding=padding,
        )
    else:
        sheet = label_badge_style(label)
    if mono:
        sheet += f" QLabel {{ font-family: {MONO_FAMILY}; }}"
    return sheet


def _apply_icon(widget: Any, name: str, color: str | None, size: int) -> None:
    """Set a Lucide glyph on ``widget``, tinted for the active theme.

    ``name`` may be a documented role (``"sidebar_hide"``) or a bundled
    asset name; ``role_icon`` maps the former and passes the latter through.
    """
    from ui.icons import role_icon

    widget.setIcon(role_icon(name, color=colour(color) if color else None, size=size))


def set_icon(widget: QWidget, name: str, *, color: str | None = None, size: int = 16) -> None:
    """Set a Lucide glyph and keep it in step with the theme (dv-314).

    Icons are bundled SVG tinted by replacing ``currentColor``; the tint is
    baked into a pixmap, so a live switch has to re-tint. ``color`` may be
    a role name (re-resolved on a switch) or a literal.
    """
    _apply_icon(widget, name, color, size)
    _register(widget, "icon", name, color, size)


def _apply_caption_button(widget: Any, kind: str) -> None:
    """Repaint a caption button's sheet and its glyph (dv-314)."""
    widget.setStyleSheet(caption_button_qss(kind, theme=_active_theme()))
    apply_icon = getattr(widget, "_apply_icon", None)
    if callable(apply_icon):
        apply_icon()


# Rebuilders, keyed by the name a factory passes to _register. Each takes
# the widget as its first parameter, so nothing captures it.
_REBUILDERS: dict[str, Any] = {
    "button": lambda w, kind: w.setStyleSheet(
        button_qss(kind, selector="QPushButton", theme=_active_theme())
    ),
    "input": lambda w, selector, font_size, family: w.setStyleSheet(
        input_qss(
            selector,
            font_size=font_size,
            family=family,
            theme=_active_theme(),
        )
    ),
    "checkbox": lambda w: w._apply_sheet(),
    "progress_bar": lambda w: w.setStyleSheet(
        f"QProgressBar {{ background: {role('SURFACE_SUBTLE', _active_theme())}; "
        f"border: 1px solid {role('BORDER_SUBTLE', _active_theme())}; "
        f"border-radius: {RADIUS_LG}; }} "
        f"QProgressBar::chunk {{ background: {role('ACCENT_PRIMARY', _active_theme())}; "
        f"border-radius: {RADIUS_LG}; }}"
    ),
    "card": lambda w: _reapply_card(w),
    "value_chip": lambda w: w._apply_sheet(),
    "pane_footer": lambda w: w._apply_sheet(),
    "status_widget": lambda w: w._apply_sheet(),
    "tree": lambda w, flush, row_height, hover: w.setStyleSheet(
        tree_style(flush=flush, row_height=row_height, hover=hover)
    ),
    "list": lambda w, last, flush: w.setStyleSheet(
        flush_list_style(last=last) if flush else framed_list_style()
    ),
    "flush_table": lambda w, last, header_background, item_padding: w.setStyleSheet(
        flush_table_style(
            last=last,
            header_background=header_background,
            item_padding=item_padding,
        )
    ),
    # --- View-level sheets (dv-314). Colour args are role names. ---
    "page_background": lambda w, names: w.setStyleSheet(
        page_background_qss(*names, theme=_active_theme())
    ),
    "surface_frame": lambda w, background, border, **kw: w.setStyleSheet(
        surface_frame_qss(background, border, theme=_active_theme(), **kw)
    ),
    "band": lambda w, background, border, **kw: w.setStyleSheet(
        band_qss(background, border, theme=_active_theme(), **kw)
    ),
    "rule": lambda w, selector, background: w.setStyleSheet(
        rule_qss(selector, background, theme=_active_theme())
    ),
    "search_field": lambda w: w.setStyleSheet(_search_field_qss()),
    "badge": lambda w, label, background, foreground, border, mono, font_size, padding: (
        w.setStyleSheet(
            _badge_sheet(label, background, foreground, border, font_size, padding, mono)
        )
    ),
    "split_chip": lambda w, active, part: w.setStyleSheet(_split_chip_qss(active, part)),
    "text_label": lambda w, color, object_name: w.setStyleSheet(
        _text_label_qss(color, object_name)
    ),
    "info_tip": lambda w: w.setStyleSheet(
        "QToolButton#InfoTip { background: transparent; border: none; "
        "border-radius: 16px; padding: 0; }"
        f"QToolButton#InfoTip:hover {{ background: {role('SURFACE_TINT', _active_theme())}; }}"
    ),
    "caption_button": lambda w, kind: _apply_caption_button(w, kind),
    "icon": lambda w, name, color, size: _apply_icon(w, name, color, size),
    "workflow_rail": lambda w: w._retheme(),
}


def _retheme_widget(widget: Any) -> int:
    """Repaint one widget's specs. Returns how many ran."""
    specs = getattr(widget, _theme.RETHEME_ATTR, None)
    if not isinstance(specs, list):
        return 0
    run = 0
    for spec in specs:
        if not isinstance(spec, tuple) or len(spec) != 3:
            continue
        name, args, kwargs = spec
        rebuild = _REBUILDERS.get(str(name))
        if rebuild is None:
            continue
        try:
            rebuild(widget, *args, **kwargs)
            run += 1
        except Exception:
            continue
    return run


def _collect_item_icons(widget: Any, items: list[Any]) -> None:
    """Append a tree/list/table's model items to ``items``."""
    if isinstance(widget, QTreeWidget):
        from PySide6.QtWidgets import QTreeWidgetItemIterator

        iterator = QTreeWidgetItemIterator(widget)
        while iterator.value():
            items.append(iterator.value())
            iterator += 1
    elif isinstance(widget, QListWidget):
        items.extend(widget.item(i) for i in range(widget.count()))
    elif isinstance(widget, QTableWidget):
        items.extend(
            widget.item(row, col)
            for row in range(widget.rowCount())
            for col in range(widget.columnCount())
        )


def _retheme_item_icons(widget: Any) -> int:
    """Re-tint the Lucide glyphs on a tree/list/table's model items."""
    from ui.icons import ITEM_ICON_ROLE, set_item_icon

    items: list[Any] = []
    try:
        _collect_item_icons(widget, items)
    except Exception:
        # A dead or half-built model must not abort the whole switch.
        return 0
    run = 0
    for item in items:
        if item is None:
            continue
        spec = item.data(ITEM_ICON_ROLE)
        if not (isinstance(spec, tuple) and len(spec) == 3):
            continue
        try:
            set_item_icon(item, *spec)
            run += 1
        except Exception:
            continue
    return run


def _retheme_all(app: Any) -> int:
    """Repaint every widget carrying a retheme spec. Returns how many ran.

    Walks the *visible* top-level windows and their children, not
    ``app.allWidgets()``: a long session (and the test suite) accumulates
    hidden leaked windows, and walking those is what made a switch
    expensive. A hidden page inside a visible window is still reached, so a
    switch on the dashboard also fixes the detail page for when it is
    shown. A widget in a hidden window is skipped and repainted by the next
    switch after that window is shown.
    """
    run = 0
    roots: list[Any] = []
    try:
        top_levels = app.topLevelWidgets()
    except Exception:
        return run
    for top in top_levels:
        # One dead leaked window must not abort the whole switch.
        try:
            if top.isVisible():
                roots.append(top)
        except Exception:
            continue
    # One paint pass for the whole switch: rebuilding a sheet re-polishes
    # the widget, and letting each one repaint in turn is a visible freeze
    # on a window with a real dataset (dv-314).
    for root in roots:
        try:
            root.setUpdatesEnabled(False)
        except Exception:
            pass
    try:
        for root in roots:
            for widget in [root, *root.findChildren(QWidget)]:
                try:
                    run += _retheme_widget(widget)
                    run += _retheme_item_icons(widget)
                except Exception:
                    # One dead widget must not abort the whole switch.
                    continue
    finally:
        for root in roots:
            try:
                root.setUpdatesEnabled(True)
                root.update()
            except Exception:
                pass
    return run


_theme.set_retheme_hook(_retheme_all)


__all__ = [
    "BUTTON_HEIGHTS",
    "AppButton",
    "AppCheckBox",
    "AppTable",
    "AppTree",
    "AppTreeWidget",
    "ElidedLabel",
    "PaneFooter",
    "RingProgress",
    "SortArrowHeaderView",
    "StatusWidget",
    "WorkflowRail",
    "add_info_tip",
    "fit_tree_height",
    "flush_list_style",
    "flush_table_style",
    "human_size",
    "make_action_button",
    "make_badge",
    "make_body_label",
    "make_caption_label",
    "make_card",
    "make_card_title",
    "make_cell_control",
    "make_checkbox",
    "make_combo",
    "make_elided_label",
    "make_field_label",
    "make_icon_button",
    "make_icon_text_button",
    "make_line_edit",
    "make_list",
    "make_metric_value",
    "make_multiline_input",
    "make_number_field",
    "make_page_heading",
    "make_plain_text_view",
    "make_progress_bar",
    "make_refresh_button",
    "make_reset_columns_button",
    "make_search_field",
    "make_section_heading",
    "make_small_body_label",
    "make_split_chip",
    "make_value_list",
    "set_chip_room_limited",
    "set_flush_table_style",
    "set_icon",
    "set_sheet",
    "tree_style",
]

# Button heights (px) by size token.
# "sm" is 32px, not 28: WCAG 2.5.8 asks for a 24px target, but the
# platform's own menus and toolbars land on 32, and a 28px chip is easy
# to miss with a mouse or a stylus. Every button in the app clears 32.
BUTTON_HEIGHTS: dict[str, int] = {"sm": 32, "md": 36, "lg": 40}

# A chip is a status pill in the header: it sits on the same line as the
# action buttons, so it takes the standard button height instead of being
# stretched to whatever the tallest control in its row happens to be.
CHIP_HEIGHT: int = BUTTON_HEIGHTS["md"]


def human_size(n: int) -> str:
    """Human-readable size with B/KB/MB/GB/TB (dv-005, single helper).

    Decimal scaling, so the divisor is 1000 and the label matches what the
    user reads (KB means 1000 bytes here, not KiB). All call sites share
    this: dashboard, detail, checks tree, download dialog, settings.
    """
    try:
        n_int = int(n)
    except Exception:
        return str(n)
    if n_int < 1000:
        return f"{n_int} B"
    value = float(n_int)
    for unit in ("KB", "MB", "GB", "TB"):
        value /= 1000.0
        if value < 1000 or unit == "TB":
            return f"{value:.1f} {unit}"
    return f"{value:.1f} TB"


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
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if tip:
            self.setToolTip(tip)

    def clicked_to(self, slot: Callable[..., Any]) -> "AppButton":
        """Chainable connect: AppButton("Save").clicked_to(self._on_save)."""
        self.clicked.connect(slot)
        return self


def _section_is_user_resizable(header: QHeaderView, logical: int) -> bool:
    """Tell whether the user could have dragged this section's edge.

    A section the layout owns is never a user gesture, however Qt
    reports the resize: a Stretch or Fixed section, or the last section
    of a header that stretches its last section. Without this check a
    window resize (which re-stretches those sections) would look like a
    user drag and would be persisted as one.
    """
    try:
        if header.sectionResizeMode(logical) != QHeaderView.ResizeMode.Interactive:
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

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.ToolTip:
            header = cast(QHeaderView, obj)
            help_event = cast(QHelpEvent, event)
            try:
                index = header.logicalIndexAt(help_event.pos())
                label = header.model().headerData(
                    index, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole
                )
            except Exception:
                return False
            if index >= 0 and label:
                QToolTip.showText(help_event.globalPos(), str(label), header)
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
        self._arrow.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._arrow.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._arrow.setMouseTracking(False)
        self._arrow.setStyleSheet(transparent_qss("QLabel", theme=_active_theme()))
        self._arrow.hide()
        self._painting = False
        # setSortIndicator / setSortIndicatorShown update the
        # view's viewport, not the header — without this, the label
        # would lag one paint behind the sorted order.
        self.sortIndicatorChanged.connect(self._on_sort_indicator_changed)

    def _on_sort_indicator_changed(self, *_args: Any) -> None:
        if not self._painting:
            self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        section = self.sortIndicatorSection()
        active = (
            self.orientation() == Qt.Orientation.Horizontal
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
            self.orientation() != Qt.Orientation.Horizontal
            or not self.isSortIndicatorShown()
            or not (0 <= section < self.count())
            or self.isSectionHidden(section)
        ):
            self._arrow.hide()
            return
        try:
            from ui.icons import icon

            name = (
                "chevron-down"
                if self.sortIndicatorOrder() == Qt.SortOrder.DescendingOrder
                else "chevron-up"
            )
            pixmap = icon(name, color=ON_SURFACE_VARIANT, size=self._ARROW_PX).pixmap(
                QSize(self._ARROW_PX, self._ARROW_PX)
            )
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


class SelectionDelegate(QStyledItemDelegate):
    """Paint item views without Qt's dotted focus rectangle.

    The row tint marks the selection and the theme's ``focusVisible``
    outline marks keyboard focus on the view itself. Qt's default
    delegate adds a dotted black box around the current item on top of
    both, inset by that view's padding — so the same selection looked
    different in every table (the reported bug). Dropping
    ``State_HasFocus`` for the base paint removes the box everywhere;
    the row tint stays, because selection is a separate state.
    """

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        if option.state & QStyle.StateFlag.State_HasFocus:
            option = QStyleOptionViewItem(option)
            option.state &= ~QStyle.StateFlag.State_HasFocus
        super().paint(painter, option, index)


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

    def setHorizontalHeaderLabels(self, labels: Sequence[str]) -> None:
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
        headers: Sequence[str],
        parent: QWidget | None = None,
        *,
        sortable: bool = True,
        row_height: int = 40,
        stretch_last: bool = True,
        widths: dict[int, int] | None = None,
    ) -> None:
        super().__init__(0, len(headers), parent)
        # The kit header draws the sort arrow itself (see
        # SortArrowHeaderView): the style's native indicator floats in
        # the seam above the header on this Qt build.
        self.setHorizontalHeader(SortArrowHeaderView(Qt.Orientation.Horizontal, self))
        self.setHorizontalHeaderLabels(list(headers))
        hdr = self.horizontalHeader()
        hdr.setStretchLastSection(stretch_last)
        hdr.setSectionsMovable(True)
        hdr.setSectionsClickable(True)
        # A narrow section elides its label instead of clipping it: a
        # centred label clipped on both sides loses its first letter
        # ("SUBMITTING AUTHOR" read as "UBMITTING AUTHOR").
        hdr.setTextElideMode(Qt.TextElideMode.ElideRight)
        # Hovering an elided column gives the full title back.
        self._header_tip = _HeaderTooltipFilter(hdr)
        hdr.installEventFilter(self._header_tip)
        for i in range(len(headers)):
            width = (widths or {}).get(i, 120)
            self.setColumnWidth(i, width)
            hdr.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
        self.setShowGrid(False)
        # NoFrame: the 1px StyledPanel frame would inset every flush table
        # 1px inside its card (770px table in a 772px card); the card border
        # already provides the outline.
        self.setFrameStyle(QFrame.Shape.NoFrame)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(False)
        self.setWordWrap(False)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(row_height)
        # StrongFocus (not NoFocus): the copy KeyPress filter is installed
        # on the table itself, so it only sees events when the table has
        # focus. Visual outline stays off via the stylesheet.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSortingEnabled(sortable)
        # One selection face app-wide, and no dotted focus box (dv-coj).
        self.setItemDelegate(SelectionDelegate(self))
        self._auto_fit = True
        self._fitting = False
        self._fitted = False
        hdr.sectionResized.connect(self._on_user_section_resized)
        hdr.sectionMoved.connect(self._on_user_section_moved)
        enable_table_copy(self)

    def showEvent(self, event: QShowEvent) -> None:
        """First visible paint: fit once the viewport has a real width.

        Populates often run during __init__ (cached dashboard, settings
        reload) when the widget is still hidden — viewport().width() is
        meaningless there, so fit defers to here. Hidden-built cell
        widgets (Settings extensions' Reinstall/Uninstall) keep their
        construction-time geometry until one full layout pass runs.
        """
        super().showEvent(event)
        if self._auto_fit and not self._fitted and self.rowCount() > 0:
            QTimer.singleShot(0, self._fit_after_show)
        QTimer.singleShot(0, self.refresh_cell_geometry)

    def _fit_after_show(self) -> None:
        if self._auto_fit and not self._fitted and self.isVisible():
            self.fit_columns_to_content()

    def refresh_cell_geometry(self) -> None:
        """Force one full layout pass on cell widgets.

        A hidden-built table remembers every cell widget at its
        construction-time width; once visible, the column may have a
        different width, and Qt does not re-lay the widgets until some
        item geometry pass happens. Call this after the table's first
        show so action columns (Reinstall/Uninstall) fit the real cell
        rect. Cheap: one QStyle rediscover of all geometry.
        """
        try:
            self.updateGeometries()
        except Exception:
            # updateGeometries is protected but always present on
            # QAbstractItemView; fall back to a column-width roundtrip of
            # a visible section, which forces the same re-layout.
            try:
                hdr = self.horizontalHeader()
                if hdr is None or hdr.count() == 0:
                    return
                w = hdr.sectionSize(0)
                hdr.resizeSection(0, max(1, w + 1))
                hdr.resizeSection(0, w)
            except Exception:
                pass
        try:
            self.viewport().update()
        except Exception:
            pass

    def populate_guarded(self, row_count: int) -> None:
        """SetRowCount with sorting suppressed so inserts stay in order."""
        was = self.isSortingEnabled()
        self.setSortingEnabled(False)
        self.setRowCount(row_count)
        self.setSortingEnabled(was)

    def _on_user_section_resized(self, logical: int, *_args: Any) -> None:
        """Lock content auto-fit once the user drags a column edge."""
        if self._fitting:
            return
        if not _section_is_user_resizable(self.horizontalHeader(), logical):
            return
        self._auto_fit = False
        self.user_layout_changed.emit()

    def _on_user_section_moved(self, *_args: Any) -> None:
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

    def refit_columns_to_content(self) -> None:
        """Clear the one-shot fit latch and fit again on the next layout.

        A first paint can populate rows before the view has its final
        width (cached dashboard rows during startup, a filter applied while
        the window is still being laid out); the fit then measures against
        a too-small viewport and leaves columns squished. Re-arming here
        makes ``fit_columns_to_content`` retry once the real width is known
        (showEvent / the deferred pass), without touching a layout the
        curator saved or resized by hand.
        """
        if not self._auto_fit:
            return
        self._fitted = False

    def fit_columns_to_content(  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
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
                if mode == QHeaderView.ResizeMode.Stretch:
                    stretch_reserve += max(min_width, min(max_width, int(hdr.sectionSize(i))))
                    continue
                if mode != QHeaderView.ResizeMode.Interactive:
                    continue
                hint = 0
                try:
                    hint = int(hdr.sectionSizeFromContents(i).width())
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
                    targets[i] = max(min_width, round(w * ratio))
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
    theme = _active_theme()
    bottom = "8px" if last else "0px"
    return (
        "QTableWidget { background: " + role("SURFACE_CARD", theme) + "; border: none; "
        "border-top-left-radius: 0px; border-top-right-radius: 0px; "
        "border-bottom-left-radius: " + bottom + "; "
        "border-bottom-right-radius: "
        + bottom
        + "; } "
        + header_section_qss(flush=True, theme=theme)
        + selection_qss("QTableWidget", theme=theme)
        + scrollbar_lane_qss("QTableWidget", theme=theme)
        + (f" QHeaderView {{ background: {header_background}; }}" if header_background else "")
        + (f" QTableWidget::item {{ padding: {item_padding}; }}" if item_padding else "")
    )


def set_flush_table_style(
    table: QTableWidget,
    *,
    last: bool = True,
    header_background: str | None = None,
    item_padding: str | None = None,
) -> None:
    """Apply :func:`flush_table_style` to ``table`` and keep it in step with the theme.

    A table's sheet is scoped, so a live theme switch would otherwise leave
    it on the old palette (dv-4jm.7). Views call this instead of
    ``table.setStyleSheet(flush_table_style(...))``.
    """

    def _apply() -> None:
        table.setStyleSheet(
            flush_table_style(
                last=last,
                header_background=header_background,
                item_padding=item_padding,
            )
        )

    _apply()
    _register(table, "flush_table", last, header_background, item_padding)


def framed_list_style() -> str:
    """Build the framed QListWidget face (a list that lives inside a card body).

    A function, not a module constant: the colours come from the active
    role table, and a constant built at import would stay on the palette
    the kit was loaded with.
    """
    theme = _active_theme()
    return (
        f"QListWidget {{ background: {role('SURFACE_CARD', theme)}; "
        f"border: 1px solid {role('SURFACE_RAISED', theme)}; border-radius: {RADIUS_LG}; "
        f"font-size: {FONT_SMALL}px; color: {role('TEXT_MUTED', theme)}; }}"
    )


def flush_list_style(last: bool = True) -> str:
    """Edge-to-edge QListWidget face, same corner contract as flush tables."""
    bottom = "8px" if last else "0px"
    theme = _active_theme()
    return (
        f"QListWidget {{ background: {role('SURFACE_CARD', theme)}; border: none; "
        "border-top-left-radius: 0px; border-top-right-radius: 0px; "
        "border-bottom-left-radius: " + bottom + "; "
        "border-bottom-right-radius: " + bottom + "; "
        f"font-size: {FONT_SMALL}px; color: {role('TEXT_MUTED', theme)}; }}"
        + scrollbar_lane_qss("QListWidget", theme=theme)
    )


def tree_style(*, flush: bool = True, row_height: int | None = 30, hover: bool = True) -> str:
    """Build the standard tree chrome (file manifest, metadata field list).

    flush=True: square corners and no frame — the tree sits flush inside
    a card, its header meeting the card's top bar. flush=False: the tree
    keeps its own 8px frame (trees that live inside a card body).

    row_height=None leaves the row height to the tree (rows that host
    their own widgets, e.g. the per-field status combo).

    hover=False drops the ``::item:hover`` band for a form-like tree where
    a pointer passing over a row must not look like a selection (dv-ud0).

    The header rules and scrollbar lanes come from the theme mixins, so
    every tree in the app wears the same header.
    """
    theme = _active_theme()
    frame = (
        "border: none;"
        if flush
        else f"border: 1px solid {role('SURFACE_RAISED', theme)}; border-radius: 8px;"
    )
    item = (
        f"QTreeView::item {{ height: {row_height}px; border: none; }} "
        if row_height
        else "QTreeView::item { border: none; } "
    )
    # Branch chevrons are painted by _BranchPainting, not by QSS: the
    # native Windows 11 branch chip ignored ``image: none`` and put a
    # blue accent chevron beside the selected row (dv-coj).
    return (
        f"QTreeView {{ background: {role('SURFACE_CARD', theme)}; {frame} "
        f"font-size: {FONT_SMALL}px; color: {role('TEXT_PRIMARY', theme)}; }} "
        + item
        + selection_qss("QTreeView", hover=hover, theme=theme)
        + header_section_qss(flush=flush, theme=theme)
        + scrollbar_lane_qss("QTreeView", theme=theme)
    )


class _BranchPainting:
    """Draw tree branch chevrons ourselves instead of the native chip.

    The Windows 11 style paints every branch as a grey rounded chip with
    an accent-coloured chevron. On a selected row that chevron sits just
    left of the tint and reads as a 2px blue vertical bar — the stray
    stripe reported in the metadata tree (dv-coj). A Lucide chevron in
    the muted ink is quieter, matches the icon set, and looks the same in
    every tree. The dotted indent guides Qt draws go away with it.
    """

    _BRANCH_PX = 14

    # Supplied by the Qt view base (QTreeView/QTreeWidget); declared so
    # mypy can check this mixin in isolation. Bare annotations create no
    # runtime attribute, so the view's real members win at runtime.
    model: Any
    indentation: Any
    isExpanded: Any

    def drawBranches(
        self, painter: QPainter, rect: QRect, index: QModelIndex | QPersistentModelIndex
    ) -> None:
        """Replace the style's branch painting with one chevron."""
        self._paint_branch(painter, rect, index)

    def _paint_branch(
        self, painter: QPainter, rect: QRect, index: QModelIndex | QPersistentModelIndex
    ) -> None:
        """Draw the expand/collapse chevron for *index*, if it has children."""
        try:
            model = self.model()
        except Exception:
            return
        if model is None or not index.isValid() or not model.hasChildren(index):
            return
        try:
            from ui.icons import icon
            from ui.theme import TEXT_MUTED

            name = "chevron-down" if self.isExpanded(index) else "chevron-right"
            size = self._BRANCH_PX
            pixmap = icon(name, color=TEXT_MUTED, size=size).pixmap(QSize(size, size))
            indent = self.indentation()
            # rect spans all ancestor indents; the last cell is this row's.
            cell = QRect(
                rect.right() - indent + 1,
                rect.top(),
                max(1, indent - 1),
                rect.height(),
            )
            painter.drawPixmap(
                cell.x() + (cell.width() - size) // 2,
                cell.y() + (cell.height() - size) // 2,
                pixmap,
            )
        except Exception:
            pass


class AppTree(_BranchPainting, QTreeView):
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
        self.setHeader(SortArrowHeaderView(Qt.Orientation.Horizontal, self))
        self.setHeaderHidden(False)
        self.setUniformRowHeights(False)
        self.setExpandsOnDoubleClick(True)
        self.setAnimated(True)
        self.setIndentation(18)
        self.setRootIsDecorated(True)
        self.setFrameStyle(QFrame.Shape.NoFrame)

        def _apply() -> None:
            self.setStyleSheet(tree_style(flush=flush, row_height=row_height))

        _apply()
        _register(self, "tree", flush, row_height, True)
        # One selection face app-wide, and no dotted focus box (dv-coj).
        self.setItemDelegate(SelectionDelegate(self))
        self._fitting = False
        hdr = self.header()
        hdr.setSectionsMovable(True)
        hdr.setSectionsClickable(True)
        # A narrow section elides its label instead of clipping it.
        hdr.setTextElideMode(Qt.TextElideMode.ElideRight)
        # Hovering an elided column gives the full title back.
        self._header_tip = _HeaderTooltipFilter(hdr)
        hdr.installEventFilter(self._header_tip)
        hdr.sectionResized.connect(self._on_user_section_resized)
        hdr.sectionMoved.connect(self._on_user_section_moved)

    def _on_user_section_resized(self, logical: int, *_args: Any) -> None:
        if self._fitting:
            return
        if not _section_is_user_resizable(self.header(), logical):
            return
        self.user_layout_changed.emit()

    def _on_user_section_moved(self, *_args: Any) -> None:
        if self._fitting:
            return
        self.user_layout_changed.emit()

    def fit_columns_to_contents(self, *, floors: dict[int, int] | None = None) -> None:
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


class AppTreeWidget(_BranchPainting, QTreeWidget):
    """Standard tree widget — the QTreeWidget sibling of AppTree.

    Same contract as AppTree: themed chrome and user_layout_changed
    when the *user* resizes or moves a column (the only layout change
    that may be persisted).

    A QTreeWidget (not a QTreeView): the trees that host their own cell
    widgets — the metadata field rules with their per-field combo —
    build their items directly.
    """

    user_layout_changed = Signal()

    def setHeaderLabels(self, labels: Sequence[str]) -> None:
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
        hover_tint: bool = True,
    ) -> None:
        super().__init__(parent)
        self.setHeader(SortArrowHeaderView(Qt.Orientation.Horizontal, self))
        self.setUniformRowHeights(False)
        self.setExpandsOnDoubleClick(True)
        self.setAnimated(True)
        self.setIndentation(18)
        self.setRootIsDecorated(True)
        self.setFrameStyle(QFrame.Shape.NoFrame)

        def _apply() -> None:
            self.setStyleSheet(tree_style(flush=flush, row_height=row_height, hover=hover_tint))

        _apply()
        _register(self, "tree", flush, row_height, hover_tint)
        # One selection face app-wide, and no dotted focus box (dv-coj).
        self.setItemDelegate(SelectionDelegate(self))
        self._fitting = False
        hdr = self.header()
        hdr.setSectionsMovable(True)
        hdr.setSectionsClickable(True)
        # A narrow section elides its label instead of clipping it.
        hdr.setTextElideMode(Qt.TextElideMode.ElideRight)
        # Hovering an elided column gives the full title back.
        self._header_tip = _HeaderTooltipFilter(hdr)
        hdr.installEventFilter(self._header_tip)
        hdr.sectionResized.connect(self._on_user_section_resized)
        hdr.sectionMoved.connect(self._on_user_section_moved)

    def _on_user_section_resized(self, logical: int, *_args: Any) -> None:
        if self._fitting:
            return
        if not _section_is_user_resizable(self.header(), logical):
            return
        self.user_layout_changed.emit()

    def _on_user_section_moved(self, *_args: Any) -> None:
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
    btn.setStyleSheet(button_qss(kind, selector="QPushButton", theme=_active_theme()))
    _register(btn, "button", kind)
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

    def _apply() -> None:
        field.setStyleSheet(
            input_qss(
                selector,
                font_size=font_size,
                family=MONO_FAMILY if mono else None,
                theme=_active_theme(),
            )
        )

    _apply()
    _register(field, "input", selector, font_size, MONO_FAMILY if mono else None)
    return field


def make_plain_text_view(
    placeholder: str = "",
    *,
    font_size: int = FONT_SMALL,
    parent: QWidget | None = None,
) -> QPlainTextEdit:
    """Build the standard read-only plain-text view (log, preview, gallery).

    Prose at body size in Inter. The one mono read-only field left in the
    app is the raw metadata view, which opts in through
    ``make_multiline_input(mono=True)``.
    """
    view = QPlainTextEdit(parent)
    view.setPlaceholderText(placeholder)
    view.setReadOnly(True)
    # Inter, not mono: the raw metadata view is the only opt-in mono field.
    # Registering keeps this sheet in step with a live theme switch.
    set_sheet(view, "input", "QPlainTextEdit", font_size, None)
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

    def _apply() -> None:
        lst.setStyleSheet(flush_list_style(last=last) if flush else framed_list_style())

    _apply()
    _register(lst, "list", last, flush)
    return lst


def make_checkbox(
    text: str,
    *,
    checked: bool = False,
    parent: QWidget | None = None,
) -> "AppCheckBox":
    """Build the standard check box (a response checklist item)."""
    box = AppCheckBox(text, parent)
    box.setChecked(checked)
    return box


# Check box indicator: 16px square, RADIUS_SM corners, a 12px Lucide check.
_CHECK_INDICATOR_PX = 16
_CHECK_GLYPH_PX = 12
_CHECK_GLYPHS: dict[tuple[str, int], QIcon] = {}


def _check_glyph(color: str, pixel_size: int) -> QIcon | None:
    """Return the cached check icon at ``pixel_size`` pixels, in ``color``.

    The glyph is an asset (``ui/icons.py``), never a stylesheet image or a
    character: the SVG lives in the packaged asset directory, which a QSS
    ``url(...)`` cannot reach reliably in the frozen build.
    """
    key = (color, int(pixel_size))
    hit = _CHECK_GLYPHS.get(key)
    if hit is not None:
        return hit
    try:
        from ui.icons import icon as _icon

        glyph = _icon("check", color=color, size=max(1, int(pixel_size)))
    except Exception:  # no asset, no SVG renderer: paint the face only
        return None
    if glyph.isNull():
        return None
    _CHECK_GLYPHS[key] = glyph
    return glyph


class AppCheckBox(QCheckBox):
    """A check box whose indicator is a rounded square carrying a check.

    Qt's indicator at 16px with a half-height radius reads as a chosen radio
    button, and the kit's QSS face had no check mark at all (dv-7mf). QSS
    cannot draw the glyph, so the base style keeps the label, the hit target
    and the focus cue, and this class paints the indicator itself: the three
    faces a curator can see are unchecked, checked and disabled.
    """

    INDICATOR_PX = _CHECK_INDICATOR_PX

    @staticmethod
    def face_colours(
        *, enabled: bool, checked: bool, hovered: bool = False
    ) -> tuple[str, str, str]:
        """Return the indicator's face, edge and glyph colours for one state.

        One place decides the three faces, so the painted indicator and the
        contrast tests read the same tokens: the edge is always a control
        boundary (3:1 on a card) except when the face is already the accent.
        Resolved from the active role table so the painted indicator follows
        a live theme switch (dv-314).
        """
        theme = _active_theme()
        if not enabled:
            # Muted, never the accent: a disabled check is not a decision.
            return (
                role("SURFACE_SUBTLE", theme),
                role("BORDER_SUBTLE", theme),
                role("TEXT_DISABLED", theme),
            )
        if checked:
            return (
                role("ACCENT_PRIMARY", theme),
                role("ACCENT_PRIMARY", theme),
                role("TEXT_ON_ACCENT", theme),
            )
        if hovered:
            return (
                role("SURFACE_CARD", theme),
                role("ACCENT_PRIMARY", theme),
                role("TEXT_ON_ACCENT", theme),
            )
        return (
            role("SURFACE_CARD", theme),
            role("BORDER_CONTROL", theme),
            role("TEXT_ON_ACCENT", theme),
        )

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._apply_sheet()
        _register(self, "checkbox")

    def _apply_sheet(self) -> None:
        """Paint the checkbox face from the active role table."""
        theme = _active_theme()
        self.setStyleSheet(
            f"QCheckBox {{ color: {role('TEXT_PRIMARY', theme)}; font-size: {FONT_BODY}px; "
            f"spacing: 8px; }} "
            # The indicator is painted below, so the sheet only reserves its
            # box: the text starts 8px after it, in every state.
            f"QCheckBox::indicator {{ width: {_CHECK_INDICATOR_PX}px; "
            f"height: {_CHECK_INDICATOR_PX}px; background: transparent; "
            f"border: none; }} "
            f"QCheckBox:disabled {{ color: {role('TEXT_DISABLED', theme)}; }} "
            # A widget sheet can shadow the app-wide focus rule, so carry it.
            f'QCheckBox[focusVisible="true"] {{ outline: 2px solid '
            f"{role('ACCENT_FOCUS_RING', theme)}; outline-offset: 2px; }}"
        )

    def indicatorRect(self) -> QRect:
        """Return the indicator's rectangle in widget coordinates.

        Plain geometry, not the style's: the widget sheet reserves exactly
        ``INDICATOR_PX`` (plus the 8px spacing), so the painted box is the
        same whether or not the style has been polished yet.
        """
        size = self.INDICATOR_PX
        area = self.contentsRect()
        height = area.height() or self.sizeHint().height()
        top = area.top() + max(0, (height - size) // 2)
        return QRect(area.left(), top, size, size)

    def enterEvent(self, event: QEnterEvent) -> None:
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event: QEvent) -> None:
        super().leaveEvent(event)
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        # Base style first: the label, the elided text and the focus cue.
        super().paintEvent(event)
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            self._paint_indicator(painter)
        finally:
            painter.end()

    def _paint_indicator(self, painter: QPainter) -> None:
        rect = self.indicatorRect()
        if rect.isEmpty():
            return
        checked = self.isChecked()
        face, edge, glyph_color = self.face_colours(
            enabled=self.isEnabled(), checked=checked, hovered=self.underMouse()
        )
        radius = float(RADIUS_SM.rstrip("px").strip())
        face_rect = QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(QColor(edge), 1.0))
        painter.setBrush(QColor(face))
        painter.drawRoundedRect(face_rect, radius, radius)
        if not checked:
            return
        try:
            ratio = float(self.devicePixelRatioF()) or 1.0
        except Exception:
            ratio = 1.0
        glyph = _check_glyph(glyph_color, round(_CHECK_GLYPH_PX * ratio))
        if glyph is None:
            return
        inset = max(0, (rect.width() - _CHECK_GLYPH_PX) // 2)
        glyph.paint(painter, rect.adjusted(inset, inset, -inset, -inset))


def make_progress_bar(
    *,
    height: int = 6,
    parent: QWidget | None = None,
) -> QProgressBar:
    """Build the standard progress bar (a thin fill, no text)."""
    bar = QProgressBar(parent)
    bar.setTextVisible(False)
    bar.setFixedHeight(height)

    def _apply() -> None:
        theme = _active_theme()
        bar.setStyleSheet(
            f"QProgressBar {{ background: {role('SURFACE_SUBTLE', theme)}; "
            f"border: 1px solid {role('BORDER_SUBTLE', theme)}; border-radius: {RADIUS_LG}; }} "
            f"QProgressBar::chunk {{ background: {role('ACCENT_PRIMARY', theme)}; "
            f"border-radius: {RADIUS_LG}; }}"
        )

    _apply()
    _register(bar, "progress_bar")
    return bar


def set_badge_label(
    badge: QLabel,
    text: str,
    *,
    label: str = "",
    background: str | None = None,
    foreground: str | None = None,
    border: str | None = None,
    font_size: int = FONT_SMALL,
    padding: str = "0 6px",
    chip: bool = True,
) -> QLabel:
    """Re-dress a live badge: new text, new face, same kit rule.

    A badge whose words change (a status pill that flips from
    "Loading" to "In Review") has to change its colours with them. The
    kit owns that, so a view never reaches into the theme for the
    badge's colours - and the badge cannot end up wearing a different
    face from the one the kit built.

    ``chip=True`` (the default) is the header/status-pill contract: the
    badge takes the standard button height and a tighter shadow. Pass
    ``chip=False`` for a small in-row badge (a check verdict) that sets
    its own metrics.
    """
    badge.setText(text)
    # Role names (or literals) are stored, so a live switch repaints the
    # badge with the same label (dv-314). Mono is always off: the kit no
    # longer offers a mono badge (the identifier sample was the last user).
    set_sheet(
        badge,
        "badge",
        label or text,
        background,
        foreground,
        border,
        False,
        font_size,
        padding,
    )
    if chip:
        # A chip is the header's counterpart to a button: it takes the
        # standard button height (centring its text inside) and must not be
        # stretched to whatever the tallest control in its row is.
        if badge.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Expanding:
            badge.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        badge.setMinimumHeight(CHIP_HEIGHT)
        badge.setMaximumHeight(CHIP_HEIGHT)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        apply_elevation(
            badge,
            blur=CHIP_SHADOW_BLUR,
            dy=CHIP_SHADOW_DY,
            alpha=CHIP_SHADOW_ALPHA,
        )
    return badge


def make_badge(
    text: str,
    *,
    label: str = "",
    background: str | None = None,
    foreground: str | None = None,
    border: str | None = None,
    font_size: int = FONT_SMALL,
    padding: str = "0 6px",
    chip: bool = True,
    parent: QWidget | None = None,
) -> QLabel:
    """Build a status badge wearing the role colours of its label.

    The label drives the colour (a curation label picks a role), so two
    badges of the same family never drift apart. A caller that already
    knows its role (a check result: PASS / FAIL / SKIP) may pass the
    three role colours explicitly.

    ``chip=True`` (the default) gives the header pill: standard button
    height plus a tight elevation shadow. A small in-row badge (a check
    verdict) passes ``chip=False`` and sets its own metrics.
    """
    return set_badge_label(
        QLabel("", parent),
        text,
        label=label,
        background=background,
        foreground=foreground,
        border=border,
        font_size=font_size,
        padding=padding,
        chip=chip,
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

    # A dataset title is only cut once the nav bar is genuinely out of
    # room (dv-gfx.19). The flag is set by the owner, which measures the
    # chips together against the space the row actually has; until then the
    # full title is both asked for and shown.
    _room_limited = False

    @property
    def room_limited(self) -> bool:
        return self._room_limited

    @room_limited.setter
    def room_limited(self, value: bool) -> None:
        if bool(value) == self._room_limited:
            return
        self._room_limited = bool(value)
        self._apply_elide()
        self.updateGeometry()

    def sizeHint(self) -> QSize:
        """Ask for the room the FULL title needs.

        QPushButton's own hint follows the *current* text, and
        ``_apply_elide`` replaces that text with the elided string — so
        the hint shrank after every elide and the chip ratcheted down to
        "Selecti…" even with the nav bar nearly empty (dv-dvu). Measuring
        the full text keeps the request stable: the owner can then compare
        the chips' combined request with the row width and only allow
        eliding when the bar is genuinely full (dv-gfx.19).
        """
        hint = super().sizeHint()
        metrics = self.fontMetrics()
        full = metrics.horizontalAdvance(self._full_text)
        shown = metrics.horizontalAdvance(self._shown_text)
        return QSize(hint.width() + max(0, full - shown), hint.height())

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._apply_elide()

    def _apply_elide(self) -> None:
        if not self.room_limited:
            # Room to spare: show the title in full (dv-gfx.19).
            shown = self._full_text
        else:
            width = max(0, self.width() - self._TEXT_INSET)
            shown = self.fontMetrics().elidedText(
                self._full_text, Qt.TextElideMode.ElideRight, width
            )
        if shown != self._shown_text:
            self._shown_text = shown
            self.setText(shown)
            self.updateGeometry()


def make_split_chip(
    label: str,
    *,
    active: bool = False,
    tip: str = "",
    close_tip: str = "",
    on_open: Callable[[], Any] | None = None,
    on_close: Callable[[], Any] | None = None,
    parent: QWidget | None = None,
) -> QFrame:
    """Build the dataset chip: a label half joined to a close half.

    The chip is two halves of one control - the label opens the dataset,
    the x closes it - so they share a border, a radius and a height.
    """
    chip = QFrame(parent)
    chip.setObjectName("DatasetChip")
    chip.setStyleSheet(transparent_surface_qss("DatasetChip", theme=_active_theme()))
    lay = QHBoxLayout(chip)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)

    open_btn = _ElidedChipButton(label)
    open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    open_btn.setToolTip(tip or label)
    open_btn.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
    open_btn.setFixedHeight(32)
    # No max width: the label asks for its full title (sizeHint) and only
    # elides when the chip row runs out of width (dv-dvu). The old 240px
    # cap cut ordinary titles even in an empty nav bar.
    open_btn.setMinimumWidth(72)
    set_sheet(open_btn, "split_chip", active, "left")
    if on_open is not None:
        open_btn.clicked.connect(on_open)
    lay.addWidget(open_btn)

    close_btn = QPushButton()
    close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    close_btn.setToolTip(close_tip or t("main.chip_close", label=label))
    close_btn.setAccessibleName(close_tip or t("main.chip_close", label=label))
    close_btn.setFixedSize(32, 32)
    try:
        set_icon(close_btn, "x", color="TEXT_PRIMARY" if active else "TEXT_ON_TINT")
        close_btn.setIconSize(QSize(12, 12))
    except Exception:
        # Fallback glyph only when the SVG cannot be drawn at all; it is
        # still centred by the right half's face (dv-ap7).
        close_btn.setText("×")
    set_sheet(close_btn, "split_chip", active, "right")
    if on_close is not None:
        close_btn.clicked.connect(on_close)
    lay.addWidget(close_btn)
    # The label half is how the owner decides whether the bar is full, and
    # how it switches eliding on; keep both on the chip.
    chip.label_half = open_btn  # type: ignore[attr-defined]
    apply_elevation(
        chip,
        blur=CHIP_SHADOW_BLUR,
        dy=CHIP_SHADOW_DY,
        alpha=CHIP_SHADOW_ALPHA,
    )
    return chip


def _split_chip_qss(active: bool, part: str) -> str:
    """Build the face of one half of the dataset chip.

    Colours come from the active role table, so a live switch repaints the
    chip (dv-314).
    """
    theme = _active_theme()
    if active:
        bg, fg, border = (
            role("SURFACE_TINT", theme),
            role("TEXT_PRIMARY", theme),
            role("ACCENT_PRIMARY", theme),
        )
    else:
        bg, fg, border = (
            role("SURFACE_CARD", theme),
            role("TEXT_PRIMARY", theme),
            role("BORDER_SUBTLE", theme),
        )
    if part == "left":
        edges = "border-top-left-radius: 8px; border-bottom-left-radius: 8px;"
        padding = "padding: 0 12px;"
        align = "left"
    else:
        edges = "border-left: none; border-top-right-radius: 8px; border-bottom-right-radius: 8px;"
        fg = role("TEXT_PRIMARY", theme) if active else role("TEXT_ON_TINT", theme)
        padding = "padding: 0;"
        # The x icon must sit dead-centre in the 32px square (dv-ap7):
        # left alignment (right for the title half) pushed it to the edge.
        align = "center"
    danger = role("TEXT_DANGER", theme)
    hover = (
        f"QPushButton:hover {{ color: {danger}; border-color: {danger}; }}"
        if part == "right"
        else f"QPushButton:hover {{ border-color: {role('ACCENT_PRIMARY', theme)}; }}"
    )
    return (
        f"QPushButton {{ background: {bg}; color: {fg}; text-align: {align}; "
        f"border: 1px solid {border}; {edges} {padding} "
        f"font-size: {FONT_SMALL}px; font-weight: 700; }}" + hover
    )


def set_chip_room_limited(chip: QWidget, limited: bool) -> None:
    """Let a dataset chip's title elide (or not) — the nav bar's call (dv-gfx.19).

    A chip is only allowed to cut its title once the chips together need
    more room than the row has. Until then the full title is shown, so a
    short title in an empty bar is never truncated.
    """
    label = getattr(chip, "label_half", None)
    if isinstance(label, _ElidedChipButton):
        label.room_limited = bool(limited)
        label._apply_elide()


def make_page_heading(title: str, subtitle: str = "") -> tuple[QLabel, QLabel | None]:
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
    """Small caption text (``CaptionSM`` token: 13px, muted).

    Prose beside a row or under a card: status strips, hints, footers.
    """
    lbl = QLabel(text)
    lbl.setObjectName("CaptionSM")
    lbl.setWordWrap(wrap)
    return lbl


def make_text_label(
    text: str = "",
    *,
    color: str = "",
    object_name: str = "BodySM",
    tip: str = "",
    wrap: bool = False,
    selectable: bool = False,
) -> QLabel:
    """Plain text label wearing a body token, optionally recoloured.

    For keys and legends where colour is the only decoration (dv-wp1):
    the kit owns the face, so a view never writes its own stylesheet.
    """
    lbl = QLabel(text)
    lbl.setObjectName(object_name)
    lbl.setWordWrap(wrap)
    if selectable:
        lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    if color:
        set_sheet(lbl, "text_label", color, object_name)
    if tip:
        lbl.setToolTip(tip)
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
    """Small body text (``BodySM`` token: 13px, muted)."""
    lbl = QLabel(text)
    lbl.setObjectName("BodySM")
    lbl.setWordWrap(wrap)
    return lbl


def make_card_title(text: str = "") -> QLabel:
    """Card title (``CardTitle`` token: 16px, semibold)."""
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
        mode: "Qt.TextElideMode" = Qt.TextElideMode.ElideRight,
        object_name: str = "",
    ) -> None:
        super().__init__(parent)
        self._full_text = ""
        self._shown = ""
        self._mode = mode
        # Ignored: the widget may be squeezed; the layout must not reserve
        # the width of the full string.
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
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

    def setText(self, text: str) -> None:
        self._full_text = text or ""
        self.setToolTip(self._full_text)
        self._apply_elide()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._apply_elide()

    def _apply_elide(self) -> None:
        shown = self.fontMetrics().elidedText(self._full_text, self._mode, max(0, self.width()))
        if shown == self._shown:
            return
        self._shown = shown
        super().setText(shown)


def make_elided_label(
    text: str = "",
    *,
    mode: "Qt.TextElideMode" = Qt.TextElideMode.ElideRight,
    object_name: str = "",
    parent: QWidget | None = None,
) -> ElidedLabel:
    """Build a label that elides its tail rather than widening its container.

    ``object_name`` names the theme token the label wears (for example
    ``"HeadlineMD"``), so an eliding label looks exactly like the static
    one it replaces.
    """
    return ElidedLabel(text, parent, mode=mode, object_name=object_name)


def make_icon_button(
    icon_name: str,
    tip: str = "",
    *,
    accessible_name: str = "",
    kind: str = "ghost",
    size: str = "sm",
    fallback_text: str = "",
    parent: QWidget | None = None,
) -> AppButton:
    """Build the kit's icon-only button: one face for every glyph affordance.

    A small AppButton (32px by default) carrying a Lucide icon, an optional
    accessible name and a tooltip, with a text fallback only for an
    environment where the SVG cannot be drawn at all. The column-reset
    button, the number-field stepper and the value-list add button all go
    through here, so they cannot drift apart.
    """
    btn = AppButton("", kind=kind, size=size, parent=parent)
    btn.setFixedSize(BUTTON_HEIGHTS.get(size, 32), BUTTON_HEIGHTS.get(size, 32))
    if accessible_name:
        btn.setAccessibleName(accessible_name)
    try:
        set_icon(btn, icon_name)
    except Exception:
        if fallback_text:
            btn.setText(fallback_text)
    if tip:
        btn.setToolTip(tip)
    return btn


def make_icon_text_button(
    label: str,
    icon_name: str,
    *,
    color: str | None = None,
    kind: str = "secondary",
    size: str = "md",
    tip: str = "",
    parent: QWidget | None = None,
) -> AppButton:
    """Build a labelled button that leads with its Lucide glyph.

    A refresh button, a Reinstall button and any other action that reads
    better with its mark carries the same shape: the icon first, the words
    after, one glyph per role from ``ui.icons.ICON_ROLES`` (dv-kvb). The
    label is still the button's text, so the accessible name and the
    keyboard focus are unchanged.
    """
    btn = AppButton(label, kind=kind, size=size, parent=parent)
    try:
        set_icon(btn, icon_name, color=color, size=14)
        btn.setIconSize(QSize(14, 14))
    except Exception:
        pass
    if tip:
        btn.setToolTip(tip)
    return btn


def make_refresh_button(
    label: str,
    *,
    kind: str = "secondary",
    size: str = "md",
    tip: str = "",
    parent: QWidget | None = None,
) -> AppButton:
    """Build the app's one refresh button: rotate-ccw plus its label (dv-kvb).

    Every refresh in the app (the queue, the Log page) is this button, so
    the glyph and the wording cannot drift apart. Extensions' Reinstall
    uses ``make_icon_text_button`` directly: same shape, a different role.
    """
    from ui.icons import ICON_ROLES

    return make_icon_text_button(
        label,
        ICON_ROLES["refresh"],
        kind=kind,
        size=size,
        tip=tip,
        parent=parent,
    )


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
    return make_icon_button(
        "rotate-ccw",
        tip or t("common.reset_columns_tip"),
        accessible_name=accessible_name or f"Reset {name} columns",
        fallback_text=fallback_text,
        parent=parent,
    )


def make_card(
    title: str, parent: QWidget | None = None
) -> tuple[QFrame, QVBoxLayout, QLabel, QHBoxLayout]:
    """Build a standard white card (8px unified radius) with a header bar.

    Returns (card, body_layout, title_label, header_layout) — append extra
    header widgets (summaries, combos, filters) to header_layout.
    """
    card = QFrame(parent)
    card.setObjectName("Card")
    outer = QVBoxLayout(card)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)
    top = QFrame()
    # Scoped (#id): a bare `QFrame {...}` rule would restyle every QFrame
    # below this bar — inline scope beats app-level rules subtree-wide.
    top.setObjectName("CardTopBar")

    def _apply() -> None:
        theme = _active_theme()
        card.setStyleSheet(
            f"QFrame#Card {{ background: {role('SURFACE_CARD', theme)}; "
            f"border: 1px solid {role('BORDER_SUBTLE', theme)}; border-radius: 8px; }}"
        )
        top.setStyleSheet(
            f"QFrame#CardTopBar {{ background: {role('SURFACE_PAGE', theme)}; "
            f"border-bottom: 1px solid {role('SURFACE_SUBTLE', theme)}; "
            "border-top-left-radius: 8px; border-top-right-radius: 8px; }"
        )

    _apply()
    # One registration covers both faces: they are one card. The top bar is
    # found through the card, so the spec stays plain data.
    _register(card, "card")
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
    wrap.setStyleSheet(transparent_surface_qss("CardBodyWrap", theme=_active_theme()))
    outer.addWidget(wrap)
    apply_elevation(card)
    return card, body, title_lbl, top_lay


def _wrap_tip(*paragraphs: str, width: int = 76) -> str:
    """Join tooltip paragraphs with blank lines, wrapped for readability."""
    chunks = []
    for paragraph in paragraphs:
        text = " ".join(str(paragraph).split())
        if text:
            chunks.append(textwrap.fill(text, width=width))
    return "\n\n".join(chunks)


def add_info_tip(
    header_layout: QHBoxLayout, *paragraphs: str, name: str = "", group: str = ""
) -> QToolButton:
    """Add a small Lucide (i) button right after a card title.

    The explanation lives in the tooltip, so section headers read as
    "Auto-Checks (i)" instead of carrying a permanent help paragraph.
    Clicking shows the same text, for touch and pen input. The tip is
    also registered into ui.help_index for the searchable Help page
    (dv-o8k); ``group=`` places it under a curator task.
    """
    from ui.help_index import register_help

    tip = _wrap_tip(*paragraphs)
    try:
        register_help(group, name, tip)
    except Exception:
        pass
    btn = QToolButton()
    btn.setObjectName("InfoTip")
    try:
        set_icon(btn, "info", color="TEXT_ON_TINT", size=14)
    except Exception:
        btn.setText("i")
    btn.setIconSize(QSize(14, 14))
    # 32px: the help dot is a target like any other, and 24px was below
    # the app's own hit-target floor.
    btn.setFixedSize(32, 32)
    btn.setAutoRaise(True)
    btn.setCursor(Qt.CursorShape.WhatsThisCursor)
    btn.setToolTip(tip)
    btn.setAccessibleName(t("common.about_named", name=name) if name else t("common.section_help"))
    btn.setAccessibleDescription(tip)
    btn.setStyleSheet(
        "QToolButton#InfoTip { background: transparent; border: none; "
        "border-radius: 16px; padding: 0; }"
        f"QToolButton#InfoTip:hover {{ background: {SURFACE_TINT}; }}"
    )
    _register(btn, "info_tip")
    btn.clicked.connect(
        lambda: QToolTip.showText(btn.mapToGlobal(btn.rect().bottomLeft()), tip, btn)
    )
    # Insert right after the title. A header with nothing in it yet (a test,
    # or a card built empty) has no index 1 to insert at, and Qt warns about
    # it, so clamp to the end.
    header_layout.insertWidget(min(1, header_layout.count()), btn)
    return btn


def make_search_field(
    placeholder: str, parent: QWidget | None = None, *, height: int = 36, min_width: int = 220
) -> QLineEdit:
    """Build a standard search box (SearchField style: rounded, 13px text)."""
    field = QLineEdit(parent)
    field.setObjectName("SearchField")
    field.setPlaceholderText(placeholder)
    field.setFixedHeight(height)
    field.setMinimumWidth(min_width)
    field.setClearButtonEnabled(True)
    # The field's own sheet replaces the app-level input rules, so it
    # repeats them: the control edge (3:1, not the decorative card
    # edge) and the placeholder colour (4.5:1). Registered so a live
    # switch repaints it (dv-314).
    set_sheet(field, "search_field")
    return field


def make_line_edit(
    placeholder: str = "",
    parent: QWidget | None = None,
    *,
    height: int = 36,
    password: bool = False,
) -> QLineEdit:
    """Build a standard form field: same height/focus ring as make_search_field."""
    field = QLineEdit(parent)
    field.setObjectName("SearchField")
    field.setPlaceholderText(placeholder)
    field.setFixedHeight(height)
    if password:
        field.setEchoMode(QLineEdit.EchoMode.Password)
    set_sheet(field, "search_field")
    return field


class _ComboPopupRowDelegate(QStyledItemDelegate):
    """Paint combo-box popup rows at the app's menu row metrics (dv-tkz).

    The app sheet declares ``QAbstractItemView::item`` with min-height
    22px and 6px vertical padding (~34px rows), but the popup measures
    items through the delegate, not the stylesheet — rows painted at
    ~20px and clipped descenders. Sizing from the font keeps the row at
    the declared contract at any display scaling.
    """

    _ROW_HEIGHT = 34  # 22px min-height + 2 x 6px padding

    def sizeHint(
        self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex
    ) -> QSize:
        hint = super().sizeHint(option, index)
        try:
            font_h = option.fontMetrics.height()
        except Exception:
            font_h = 12
        return QSize(hint.width(), max(self._ROW_HEIGHT, font_h + 12))


class _NoWheelCombo(QComboBox):
    """QComboBox that ignores the mouse-wheel until it has been clicked.

    Stops scroll-over accidents: wheeling over a dropdown you never
    opened (e.g. the Required/Optional level combos while scrolling the
    page) would otherwise flip the value. First click arms the wheel
    (and opens the popup); focus-out disarms it again.

    The popup also keeps a small vertical gap below the field (2026-11-24):
    a flush popup made the field's bottom corners look square while open.
    """

    # Gap between the field's bottom edge and the popup's top edge.
    _POPUP_GAP = 4

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._wheel_armed = False

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._wheel_armed = True
        try:
            super().mousePressEvent(event)
        except Exception:
            pass

    def focusOutEvent(self, event: QFocusEvent) -> None:
        self._wheel_armed = False
        try:
            super().focusOutEvent(event)
        except Exception:
            pass

    def wheelEvent(self, event: QWheelEvent) -> None:
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

    def showPopup(self) -> None:
        """Show the popup with a small gap under the field.

        Qt places the popup flush against the field by default, which made
        the field's rounded bottom corners read as square while open. The
        gap keeps both shapes rounded and visually separates the menu from
        the control that opened it.
        """
        try:
            super().showPopup()
            popup = self.view()
            if popup is not None:
                popup.move(popup.x(), popup.y() + self._POPUP_GAP)
        except Exception:
            pass


def make_combo(
    items: Iterable[Any] | None = None,
    parent: QWidget | None = None,
    *,
    height: int = 36,
    min_width: int = 130,
    tip: str = "",
) -> QComboBox:
    """Build a standard dropdown (themed chevron, 12px semibold entries).

    items: list of labels or (label, data) tuples. Wheel-safe: the wheel
    only scrolls the value after the dropdown has been clicked open once.
    """
    combo = _NoWheelCombo(parent)
    combo.setFixedHeight(height)
    combo.setMinimumWidth(min_width)
    combo.setCursor(Qt.CursorShape.PointingHandCursor)
    # Popup rows honor the app's menu row metrics (dv-tkz).
    combo.view().setItemDelegate(_ComboPopupRowDelegate(combo))
    if tip:
        combo.setToolTip(tip)
    for entry in items or []:
        if isinstance(entry, (tuple, list)):
            combo.addItem(str(entry[0]), entry[1] if len(entry) > 1 else None)
        else:
            combo.addItem(str(entry))
    return combo


# The transparent host that centres one control in a table/tree cell.
_CELL_HOST_NAME = "CellControlHost"


def make_cell_control(
    widget: QWidget,
    *,
    v_margin: int = 4,
    h_margin: int = 8,
    parent: QWidget | None = None,
) -> QWidget:
    """Host ``widget`` in a cell, centred with equal space above and below.

    Qt gives a cell widget the cell's top-left corner and its full height, so
    a 32px control in a 40px row lands flush against the top edge unless
    something inside the cell does the centring (dv-7zv: the review rules
    dropdowns sat 4px high against their own labels). One helper does it, so
    the review table's two dropdown columns cannot drift apart.

    The host paints nothing (a scoped transparent rule, not a bare
    ``background: transparent`` that would also reach the control inside it),
    and its height is the control's plus both margins - exactly the row
    height the kit uses, so nothing is stretched or clipped.
    """
    host = QWidget(parent)
    host.setObjectName(_CELL_HOST_NAME)
    host.setStyleSheet(transparent_surface_qss(_CELL_HOST_NAME, theme=_active_theme()))
    lay = QHBoxLayout(host)
    lay.setContentsMargins(h_margin, v_margin, h_margin, v_margin)
    lay.setSpacing(0)
    # AlignVCenter is explicit, not a consequence of the margins: a child
    # with a fixed height would otherwise be placed wherever Qt's box layout
    # puts a short item, and the "4px above and below" promise would be a
    # coincidence of the current sizeHint.
    lay.addWidget(widget, 1, Qt.AlignmentFlag.AlignVCenter)
    return host


class AppNumberField(QWidget):
    """A bounded number field: a QSpinBox between two Lucide stepper buttons.

    The platform's native stepper is switched off
    (``ButtonSymbols.NoButtons``: typing is allowed and clamped on focus-out
    and Enter) and the stepping is the kit's own 32px ghost icon buttons,
    disabled at the bounds, so the control wears the kit's button face
    instead of a clipped native arrow. ``value()``/``setValue()``/
    ``setRange()`` mirror the QSpinBox API the field replaces, and
    ``changed`` fires only on user action - never on a programmatic
    ``setValue`` (the params loader sets values by hand and relies on that).
    """

    changed = Signal(int)

    def __init__(
        self,
        value: int = 0,
        *,
        minimum: int = 0,
        maximum: int = 10000,
        step: int = 1,
        tip: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._spin = QSpinBox(self)
        self._spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._spin.setRange(minimum, maximum)
        self._spin.setSingleStep(step)
        self._spin.setValue(value)
        self._spin.setFixedHeight(32)
        self._down = make_icon_button(
            "minus",
            tip=t("common.decrease_tip"),
            accessible_name=t("common.decrease_a11y"),
            fallback_text="-",
        )
        self._up = make_icon_button(
            "plus",
            tip=t("common.increase_tip"),
            accessible_name=t("common.increase_a11y"),
            fallback_text="+",
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(self._down)
        lay.addWidget(self._spin, 1)
        lay.addWidget(self._up)
        if tip:
            self.setToolTip(tip)
            self._spin.setToolTip(tip)
        self._spin.valueChanged.connect(self._on_value)
        self._down.clicked.connect(lambda: self._spin.stepBy(-1))
        self._up.clicked.connect(lambda: self._spin.stepBy(1))
        self._refresh()

    def value(self) -> int:
        return self._spin.value()

    def setValue(self, value: int) -> None:
        """Set the value without emitting ``changed`` (a loader, not a user)."""
        self._spin.blockSignals(True)
        try:
            self._spin.setValue(int(value))
        finally:
            self._spin.blockSignals(False)
        self._refresh()

    def setRange(self, minimum: int, maximum: int) -> None:
        self._spin.setRange(minimum, maximum)
        self._refresh()

    def _on_value(self, v: int) -> None:
        self._refresh()
        self.changed.emit(v)

    def _refresh(self) -> None:
        v = self._spin.value()
        self._down.setEnabled(v > self._spin.minimum())
        self._up.setEnabled(v < self._spin.maximum())


def make_number_field(
    value: int = 0,
    *,
    minimum: int = 0,
    maximum: int = 10000,
    step: int = 1,
    tip: str = "",
    parent: QWidget | None = None,
) -> AppNumberField:
    """Build the standard bounded number field (Lucide minus/plus stepper)."""
    return AppNumberField(
        value, minimum=minimum, maximum=maximum, step=step, tip=tip, parent=parent
    )


class _ValueChip(QFrame):
    """One phrase as a chip: its text plus a Lucide x that deletes it."""

    def __init__(
        self, text: str, *, on_remove: Callable[[], Any], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.value = str(text)
        self.setObjectName("ValueChip")
        self._apply_sheet()
        _register(self, "value_chip")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        label = QLabel(self.value)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        btn = make_icon_button(
            "x",
            tip=t("common.remove_tip"),
            accessible_name=t("common.remove_a11y", value=self.value),
            fallback_text="×",
        )
        btn.clicked.connect(on_remove)
        lay.addWidget(label)
        lay.addWidget(btn)

    def _apply_sheet(self) -> None:
        """Paint the chip face from the active role table."""
        theme = _active_theme()
        self.setStyleSheet(
            f"QFrame#ValueChip {{ background: {role('SURFACE_TINT', theme)}; "
            f"border: 1px solid {role('BORDER_SUBTLE', theme)}; border-radius: {RADIUS_SM}; "
            f"padding: 0 2px 0 8px; }}"
        )


class _ChipFlow(QWidget):
    """Chips laid out left-to-right, wrapping onto rows as the width allows."""

    _GAP = 6

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(self._GAP)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._chips: list[QWidget] = []
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

    def chips(self) -> list[QWidget]:
        return list(self._chips)

    def add_chip(self, chip: QWidget, index: int | None = None) -> None:
        self._chips.insert(len(self._chips) if index is None else index, chip)
        self._relayout()

    def remove_chip(self, chip: QWidget) -> None:
        if chip in self._chips:
            self._chips.remove(chip)
        chip.deleteLater()
        self._relayout()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._relayout()

    def _relayout(self) -> None:
        """Place every chip on a row, wrapping when the width runs out.

        The estimate walks the chips' own size hints with the same gap the
        grid paints, so a chip is never split across rows and none is ever
        pushed past the right edge.
        """
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.setParent(None)
        rows: list[list[QWidget]] = []
        current: list[QWidget] = []
        used = 0
        available = self.width()
        for chip in self._chips:
            need = chip.sizeHint().width()
            if current and available > 0 and used + self._GAP + need > available:
                rows.append(current)
                current = []
                used = 0
            current.append(chip)
            used += (self._GAP if used else 0) + need
        if current:
            rows.append(current)
        for row_index, row in enumerate(rows):
            for col_index, chip in enumerate(row):
                self._grid.addWidget(chip, row_index, col_index)
        for chip in self._chips:
            chip.show()


class AppValueList(QWidget):
    """A multi-value field: one chip per phrase, added one at a time.

    The field takes a single phrase (Enter in it, or the plus button, adds
    it), each entry renders as its own chip with a Lucide x that deletes
    just that entry, and the chips wrap onto rows when the control is
    narrow. Blanks and case-insensitive duplicates are ignored, so a list of
    values never gains a second copy of the same phrase; an optional
    empty-state caption names what the list is for.
    """

    changed = Signal(list)

    def __init__(
        self,
        values: Iterable[Any] = (),
        *,
        placeholder: str = "",
        add_tip: str = "",
        empty_text: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._values: list[str] = []
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)
        self._flow = _ChipFlow(self)
        outer.addWidget(self._flow)
        self._empty: QLabel | None = None
        if empty_text:
            self._empty = QLabel(empty_text)
            self._empty.setObjectName("CaptionSM")
            outer.addWidget(self._empty)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self._field = make_line_edit(placeholder, height=32)
        self._field.returnPressed.connect(self._add_current)
        self._add_btn = make_icon_button(
            "plus",
            tip=add_tip,
            accessible_name=t("common.add_a11y"),
            fallback_text="+",
        )
        self._add_btn.clicked.connect(self._add_current)
        row.addWidget(self._field, 1)
        row.addWidget(self._add_btn)
        outer.addLayout(row)
        self.setValues(list(values))

    def values(self) -> list[str]:
        return list(self._values)

    def setValues(self, values: Iterable[Any]) -> None:
        """Replace the whole list: one ``changed``, never one per item."""
        for chip in self._flow.chips():
            self._flow.remove_chip(chip)
        self._values = []
        for value in values:
            self._add(str(value))
        self._refresh()
        self.changed.emit(list(self._values))

    def _add_current(self) -> None:
        if self._add(self._field.text()):
            self._field.clear()
            self._refresh()
            self.changed.emit(list(self._values))

    def _add(self, raw: str) -> bool:
        value = str(raw or "").strip()
        if not value:
            return False
        if any(value.lower() == existing.lower() for existing in self._values):
            return False
        self._values.append(value)
        self._flow.add_chip(_ValueChip(value, on_remove=lambda: self._remove(value)))
        return True

    def _remove(self, value: str) -> None:
        self._values = [v for v in self._values if v != value]
        for chip in list(self._flow.chips()):
            if getattr(chip, "value", None) == value:
                self._flow.remove_chip(chip)
                break
        self._refresh()
        self.changed.emit(list(self._values))

    def _refresh(self) -> None:
        if self._empty is not None:
            self._empty.setVisible(not self._values)


def make_value_list(
    values: Iterable[Any] = (),
    *,
    placeholder: str = "",
    add_tip: str = "",
    empty_text: str = "",
    parent: QWidget | None = None,
) -> AppValueList:
    """Build the standard multi-value field (one chip per phrase)."""
    return AppValueList(
        values,
        placeholder=placeholder,
        add_tip=add_tip,
        empty_text=empty_text,
        parent=parent,
    )


# -- finding dispositions (dv-32x) ----------------------------------------
# Canonical tokens mirror storage.DISPOSITION_TOKENS; the tuple is
# duplicated (not imported) so the kit stays free of the storage layer,
# and a test asserts the two stay identical.

DISPOSITION_TOKENS = ("", "acknowledged", "fix-requested", "wontfix", "blocked")

_DISPOSITION_LABEL_KEYS = {
    "": "detail.disposition.unset",
    "acknowledged": "detail.disposition.acknowledged",
    "fix-requested": "detail.disposition.fix_requested",
    "wontfix": "detail.disposition.wontfix",
    "blocked": "detail.disposition.blocked",
}


def disposition_label(token: str) -> str:
    """Human label for a disposition token (the unset label when unknown)."""
    return t(_DISPOSITION_LABEL_KEYS.get(str(token or ""), "detail.disposition.unset"))


def make_disposition_combo(
    current: str = "",
    on_change: Callable[[Any], Any] | None = None,
    parent: QWidget | None = None,
) -> QComboBox:
    """Compact disposition dropdown for one finding row.

    current: the stored token ("" = none recorded). on_change(token) fires
    when the curator picks a different disposition. The initial index is
    set before the signal is connected, so building a row never fires.
    """
    combo = make_combo(
        [(disposition_label(token), token) for token in DISPOSITION_TOKENS],
        parent,
        # Standard 36px field, like every other combo in the app (dv-3d0.3):
        # the QSS pads the text box 7px top and bottom, so a shorter frame
        # clipped the descenders ("text cut off at the bottom").
        height=36,
        min_width=118,
        tip=t("detail.disposition.combo_tip"),
    )
    tokens = list(DISPOSITION_TOKENS)
    combo.setCurrentIndex(tokens.index(current if current in tokens else ""))
    if on_change is not None:
        combo.currentIndexChanged.connect(lambda _i: on_change(combo.currentData()))
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
        self._apply_sheet()
        _register(self, "pane_footer")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(8)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
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

    def _apply_sheet(self) -> None:
        """Paint the footer's top hairline from the active role table."""
        self.setStyleSheet(
            f"QFrame#PaneFooter {{ background: transparent; "
            f"border-top: 1px solid {role('BORDER_SUBTLE', _active_theme())}; }}"
        )

    def set_status(self, text: str) -> None:
        self.status.setText(text or "")

    def set_dirty(self, dirty: bool) -> None:
        self.dirty_chip.setVisible(bool(dirty))
        self.revert_btn.setEnabled(bool(dirty))


# Horizontal gap between two nav-mode rail links, matching the nav bar's
# dataset-item rhythm (2026-11-24).
_NAV_ITEM_SPACING = 8


class WorkflowRail(QWidget):
    """Compact six-step progress rail for a dataset.

    Guidance, not a gate: every step is clickable in every state, and the
    widget itself runs nothing (it only emits the clicked step's key). State
    comes from the pure :func:`ui.workflow.derive_workflow`; the current
    step also carries bold text and an accessible name so the meaning never
    depends on colour alone.
    """

    stepClicked = Signal(str)
    # The mechanical/practice toggle (dv-sce): the owner persists the
    # choice and re-derives the steps; the rail just re-renders.
    viewToggled = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        nav_steps: list[tuple[str, str]] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("WorkflowRail")
        self._nav_steps = nav_steps
        layout = QHBoxLayout(self)
        # Left margin aligns with the main column's content margin (16px card
        # inset + 8px = 24px from page edge). Buttons are fixed-width tabs.
        layout.setContentsMargins(24, 0, 24, 0)
        # The nav bar spaces its items; the rail matches that rhythm instead
        # of gluing the links together (2026-11-24).
        layout.setSpacing(_NAV_ITEM_SPACING if nav_steps else 0)
        self.buttons: dict[str, QPushButton] = {}
        self._indexes: dict[str, int] = {}
        self._active_key = ""
        # The state each step was last painted in, so a theme switch can
        # repaint the rail without re-deriving the workflow (dv-314).
        self._step_states: dict[str, str] = {}
        self.hint = QLabel("")
        self.hint.setObjectName("CaptionSM")
        self.hint.setWordWrap(False)
        self.hint.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.hint.setMinimumWidth(80)
        self._toggle = QPushButton("")
        self._toggle.setObjectName("WorkflowStep")
        self._toggle.setFlat(True)
        self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle.setMinimumWidth(0)
        self._toggle.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self._toggle.setToolTip(t("workflow.curated.toggle_tip"))
        self._toggle.setAccessibleName(t("workflow.curated.toggle_tip"))
        self._toggle.clicked.connect(lambda _c: self.viewToggled.emit())
        self._rebuild_steps([key for key, _label in nav_steps] if nav_steps else list(STEP_ORDER))
        _register(self, "workflow_rail")
        if nav_steps:
            # Fixed navigation mode (the dataset page's three section buttons):
            # no state badge, no hint and no curated toggle — just the buttons.
            self.hint.hide()
            self._toggle.hide()
            for key, label in nav_steps:
                btn = self.buttons.get(key)
                if btn is not None:
                    btn.setText(label)
                    btn.setToolTip(t("detail.rail.tip"))
                    btn.setAccessibleName(label)
                    btn.setStyleSheet(self._style_for("nav", active=False))
                    try:
                        glyph = {
                            "dataset_checks": "section_checks",
                            "file_checks": "folder",
                            "response": "section_response",
                        }.get(key)
                        if glyph:
                            set_icon(btn, glyph, size=14)
                            btn.setIconSize(QSize(14, 14))
                    except Exception:
                        pass
            # Reserve space for the result pills in the full workflow mode.
            # In nav mode this is a no-op; the hint is hidden.
            self.hint.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
            self.hint.setMinimumWidth(180)
            # Pack the links on the left with the nav bar's spacing instead
            # of letting them spread across the page (2026-11-24).
            layout.addStretch(1)
        else:
            layout.addWidget(self.hint)
            layout.addWidget(self._toggle)

    def minimumSizeHint(self) -> QSize:
        """Keep the window free to stay at the 960px floor.

        Qt's default minimum-size algorithm sums the buttons' size hints
        (the seven CURATE(D) steps overflow 960px), so it would drag the
        whole window wider on narrow screens. The rail has no intrinsic
        width floor of its own: steps compress without a lower bound, and
        the hint/toggle squeeze towards their own floors. Only the height
        floor matters.
        """
        hint = super().minimumSizeHint()
        return QSize(1, hint.height())

    def _rebuild_steps(self, keys: list[str]) -> None:
        """Rebuild the step buttons for a step set (mechanical or CURATE(D))."""
        if keys == list(self.buttons):
            return
        lay = self.layout()
        if lay is None:
            return
        for w in (self.hint, self._toggle):
            lay.removeWidget(w)
        while lay.count():
            item = lay.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self.buttons = {}
        self._indexes = {}
        for i, key in enumerate(keys):
            self._indexes[key] = i + 1
            btn = QPushButton("")
            btn.setObjectName("WorkflowStep")
            btn.setFlat(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setMinimumWidth(0)
            if self._nav_steps:
                # Nav mode: fixed-height tabs, no expanding (dv-3d0.2)
                btn.setFixedHeight(32)
                btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            else:
                # Workflow mode: buttons expand to fill available space
                btn.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
            btn.clicked.connect(lambda _c, k=key: self.stepClicked.emit(k))
            lay.addWidget(btn)
            self.buttons[key] = btn
            self._step_states[key] = "available"
            if i < len(keys) - 1 and self._nav_steps:
                # Hairline separator between nav tabs (dv-3d0.2)
                sep = QFrame()
                sep.setFrameShape(QFrame.Shape.VLine)
                sep.setFixedWidth(1)
                set_sheet(sep, "rule", "QFrame", "BORDER_SUBTLE")
                lay.addWidget(sep)
                # The nav bar spaces its items; the rail matches that rhythm
                # instead of spreading the links across the page (2026-11-24).
                gap = QSpacerItem(
                    _NAV_ITEM_SPACING, 0, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
                )
                lay.addItem(gap)
        # The buttons and hint should share space; we remove the hard stretch
        # to allow the MinimumExpanding buttons to actually expand.
        lay.addWidget(self.hint)
        lay.addWidget(self._toggle)

    def set_nav_counts(self, passed: int = 0, warnings: int = 0, errors: int = 0) -> None:
        """Show the mockup's compact result pills in the fixed rail's hint.

        In nav mode (dataset page section tabs) this is a no-op — the rail
        shows no counts (dv-3d0.2).
        """
        if not self._nav_steps:
            return
        # Nav mode: no counts shown on the rail

    def set_toggle_label(self, text: str) -> None:
        """Show the name of the view the toggle switches TO."""
        self._toggle.setText(text)

    @staticmethod
    def _style_for(state: str, *, active: bool = False) -> str:
        """Return the step's face for its state - the theme owns the rule."""
        if state == "nav":
            return workflow_step_qss("nav", active=active, theme=_active_theme())
        return workflow_step_qss(state, active=active, theme=_active_theme())

    def _retheme(self) -> None:
        """Repaint the rail and every step from the active role table (dv-314)."""
        self.setStyleSheet(workflow_rail_qss(theme=_active_theme()))
        for key, btn in self.buttons.items():
            state = self._step_states.get(key, "available")
            btn.setStyleSheet(self._style_for(state, active=key == self._active_key))

    def set_active_step(self, key: str) -> None:
        """Shade the step whose section is on screen (dv-gfx.4).

        The section rail replaces "which step of the workflow" with "which
        card am I looking at", so the current view is carried by a shaded
        block behind its button. In nav mode every state uses the same
        ``nav`` face (only ``active`` differs) so the clicked link keeps
        its size and position (2026-11-24).
        """
        key = str(key or "")
        if key == self._active_key:
            return
        self._active_key = key
        for step_key, btn in self.buttons.items():
            is_active = step_key == key
            state = "nav" if self._nav_steps else ("current" if is_active else "available")
            # Keep the state map in step so a live theme switch repaints the
            # same faces (dv-314); nav mode shades every step, active or not.
            self._step_states[step_key] = state
            btn.setStyleSheet(self._style_for(state, active=is_active))
        self.setStyleSheet(workflow_rail_qss(theme=_active_theme()))

    def set_workflow(self, workflow: Workflow) -> None:
        """Paint each step and the next-step hint; never disables a step.

        In fixed-navigation mode the rail is just the three section buttons:
        it ignores workflow derivation so its buttons stay stable.
        """
        if self._nav_steps:
            return
        self._rebuild_steps([step.key for step in workflow.steps])
        for step in workflow.steps:
            btn = self.buttons.get(step.key)
            if btn is None:
                continue
            number = step.badge or str(self._indexes.get(step.key, 0))
            done = step.state == "done"
            # Done steps lead with the app's Lucide check, not a text
            # glyph; the number stays for every other state.
            btn.setText(f"{'  ' if done else number + '  '}{step.label}")
            btn.setIconSize(QSize(14, 14))
            # A blocked step wears a lock: the state is carried by a mark
            # as well as by colour, so it survives a greyscale print and
            # a colour-blind reader.
            try:
                if done:
                    set_icon(btn, "check", color="TEXT_SUCCESS", size=14)
                elif step.state == "blocked":
                    set_icon(btn, "lock", color="TEXT_BLOCKED", size=12)
                else:
                    btn.setIcon(QIcon())
            except Exception:
                btn.setIcon(QIcon())
            btn.setStyleSheet(self._style_for(step.state))
            self._step_states[step.key] = step.state
            btn.setToolTip(step.hint)
            btn.setAccessibleName(step.accessible)
            btn.setAccessibleDescription(step.hint)
        self.hint.setText(workflow.hint)
        self.hint.setToolTip(workflow.hint)


class StatusWidget(QFrame):
    """One compact inline status chip: icon + words + bar (dv-3d0.4).

    Replaces the old three-row stack (message strip, progress bar, ring)
    with a single line that sits beside the dataset identity. Three faces:

    * ``set_running`` — spinner, title, "n/N" detail, determinate/indeterminate
      bar;
    * ``set_complete`` — check, "All checks complete", counts, full bar;
    * ``set_error`` — alert, short reason, full bar in the error role.

    The widget is hidden until there is something to report, so an idle
    header reserves no vertical space for it. Every glyph is a bundled
    Lucide icon; every colour comes from a theme role. The chip is wide
    enough for its text to stay on one line; there is no close/retry/cancel
    action button.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("StatusWidget")
        self.setVisible(False)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(12, 6, 12, 6)
        outer.setSpacing(0)
        self._icon = QLabel()
        self._icon.setFixedSize(18, 18)
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title = make_small_body_label("")
        self._detail = QLabel("")
        self._detail.setObjectName("CaptionSM")
        # Prevent eliding/wrapping: the chip must be wide enough for one line.
        self._detail.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._detail.setMinimumWidth(200)
        self._bar = make_progress_bar(height=4)
        self._bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        # Two rows: the words, then the bar directly under them (dv-gfx.3).
        # The bar never shares the text's line, so it reads as the status's
        # own progress rather than a stray rule between the labels.
        self._rows = QVBoxLayout()
        self._rows.setContentsMargins(0, 0, 0, 0)
        self._rows.setSpacing(2)
        line = QHBoxLayout()
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(8)
        line.addWidget(self._icon)
        line.addWidget(self._title)
        line.addWidget(self._detail, 1)
        # The verdict's action chips (required/recommended changes) share the
        # status line's right side when the run is over (2026-11-24).
        self._chips = QHBoxLayout()
        self._chips.setSpacing(6)
        line.addLayout(self._chips)
        # No action button (x/retry/cancel) — the chip is informational only.
        self._rows.addLayout(line)
        self._rows.addWidget(self._bar)
        self._bar.hide()
        outer.addLayout(self._rows, 1)
        self._apply_sheet()
        _register(self, "status_widget")

    def _apply_sheet(self) -> None:
        """Paint the chip face from the active role table."""
        theme = _active_theme()
        self.setStyleSheet(
            f"QFrame#StatusWidget {{ background: {role('SURFACE_SUBTLE', theme)}; "
            f"border: 1px solid {role('BORDER_SUBTLE', theme)}; border-radius: {RADIUS_LG}; }}"
        )

    def _paint_icon(self, name: str, color: str) -> None:
        from ui.icons import icon as _icon

        self._icon.setPixmap(_icon(name, color=color, size=16).pixmap(QSize(16, 16)))

    def _set_action(self, name: str, tip: str) -> None:
        """Deprecate (dv-3d0.4): no action button on the status chip."""
        pass

    def set_running(
        self,
        title: str,
        detail: str = "",
        fraction: float | None = None,
        *,
        cancelling: bool = False,
    ) -> None:
        """Spinner + the words; a bar only when the work is measurable.

        ``fraction=None`` is an informational line (a status message with
        no progress behind it), so it shows no bar - a bar that never
        moves reads as stalled work. A determinate fraction gets one.
        """
        self._paint_icon("loader-circle", ACCENT_PRIMARY)
        self._title.setText(title)
        self._detail.setText(detail)
        if fraction is None:
            self._bar.setRange(0, 1)
            self._bar.setValue(0)
            self._bar.hide()
        else:
            self._bar.setRange(0, 100)
            self._bar.setValue(int(max(0.0, min(1.0, fraction)) * 100))
            self._bar.show()
        self.show()

    def set_complete(self, title: str, detail: str = "") -> None:
        """Check + full success bar (no action button)."""
        self._paint_icon("circle-check", STATE_SUCCESS_GRAPHIC)
        self._title.setText(title)
        self._detail.setText(detail)
        self._bar.setRange(0, 100)
        self._bar.setValue(100)
        self._bar.show()
        self.show()

    def set_error(self, title: str, detail: str = "") -> None:
        """Alert + full error bar (no action button)."""
        self._paint_icon("circle-alert", STATE_ERROR_GRAPHIC)
        self._title.setText(title)
        self._detail.setText(detail)
        self._bar.setRange(0, 100)
        self._bar.setValue(100)
        self._bar.show()
        self.show()

    def clear(self) -> None:
        """Hide the strip and reset it for the next pass."""
        self.hide()
        self._title.setText("")
        self._detail.setText("")
        self._bar.hide()
        self.clear_chips()

    def set_chips(self, chips: list[QWidget]) -> None:
        """Show the given action chips on the status line (verdict actions)."""
        self.clear_chips()
        for chip in chips:
            self._chips.addWidget(chip)
        self.show()

    def clear_chips(self) -> None:
        """Drop the action chips from the status line."""
        while self._chips.count():
            item = self._chips.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def text(self) -> str:
        """Return the current status title text (for tests)."""
        return self._title.text()


def fit_tree_height(tree: QTreeView, row_height: int = 40, floor: int = 80) -> None:
    """Grow a tree to its visible rows so the page scrolls, not the tree.

    Content fit for flush trees on a scrolling canvas (file manifest,
    review-config checks tree): tallies the visible rows, expanded
    children included, and pins the tree to that height so it never
    needs its own scrollbar. A quiet no-op on any failure.
    """
    try:
        model = tree.model()
        if model is None:
            return
        visible_rows = 0
        stack = [tree.rootIndex()]
        while stack:
            parent = stack.pop()
            count = model.rowCount(parent)
            visible_rows += count
            for r in range(count):
                idx = model.index(r, 0, parent)
                if model.hasChildren(idx) and tree.isExpanded(idx):
                    stack.append(idx)
        header_h = tree.header().height() if tree.header() else 30
        tree.setFixedHeight(max(floor, header_h + visible_rows * row_height + 2))
    except Exception:
        pass
