"""Design tokens for the app (originally extracted from a Tailwind mock).

Palette is Material 3-like: primary #004ccd, tertiary #4142cf, error #ba1a1a,
surface #faf8ff, backgrounds #f2f3ff/#eaedff, outline-variant #c3c6d8.
Typography is Inter (body) + JetBrains Mono (monospace)."""

# --- Colors ---
PRIMARY = "#004ccd"
PRIMARY_CONTAINER = "#0f62fe"
ON_PRIMARY = "#ffffff"
ON_PRIMARY_FIXED_VARIANT = "#003da9"
PRIMARY_FIXED_DIM = "#b4c5ff"
PRIMARY_FIXED = "#dbe1ff"

TERTIARY = "#4142cf"
TERTIARY_CONTAINER = "#5b5ee9"
ON_TERTIARY_CONTAINER = "#f6f3ff"
TERTIARY_FIXED_DIM = "#c0c1ff"

ERROR = "#ba1a1a"
ERROR_CONTAINER = "#ffdad6"
ON_ERROR_CONTAINER = "#93000a"
ON_ERROR = "#ffffff"

SURFACE = "#faf8ff"
BACKGROUND = "#faf8ff"
SURFACE_BRIGHT = "#faf8ff"
SURFACE_CONTAINER_LOWEST = "#ffffff"
SURFACE_CONTAINER_LOW = "#f2f3ff"
SURFACE_CONTAINER = "#eaedff"
SURFACE_CONTAINER_HIGH = "#e2e7ff"
SURFACE_CONTAINER_HIGHEST = "#dae2fd"
SURFACE_DIM = "#d2d9f4"
SURFACE_VARIANT = "#dae2fd"

OUTLINE_VARIANT = "#c3c6d8"
OUTLINE = "#737687"

ON_SURFACE = "#131b2e"
ON_SURFACE_VARIANT = "#424656"
ON_SECONDARY_CONTAINER = "#57657a"
ON_SECONDARY_FIXED = "#0d1c2e"
SECONDARY_CONTAINER = "#d5e3fc"
SECONDARY = "#515f74"

# --- Typography (Qt QSS uses px) ---
FONT_FAMILY = "Inter, 'Segoe UI', sans-serif"
MONO_FAMILY = "'JetBrains Mono', Consolas, monospace"

# --- Radii / Sizes ---
RADIUS_XL = "12px"
RADIUS_LG = "8px"
RADIUS_MD = "6px"
RADIUS_SM = "4px"

# --- Spacing scale (px) — layouts should use these, not magic numbers ---
SP_XS = 4
SP_SM = 8
SP_MD = 12
SP_LG = 16
SP_XL = 20
SP_XXL = 24

# --- Standard margins ---
MARGIN_PAGE = 24      # outer view padding
MARGIN_CARD_H = 16    # card header/body horizontal padding
MARGIN_CARD_V = 12    # card header/body vertical padding

# --- Type scale (px) ---
FONT_HEADLINE = 22
FONT_TITLE = 16
FONT_SECTION = 15
FONT_BODY = 13
FONT_SMALL = 12
FONT_CAPTION = 11

# --- Shadows (simulated via border) ---
CARD_BORDER = f"1px solid {OUTLINE_VARIANT}"


def asset_path(name: str) -> str:
    """Absolute path to a bundled ui/asset (works frozen via sys._MEIPASS)."""
    import sys
    from pathlib import Path

    candidates = []
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        candidates.append(Path(meipass) / "ui" / "assets" / name)
        candidates.append(Path(meipass) / "assets" / name)
    candidates.append(Path(__file__).resolve().parent / "assets" / name)
    for path in candidates:
        try:
            if path.exists():
                return path.as_posix()
        except Exception:
            continue
    return ""


def _chevron_qss() -> str:
    """Down-arrow rule: real chevron glyph when bundled, CSS triangle fallback."""
    arrow = asset_path("chevron-down.png")
    if arrow:
        return f"""QComboBox::down-arrow {{
    image: url({arrow});
    width: 14px;
    height: 14px;
    margin-right: 10px;
}}"""
    return f"""QComboBox::down-arrow {{
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {ON_SURFACE_VARIANT};
    margin-right: 8px;
}}"""


