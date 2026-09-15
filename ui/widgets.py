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

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from ui.theme import (
    ON_SURFACE,
    ON_SURFACE_VARIANT,
    OUTLINE_VARIANT,
    SURFACE_CONTAINER_LOW,
    SURFACE_CONTAINER_LOWEST,
    enable_list_copy,
    enable_table_copy,
    selectable_labels,
)

__all__ = [
    "AppButton",
    "AppTable",
    "make_card",
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
    """Standard table: movable + resizable + sortable columns, row selection,
    no gridlines, hidden vertical header, Ctrl+C copy support.

    headers: ordered column titles. widths: {index: px} initial widths
    (default 120). row_height: vertical default section size.
    sortable: leave True unless the view depends on insertion order.
    """

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
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.setAlternatingRowColors(False)
        self.setWordWrap(False)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(row_height)
        self.setFocusPolicy(Qt.NoFocus)
        self.setSortingEnabled(sortable)
        enable_table_copy(self)

    def populate_guarded(self, row_count: int) -> None:
        """setRowCount with sorting suppressed so inserts stay in order."""
        was = self.isSortingEnabled()
        self.setSortingEnabled(False)
        self.setRowCount(row_count)
        self.setSortingEnabled(was)


def make_card(title: str, parent: QWidget | None = None) -> tuple:
    """Standard white card (12px radius) with a header bar.

    Returns (card, body_layout, title_label, header_layout) — append extra
    header widgets (summaries, combos, filters) to header_layout.
    """
    card = QFrame(parent)
    card.setObjectName("Card")
    card.setStyleSheet(
        f"QFrame#Card {{ background: {SURFACE_CONTAINER_LOWEST}; "
        f"border: 1px solid {OUTLINE_VARIANT}; border-radius: 12px; }}"
    )
    outer = QVBoxLayout(card)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)
    top = QFrame()
    top.setStyleSheet(
        f"QFrame {{ background: #faf8ff; border-bottom: 1px solid {SURFACE_CONTAINER_LOW}; "
        "border-top-left-radius: 12px; border-top-right-radius: 12px; }"
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
    wrap.setStyleSheet("background: transparent; border: none;")
    outer.addWidget(wrap)
    return card, body, title_lbl, top_lay


def make_search_field(placeholder: str, parent: QWidget | None = None, *, height: int = 36,
                      min_width: int = 220) -> QLineEdit:
    """Standard search box (SearchField style: rounded, 13px text)."""
    field = QLineEdit(parent)
    field.setObjectName("SearchField")
    field.setPlaceholderText(placeholder)
    field.setFixedHeight(height)
    field.setMinimumWidth(min_width)
    field.setStyleSheet(
        f"QLineEdit#SearchField {{ background: {SURFACE_CONTAINER_LOWEST}; "
        f"border: 1px solid {OUTLINE_VARIANT}; border-radius: 8px; "
        "padding-left: 12px; font-size: 13px; }"
        "QLineEdit#SearchField:focus { border: 1px solid #004ccd; }"
    )
    return field


def make_line_edit(placeholder: str = "", parent: QWidget | None = None, *,
                   height: int = 36, password: bool = False) -> QLineEdit:
    """Standard form field: same height/focus ring as make_search_field."""
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
        "QLineEdit#SearchField:focus { border: 1px solid #004ccd; }"
    )
    return field


def make_combo(items=None, parent: QWidget | None = None, *, height: int = 36,
               min_width: int = 130, tip: str = "") -> QComboBox:
    """Standard dropdown (themed chevron, 12px semibold entries).

    items: list of labels or (label, data) tuples.
    """
    combo = QComboBox(parent)
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
