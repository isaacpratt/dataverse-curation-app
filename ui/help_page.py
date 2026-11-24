"""Help page: a searchable index of every (i) tooltip, grouped by task.

The kit's ``add_info_tip`` registers each tip into ``ui.help_index``
(dv-o8k); hover help is for the focused moment, this page is for the
whole story. Rebuilt on every show so the index covers pages opened
during the session — a few dozen string copies, microseconds of work.
"""

from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ui.help_index import GROUP_ORDER, grouped, help_entries
from ui.i18n import t
from ui.theme import (
    ACTIVE_THEME,
    BORDER_SUBTLE,
    SURFACE_CARD,
    page_background_qss,
    surface_frame_qss,
    transparent_surface_qss,
)
from ui.widgets import make_caption_label, make_page_heading, make_search_field

# Literal keys: the strings test validates that every catalogue key is used
# and every t() literal exists — no t(f"...") constructions here.
_GROUP_KEYS = {
    "Queue": "help.groups.queue",
    "Download": "help.groups.download",
    "Checks": "help.groups.checks",
    "Respond": "help.groups.respond",
    "General": "help.groups.general",
}


class HelpPane(QWidget):
    """Searchable task-grouped list of the app's help tips."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # Scoped to self (same contract as the other stack pages).
        self.setObjectName("HelpPane")
        self.setStyleSheet(page_background_qss("HelpPane", theme=ACTIVE_THEME))

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(16)

        heading, subtitle = make_page_heading(t("help.heading"), t("help.sub"))
        outer.addWidget(heading)
        if subtitle is not None:
            outer.addWidget(subtitle)

        self._search = make_search_field(t("help.search_placeholder"), min_width=220)
        self._search.textChanged.connect(self._apply_filter)
        outer.addWidget(self._search)

        self._scroll = QScrollArea()
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setWidgetResizable(True)
        self._canvas = QWidget()
        self._canvas.setObjectName("HelpCanvas")
        self._canvas.setStyleSheet(transparent_surface_qss("HelpCanvas", theme=ACTIVE_THEME))
        self._column = QVBoxLayout(self._canvas)
        self._column.setContentsMargins(0, 0, 0, 0)
        self._column.setSpacing(16)
        self._scroll.setWidget(self._canvas)
        outer.addWidget(self._scroll, 1)

        self._empty = make_caption_label(t("help.empty"))
        outer.addWidget(self._empty)
        self._empty.hide()

        self._rows: list[tuple[QWidget, QWidget, str]] = []  # group, row, haystack
        self.populate()

    # -- content -----------------------------------------------------------

    def _group_title(self, group: str) -> QLabel:
        lbl = QLabel(t(_GROUP_KEYS[group]))
        lbl.setObjectName("HeadlineMD")
        return lbl

    def _entry_block(self, name: str, text: str) -> QFrame:
        block = QFrame()
        block.setObjectName("Card")
        block.setStyleSheet(surface_frame_qss(SURFACE_CARD, BORDER_SUBTLE, selector="QFrame#Card", theme=ACTIVE_THEME))
        lay = QVBoxLayout(block)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(4)
        if name:
            row = QHBoxLayout()
            row.setSpacing(8)
            name_lbl = QLabel(name)
            name_lbl.setObjectName("ValueSM")
            row.addWidget(name_lbl, 1)
            lay.addLayout(row)
        lay.addWidget(make_caption_label(text))
        return block

    def populate(self) -> None:
        """Rebuild the list from the current registry (cheap string work)."""
        # Clear the column.
        while self._column.count():
            item = self._column.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._rows.clear()

        for group in GROUP_ORDER:
            items = grouped("").get(group)
            if not items:
                continue
            g_title = self._group_title(group)
            self._column.addWidget(g_title)
            self._rows.append((g_title, g_title, f"{group} {t(_GROUP_KEYS[group])}"))
            for name, text in items:
                block = self._entry_block(name, text)
                self._column.addWidget(block)
                self._rows.append((g_title, block, f"{group} {name} {text}"))
        self._column.addStretch(1)
        self._apply_filter(self._search.text() if hasattr(self, "_search") else "")
        self._log_build()

    def _log_build(self) -> None:
        try:
            from curation.applog import get_app_log

            get_app_log().info(t("help.built_log", count=len(help_entries())))
        except Exception:
            pass

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        # Re-index so tips from lazily opened pages (Settings, Review
        # configuration, dataset detail) appear without an app restart.
        self.populate()

    # -- search ---------------------------------------------------------------

    def _apply_filter(self, text: str) -> None:
        q = (text or "").strip().lower()
        current_group: QWidget | None = None
        current_group_rows = 0
        any_visible = False
        for group_widget, row, haystack in self._rows:
            is_group_header = row is group_widget
            if is_group_header:
                if current_group is not None:
                    current_group.setVisible(current_group_rows > 0)
                current_group = row
                current_group_rows = 0
                continue
            visible = not q or q in haystack.lower()
            row.setVisible(visible)
            if visible:
                current_group_rows += 1
                any_visible = True
        if current_group is not None:
            current_group.setVisible(current_group_rows > 0)
        self._empty.setVisible(not any_visible)

    # -- test hooks ---------------------------------------------------------

    def visible_entry_count(self) -> int:
        return sum(1 for g, row, _h in self._rows if row is not g and row.isVisible())