def global_qss() -> str:
    return f"""
/* ===== Base ===== */
QWidget {{
    font-family: {FONT_FAMILY};
    color: {ON_SURFACE};
}}
QMainWindow, QStackedWidget, QScrollArea {{
    background: {BACKGROUND};
}}

/* ===== Top nav / header bar ===== */
#TopNav {{
    background: {SURFACE_CONTAINER_LOWEST};
    border-bottom: 1px solid {OUTLINE_VARIANT};
}}
#TopNav QPushButton#NavActive {{
    background: {SECONDARY_CONTAINER};
    color: #0d1c2e;
    border: none;
    border-radius: 8px;
    padding: 6px 12px;
    font-weight: 600;
    font-size: 12px;
}}
#TopNav QPushButton#NavItem {{
    background: transparent;
    color: {ON_SURFACE_VARIANT};
    border: none;
    border-radius: 8px;
    padding: 6px 12px;
    font-weight: 500;
    font-size: 12px;
}}
#TopNav QPushButton#NavItem:hover {{
    background: {SURFACE_CONTAINER_HIGH};
    color: {ON_SURFACE};
}}
/* Toggle nav buttons (Settings/Log/About) are checkable: a checked button
   reads exactly like the active location tab so "pane open" is unmistakable
   and identical for Log and Settings. */
#TopNav QPushButton#NavItem:checked {{
    background: {SECONDARY_CONTAINER};
    color: #0d1c2e;
    font-weight: 600;
}}
#TopNav QLabel#Brand {{
    font-size: 16px;
    font-weight: 700;
    color: {PRIMARY};
}}

/* ===== Cards ===== */
#Card {{
    background: {SURFACE_CONTAINER_LOWEST};
    border: {CARD_BORDER};
    border-radius: {RADIUS_XL};
}}
#MetricCard {{
    background: {SURFACE_CONTAINER_LOWEST};
    border: {CARD_BORDER};
    border-radius: {RADIUS_XL};
}}

#SectionHeader {{
    background: {SURFACE_CONTAINER_LOWEST};
    border-bottom: 1px solid {SURFACE_CONTAINER_LOW};
}}

/* ===== Buttons: pill shape (stadium ends), clear hover highlight ===== */
QPushButton#PrimaryButton {{
    background: {PRIMARY};
    color: {ON_PRIMARY};
    border: none;
    border-radius: 18px;
    padding: 8px 16px;
    font-weight: 600;
    font-size: 12px;
}}
QPushButton#PrimaryButton:hover {{ background: {ON_PRIMARY_FIXED_VARIANT}; }}
QPushButton#PrimaryButton:pressed {{ background: #002a78; }}
/* Disabled primary stays readable (muted blue, white text) so the action
   still reads as present-but-unavailable instead of vanishing. */
QPushButton#PrimaryButton:disabled {{ background: #8aa9e8; color: {ON_PRIMARY}; }}

QPushButton#SecondaryButton {{
    background: {SURFACE_CONTAINER_LOWEST};
    color: {ON_SURFACE};
    border: 1px solid {OUTLINE_VARIANT};
    border-radius: 18px;
    padding: 7px 14px;
    font-weight: 600;
    font-size: 12px;
}}
QPushButton#SecondaryButton:hover {{ background: {SURFACE_CONTAINER_HIGH}; border: 1px solid {PRIMARY}; }}
QPushButton#SecondaryButton:pressed {{ background: {SECONDARY_CONTAINER}; }}

QPushButton#GhostButton {{
    background: transparent;
    color: {ON_SURFACE_VARIANT};
    border: none;
    border-radius: 6px;
    padding: 6px 10px;
}}
QPushButton#GhostButton:hover {{ background: {SURFACE_CONTAINER}; color: {ON_SURFACE}; }}

/* Column chooser / filter chip */
QPushButton#FilterChip {{
    background: {SURFACE_CONTAINER_LOWEST};
    border: 1px solid {OUTLINE_VARIANT};
    border-radius: 18px;
    padding: 6px 10px;
    font-size: 12px;
    font-weight: 600;
    color: {ON_SURFACE_VARIANT};
}}
QPushButton#FilterChip:hover {{ background: {SURFACE_CONTAINER_HIGH}; border: 1px solid {PRIMARY}; }}

/* ===== Inputs ===== */
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox {{
    background: {SURFACE_CONTAINER_LOWEST};
    border: 1px solid {OUTLINE_VARIANT};
    border-radius: {RADIUS_MD};
    padding: 7px 10px;
    selection-background-color: {PRIMARY_FIXED};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{
    border: 1px solid {PRIMARY};
}}
QLineEdit#SearchField {{
    padding-left: 32px;
    background: {SURFACE_CONTAINER_LOWEST};
}}

/* ComboBox drop-down: fully owner-drawn button so no native edge, groove
   or separator line can render — just the chevron glyph. */
QComboBox {{
    padding-right: 32px;
}}
QComboBox::drop-down {{
    border: none;
    border-left: none;
    border-width: 0px;
    background: transparent;
    width: 30px;
    margin: 0px;
    padding: 0px;
    subcontrol-origin: padding;
    subcontrol-position: top right;
}}
{_chevron_qss()}
QComboBox QAbstractItemView {{
    background: {SURFACE_CONTAINER_LOWEST};
    border: 1px solid {OUTLINE_VARIANT};
    border-radius: 8px;
    selection-background-color: {SECONDARY_CONTAINER};
    selection-color: {ON_SURFACE};
    outline: 0;
}}
QComboBox QAbstractItemView::item {{
    border: none;
    padding: 6px 10px;
}}
QComboBox QAbstractItemView::item:selected {{
    background: {SECONDARY_CONTAINER};
    color: {ON_SURFACE};
    border: none;
}}
/* While open, the field's bottom corners go square so they meet the
   popup flush — no notch/gap artifacts at the junction. */
QComboBox:on {{
    border-bottom-left-radius: 0px;
    border-bottom-right-radius: 0px;
}}

/* ===== Table ===== */
QTableWidget {{
    background: {SURFACE_CONTAINER_LOWEST};
    border: none;
    gridline-color: {OUTLINE_VARIANT};
    selection-background-color: {SECONDARY_CONTAINER};
    alternate-background-color: {SURFACE_CONTAINER_LOW};
}}
QTableWidget::item {{
    padding: 10px 12px;
    border-bottom: 1px solid {SURFACE_CONTAINER_LOW};
}}
QHeaderView::section {{
    background: {SURFACE_CONTAINER};
    color: {ON_SURFACE_VARIANT};
    padding: 8px 12px;
    border: none;
    border-bottom: 1px solid {OUTLINE_VARIANT};
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}
QHeaderView::section:first {{
    border-top-left-radius: 11px;
}}
QHeaderView::section:last {{
    border-top-right-radius: 11px;
}}
QTableWidget::item:selected {{
    background: {SECONDARY_CONTAINER};
    color: {ON_SURFACE};
}}

/* ===== Labels ===== */
QLabel#HeadlineLG {{
    font-size: 22px;
    font-weight: 600;
    color: {ON_SURFACE};
    letter-spacing: -0.2px;
}}
QLabel#HeadlineMD {{
    font-size: 16px;
    font-weight: 600;
    color: {ON_SURFACE};
}}
QLabel#BodyMD {{
    font-size: 13px;
    color: {ON_SURFACE_VARIANT};
}}
QLabel#LabelMD {{
    font-size: 11px;
    font-weight: 600;
    color: {ON_SURFACE_VARIANT};
    letter-spacing: 0.5px;
}}
QLabel#MonoSM {{
    font-family: {MONO_FAMILY};
    font-size: 12px;
    color: {ON_SURFACE_VARIANT};
}}

/* ===== Status pills (QLabel with objectName) ===== */
QLabel#PillInReview {{
    background: {SECONDARY_CONTAINER};
    color: #1a2e4a;
    border: 1px solid #b9c7df;
    border-radius: 6px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 700;
}}
QLabel#PillDraft {{
    background: {SURFACE_VARIANT};
    color: {ON_SURFACE_VARIANT};
    border: 1px solid {OUTLINE_VARIANT};
    border-radius: 6px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 700;
}}
QLabel#PillAuthorContacted {{
    background: {ERROR_CONTAINER};
    color: {ON_ERROR_CONTAINER};
    border: 1px solid #ffb4ab;
    border-radius: 6px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 700;
}}
QLabel#PillReady {{
    background: {TERTIARY};
    color: {ON_PRIMARY};
    border: 1px solid {TERTIARY};
    border-radius: 6px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 700;
}}
QLabel#PillClean {{
    color: {PRIMARY};
    font-size: 12px;
    font-weight: 600;
}}
QLabel#PillFlagged {{
    color: {ERROR};
    font-size: 12px;
    font-weight: 600;
}}

/* ===== Auto-check rows ===== */
#CheckRowPass {{
    background: {SURFACE_CONTAINER};
    border: 1px solid {OUTLINE_VARIANT};
    border-radius: 8px;
}}
#CheckRowFail {{
    background: #fff0ef;
    border: 1px solid #ffb4ab;
    border-radius: 8px;
}}

/* ===== ScrollBar (subtle) ===== */
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {OUTLINE_VARIANT};
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
}}
QScrollBar::handle:horizontal {{
    background: {OUTLINE_VARIANT};
    border-radius: 4px;
    min-width: 24px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ===== TabWidget ===== */
QTabWidget::pane {{
    border: 1px solid {OUTLINE_VARIANT};
    border-radius: {RADIUS_LG};
    background: {SURFACE_CONTAINER_LOWEST};
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    color: {ON_SURFACE_VARIANT};
    padding: 8px 14px;
    border: 1px solid transparent;
    border-bottom: 2px solid transparent;
    font-size: 12px;
    font-weight: 600;
}}
QTabBar::tab:selected {{
    color: {PRIMARY};
    border-bottom: 2px solid {PRIMARY};
    background: {SURFACE_CONTAINER_LOWEST};
}}
QTabBar::tab:hover {{ color: {ON_SURFACE}; }}

/* ===== Progress ===== */
QProgressBar {{
    border: 1px solid {OUTLINE_VARIANT};
    border-radius: 6px;
    background: {SURFACE_CONTAINER_LOW};
    text-visible: false;
    height: 6px;
}}
QProgressBar::chunk {{
    background: {PRIMARY};
    border-radius: 6px;
}}

/* ===== Menu bar ===== */
QMenuBar {{
    background: {SURFACE_CONTAINER_LOWEST};
    border-bottom: 1px solid {OUTLINE_VARIANT};
}}
QMenuBar::item:selected {{ background: {SURFACE_CONTAINER}; }}
QMenu {{
    background: {SURFACE_CONTAINER_LOWEST};
    border: 1px solid {OUTLINE_VARIANT};
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item:selected {{ background: {SECONDARY_CONTAINER}; border-radius: 6px; }}

/* ===== Status bar ===== */
QStatusBar {{
    background: {SURFACE_CONTAINER_LOWEST};
    border-top: 1px solid {OUTLINE_VARIANT};
    color: {ON_SURFACE_VARIANT};
    font-size: 11px;
}}
QStatusBar::item {{ border: none; }}

/* ===== Dock widgets (log panel renders its own card, no native title bar) ===== */
QDockWidget {{
    background: {BACKGROUND};
    border: none;
    color: {ON_SURFACE};
    titlebar-close-icon: none;
    titlebar-normal-icon: none;
}}

/* ===== Splitter ===== */
QSplitter::handle {{
    background: {OUTLINE_VARIANT};
}}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}
"""

