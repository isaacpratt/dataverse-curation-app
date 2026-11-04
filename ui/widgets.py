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

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QToolButton,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from ui.theme import (
    BACKGROUND,
    ON_SECONDARY_CONTAINER,
    ON_SURFACE,
    ON_SURFACE_VARIANT,
    OUTLINE_VARIANT,
    PRIMARY,
    SURFACE_CONTAINER,
    SURFACE_CONTAINER_LOW,
    SURFACE_CONTAINER_LOWEST,
    enable_table_copy,
)

__all__ = [
    "AppButton",
    "AppTable",
    "flush_table_style",
    "flush_list_style",
    "make_card",
    "add_info_tip",
    "make_page_heading",
    "make_search_field",
    "make_line_edit",
    "make_combo",
    "BUTTON_HEIGHTS",
]

# Button heights (px) by size token.
BUTTON_HEIGHTS = {"sm": 28, "md": 36, "lg": 40}

_BUTTON_OBJECTS = {
    "primary": "PrimaryButton",
    "secondary": "SecondaryButton",
    "ghost": "GhostButton",
    "chip": "FilterChip",
    "nav-active": "NavActive",
    "nav": "NavItem",
}


class AppButton(QPushButton):
    """Standard button.

    kind: primary | secondary | ghost | chip | nav-active | nav.
    size: sm (28) | md (36) | lg (40) | None (natural height, e.g. nav bar).
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


class AppTable(QTableWidget):
    """Build a standard table (sortable columns, row selection, no grid).

    Hidden vertical header and Ctrl+C copy support. headers: ordered column
    titles. widths: {index: px} initial widths (default 120). row_height:
    vertical default section size. sortable: leave True unless the view
    depends on insertion order.

    Emits columns_fitted after a successful content fit so split-header
    views (dashboard queue) can mirror the new section sizes.
    """

    columns_fitted = Signal()

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
        self.setHorizontalHeaderLabels(list(headers))
        hdr = self.horizontalHeader()
        hdr.setStretchLastSection(stretch_last)
        hdr.setSectionsMovable(True)
        hdr.setSectionsClickable(True)
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

    def _on_user_section_resized(self, *_args) -> None:
        """Lock content auto-fit once the user drags a column edge."""
        if self._fitting:
            return
        self._auto_fit = False

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


def flush_table_style(last: bool = True) -> str:
    """Edge-to-edge QTableWidget face for tables flush inside cards/panes.

    Qt never clips children to a parent's border-radius, so a flush table
    paints its own corners: square top (meets the header/content above
    flush), 8px bottom when `last` (meets the card/pane border) else square
    (more flush content follows). Header end-caps stay square for the same
    reason — the global 8px section radius would notch unfilled.
    The background is explicit (not inherited from the app rule): without
    it, a styled lavender ancestor makes the whole table body transparent
    and rows render page-colored instead of white.
    """
    bottom = "8px" if last else "0px"
    return (
        "QTableWidget { background: " + SURFACE_CONTAINER_LOWEST + "; border: none; "
        "border-top-left-radius: 0px; border-top-right-radius: 0px; "
        "border-bottom-left-radius: " + bottom + "; "
        "border-bottom-right-radius: " + bottom + "; } "
        "QHeaderView::section:first { border-top-left-radius: 0px; } "
        "QHeaderView::section:last { border-top-right-radius: 0px; } "
        # Scrollbar lanes are transparent so the table's own painted surface
        # and its rounded bottom-right corner show through, keeping the card
        # border connected at the corner instead of ending in a white notch.
        # Thumbs/grooves keep coming from the global theme.
        "QTableWidget QScrollBar:vertical { background: transparent; } "
        "QTableWidget QScrollBar:horizontal { background: transparent; } "
    )


def flush_list_style(last: bool = True) -> str:
    """Edge-to-edge QListWidget face, same corner contract as flush tables."""
    bottom = "8px" if last else "0px"
    return (
        f"QListWidget {{ background: {SURFACE_CONTAINER_LOWEST}; border: none; "
        "border-top-left-radius: 0px; border-top-right-radius: 0px; "
        "border-bottom-left-radius: " + bottom + "; "
        "border-bottom-right-radius: " + bottom + "; "
        f"font-size: 12px; color: {ON_SURFACE_VARIANT}; }}"
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


def make_card(title: str, parent: QWidget | None = None) -> tuple:
    """Build a standard white card (8px unified radius) with a header bar.

    Returns (card, body_layout, title_label, header_layout) — append extra
    header widgets (summaries, combos, filters) to header_layout.
    """
    card = QFrame(parent)
    card.setObjectName("Card")
    card.setStyleSheet(
        f"QFrame#Card {{ background: {SURFACE_CONTAINER_LOWEST}; "
        f"border: 1px solid {OUTLINE_VARIANT}; border-radius: 8px; }}"
    )
    outer = QVBoxLayout(card)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)
    top = QFrame()
    # Scoped (#id): a bare `QFrame {...}` rule would restyle every QFrame
    # below this bar — inline scope beats app-level rules subtree-wide.
    top.setObjectName("CardTopBar")
    top.setStyleSheet(
        f"QFrame#CardTopBar {{ background: {BACKGROUND}; border-bottom: 1px solid {SURFACE_CONTAINER_LOW}; "
        "border-top-left-radius: 8px; border-top-right-radius: 8px; }"
    )
    top_lay = QHBoxLayout(top)
    top_lay.setContentsMargins(16, 12, 16, 12)
    top_lay.setSpacing(12)
    title_lbl = QLabel(title)
    title_lbl.setStyleSheet(
        f"font-size: 15px; font-weight: 600; color: {ON_SURFACE}; "
        "border: none; background: transparent;"
    )
    top_lay.addWidget(title_lbl)
    top_lay.addStretch(1)
    outer.addWidget(top)
    body = QVBoxLayout()
    body.setContentsMargins(16, 12, 16, 12)
    body.setSpacing(8)
    wrap = QWidget()
    wrap.setLayout(body)
    wrap.setObjectName("CardBodyWrap")
    wrap.setStyleSheet("QWidget#CardBodyWrap { background: transparent; border: none; }")
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
        btn.setIcon(_icon("info", color=ON_SECONDARY_CONTAINER, size=14))
    except Exception:
        btn.setText("i")
    btn.setIconSize(QSize(14, 14))
    btn.setFixedSize(24, 24)
    btn.setAutoRaise(True)
    btn.setCursor(Qt.WhatsThisCursor)
    btn.setToolTip(tip)
    btn.setAccessibleName(f"About {name}" if name else "Section help")
    btn.setAccessibleDescription(tip)
    btn.setStyleSheet(
        "QToolButton#InfoTip { background: transparent; border: none; "
        "border-radius: 12px; padding: 0; }"
        f"QToolButton#InfoTip:hover {{ background: {SURFACE_CONTAINER}; }}"
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
        f"QLineEdit#SearchField {{ background: {SURFACE_CONTAINER_LOWEST}; "
        f"border: 1px solid {OUTLINE_VARIANT}; border-radius: 8px; "
        "padding-left: 12px; font-size: 13px; }"
        f"QLineEdit#SearchField:focus {{ border: 1px solid {PRIMARY}; }}"
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
        f"QLineEdit#SearchField {{ background: {SURFACE_CONTAINER_LOWEST}; "
        f"border: 1px solid {OUTLINE_VARIANT}; border-radius: 8px; "
        "padding-left: 12px; font-size: 13px; }"
        f"QLineEdit#SearchField:focus {{ border: 1px solid {PRIMARY}; }}"
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