def apply_theme(app) -> None:
    """Apply global QSS and default font."""
    from PySide6.QtGui import QFont
    # Prefer Inter if installed; fall back to Segoe UI
    font = QFont("Inter")
    if font.family() != "Inter":
        font = QFont("Segoe UI")
    font.setPointSize(9)
    app.setFont(font)
    app.setStyleSheet(global_qss())
    _install_hover_cursor(app)


def action_button_style(primary: bool = False) -> str:
    """Self-contained pill styling for critical action buttons.

    Inline styles always win and always paint (unlike app-level rules,
    which demonstrably fail to render QPushButton faces inside some
    main-window subtrees). Includes hover/pressed/disabled states.
    """
    if primary:
        return (
            "QPushButton { background: #004ccd; color: #ffffff; border: none; "
            "border-radius: 18px; padding: 8px 16px; font-weight: 600; font-size: 12px; }"
            "QPushButton:hover { background: #003da9; }"
            "QPushButton:pressed { background: #002a78; }"
            "QPushButton:disabled { background: #8aa9e8; color: #ffffff; }"
        )
    return (
        "QPushButton { background: #ffffff; color: #131b2e; "
        "border: 1px solid #c3c6d8; border-radius: 18px; padding: 7px 14px; "
        "font-weight: 600; font-size: 12px; }"
        "QPushButton:hover { background: #e2e7ff; border: 1px solid #004ccd; }"
        "QPushButton:pressed { background: #d5e3fc; }"
        "QPushButton:disabled { background: #f2f3ff; color: #57657a; }"
    )


def _install_hover_cursor(app) -> None:
    """Pointing-hand cursor on every enabled button (QSS cannot set cursors).

    Installed once on the QApplication; covers buttons created later too
    (chips, table cells, dynamic rows).
    """
    try:
        from PySide6.QtCore import QEvent, QObject, Qt
        from PySide6.QtWidgets import QAbstractButton

        class _HoverCursor(QObject):
            def eventFilter(self, obj, event):
                try:
                    if event.type() == QEvent.Enter and isinstance(obj, QAbstractButton):
                        if obj.isEnabled():
                            obj.setCursor(Qt.PointingHandCursor)
                        else:
                            obj.unsetCursor()
                except Exception:
                    pass
                return False

        filt = _HoverCursor(app)
        app.installEventFilter(filt)
        try:
            app._hover_cursor_ref = filt
        except Exception:
            pass
    except Exception:
        pass


def selectable_labels(root) -> None:
    """Make every QLabel under root selectable with mouse + keyboard."""
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QLabel

        for lbl in root.findChildren(QLabel):
            try:
                flags = lbl.textInteractionFlags()
                lbl.setTextInteractionFlags(
                    flags | Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
                )
            except Exception:
                continue
    except Exception:
        pass


def enable_table_copy(table) -> None:
    """Ctrl+C support + extended selection for a QTableWidget (best-effort)."""
    try:
        from PySide6.QtCore import QEvent, QObject, Qt
        from PySide6.QtWidgets import QApplication, QTableWidget

        table.setSelectionMode(QTableWidget.ExtendedSelection)

        class _CopyFilter(QObject):
            def eventFilter(self, _obj, event):
                try:
                    if event.type() == QEvent.KeyPress and event.matches(Qt.Key_Copy):
                        ranges = table.selectedRanges()
                        if ranges:
                            rows = set()
                            for rng in ranges:
                                rows.update(range(rng.topRow(), rng.bottomRow() + 1))
                            lines = []
                            for r in sorted(rows):
                                cells = []
                                for rng in ranges:
                                    if rng.topRow() <= r <= rng.bottomRow():
                                        for c in range(rng.leftColumn(), rng.rightColumn() + 1):
                                            item = table.item(r, c)
                                            cells.append(item.text() if item else "")
                                lines.append("\t".join(cells))
                            QApplication.clipboard().setText("\n".join(lines))
                            return True
                except Exception:
                    pass
                return False

        table.installEventFilter(_CopyFilter(table))
        try:
            # Keep a reference so the filter is not garbage-collected.
            table._copy_filter_ref = table.findChildren(_CopyFilter)[-1]
        except Exception:
            pass
    except Exception:
        pass


def enable_list_copy(list_widget) -> None:
    """Ctrl+C support for a QListWidget (copies selected rows as lines)."""
    try:
        from PySide6.QtCore import QEvent, QObject, Qt
        from PySide6.QtWidgets import QApplication

        list_widget.setSelectionMode(list_widget.ExtendedSelection)

        class _ListCopyFilter(QObject):
            def eventFilter(self, _obj, event):
                try:
                    if event.type() == QEvent.KeyPress and event.matches(Qt.Key_Copy):
                        items = list_widget.selectedItems()
                        if items:
                            QApplication.clipboard().setText(
                                "\n".join(i.text() for i in items)
                            )
                            return True
                except Exception:
                    pass
                return False

        list_widget.installEventFilter(_ListCopyFilter(list_widget))
        try:
            list_widget._copy_filter_ref = list_widget.findChildren(_ListCopyFilter)[-1]
        except Exception:
            pass
    except Exception:
        pass
