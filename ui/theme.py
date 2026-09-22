"""Design tokens for the app (originally extracted from a Tailwind mock).

Palette is Material 3-like: primary #004ccd, tertiary #4142cf, error #ba1a1a,
surface #faf8ff, backgrounds #f2f3ff/#eaedff, outline-variant #c3c6d8.
Typography is Inter (body) + JetBrains Mono (monospace).
"""

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
# Unified app-wide corner radius: everything (cards, inputs, tables, panes,
# buttons, badges, menus) uses RADIUS_LG, matching the dropdown menus. The
# smaller tokens stay defined for reference; only structural square junctions
# (combo-popup seam, tab-pane seam, caption buttons) keep 0px corners.
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
    """Down-arrow rule: Lucide chevron when bundled, CSS triangle fallback."""
    arrow = asset_path("lucide/chevron-down-grey.svg")
    if not arrow:
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
    border-radius: {RADIUS_LG};
}}
#MetricCard {{
    background: {SURFACE_CONTAINER_LOWEST};
    border: {CARD_BORDER};
    border-radius: {RADIUS_LG};
}}

#SectionHeader {{
    background: {SURFACE_CONTAINER_LOWEST};
    border-bottom: 1px solid {SURFACE_CONTAINER_LOW};
}}

/* ===== Buttons: 8px rounded rectangles (unified radius), clear hover highlight ===== */
QPushButton#PrimaryButton {{
    background: {PRIMARY};
    color: {ON_PRIMARY};
    border: none;
    border-radius: {RADIUS_LG};
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
    border-radius: {RADIUS_LG};
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
    border-radius: {RADIUS_LG};
    padding: 6px 10px;
}}
QPushButton#GhostButton:hover {{ background: {SURFACE_CONTAINER}; color: {ON_SURFACE}; }}

/* Column chooser / filter chip */
QPushButton#FilterChip {{
    background: {SURFACE_CONTAINER_LOWEST};
    border: 1px solid {OUTLINE_VARIANT};
    border-radius: {RADIUS_LG};
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
    border-radius: {RADIUS_LG};
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
/* Popup descends straight from the button: square top corners meet the
   (squared when open) button flush, 8px rounds only the bottom. Item
   metrics are pinned (not font-implied) so every menu spaces choices
   identically no matter which card hosts the combo. */
QComboBox QAbstractItemView {{
    background: {SURFACE_CONTAINER_LOWEST};
    border: 1px solid {OUTLINE_VARIANT};
    border-top-left-radius: 0px;
    border-top-right-radius: 0px;
    border-bottom-left-radius: {RADIUS_LG};
    border-bottom-right-radius: {RADIUS_LG};
    selection-background-color: {SECONDARY_CONTAINER};
    selection-color: {ON_SURFACE};
    outline: 0;
}}
QComboBox QAbstractItemView::item {{
    border: none;
    min-height: 22px;
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
    padding: 8px 14px 8px 12px;
    border: none;
    border-bottom: 1px solid {OUTLINE_VARIANT};
    border-right: 1px solid {OUTLINE_VARIANT};
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}
QHeaderView::section:hover {{
    background: {SURFACE_CONTAINER_HIGH};
    border-right: 1px solid {OUTLINE};
}}
QHeaderView::section:pressed {{
    background: {PRIMARY_FIXED};
    border-right: 2px solid {PRIMARY};
}}
QHeaderView::section:first {{
    border-top-left-radius: {RADIUS_LG};
}}
QHeaderView::section:last {{
    border-top-right-radius: {RADIUS_LG};
    border-right: none;
}}
QTableWidget::item:selected {{
    background: {SECONDARY_CONTAINER};
    color: {ON_SURFACE};
}}

/* ===== Tooltips ===== */
/* Explicit light face for EVERY tooltip app-wide: without this, the global
   QWidget text color leaks into system-drawn (dark) tooltip backgrounds and
   renders black unreadable boxes (seen on dataset log + metadata table). */
QToolTip {{
    background: {SURFACE_CONTAINER_LOWEST};
    color: {ON_SURFACE};
    border: 1px solid {OUTLINE_VARIANT};
    border-radius: {RADIUS_LG};
    padding: 6px 8px;
    font-size: 12px;
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
    border-radius: {RADIUS_LG};
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 700;
}}
QLabel#PillDraft {{
    background: {SURFACE_VARIANT};
    color: {ON_SURFACE_VARIANT};
    border: 1px solid {OUTLINE_VARIANT};
    border-radius: {RADIUS_LG};
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 700;
}}
QLabel#PillAuthorContacted {{
    background: {ERROR_CONTAINER};
    color: {ON_ERROR_CONTAINER};
    border: 1px solid #ffb4ab;
    border-radius: {RADIUS_LG};
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 700;
}}
QLabel#PillReady {{
    background: {TERTIARY};
    color: {ON_PRIMARY};
    border: 1px solid {TERTIARY};
    border-radius: {RADIUS_LG};
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
/* Opaque table-surface gutters: transparent tracks failed to composite and
   left the scrollbar lanes + the bottom-right meeting corner page-colored
   ("unfilled"). White matches every table/list surface in the app. */
QScrollBar:vertical {{
    background: {SURFACE_CONTAINER_LOWEST};
    width: 8px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {OUTLINE_VARIANT};
    border-radius: {RADIUS_LG};
    min-height: 24px;
}}
QScrollBar::groove:vertical {{
    background: {SURFACE_CONTAINER_LOWEST};
    border: none;
    margin: 0px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: {SURFACE_CONTAINER_LOWEST};
    height: 8px;
    margin: 0;
}}
QScrollBar::groove:horizontal {{
    background: {SURFACE_CONTAINER_LOWEST};
    border: none;
    margin: 0px;
}}
QScrollBar::handle:horizontal {{
    background: {OUTLINE_VARIANT};
    border-radius: {RADIUS_LG};
    min-width: 24px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ===== TabWidget ===== */
/* The pane itself draws NO outline: QTabWidget::pane is painted by Qt's
   special tab-frame primitive, which ignores border-radius (it shortens
   straight edges for the radius but never paints the corner arcs, leaving
   open corners — verified by pixel-probe against a QFrame control).
   The outline + rounded corners come from a plain QFrame#Card wrapper
   around the tab widget (see settings_dialog.py), which uses the generic
   frame renderer where arcs work. Pane stays transparent so the card's
   white face shows through; tab-bar rules below are unaffected. */
QTabWidget::pane {{
    border: none;
    border-radius: 0px;
    background: transparent;
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
    border-radius: {RADIUS_LG};
    background: {SURFACE_CONTAINER_LOW};
    text-visible: false;
    height: 6px;
}}
QProgressBar::chunk {{
    background: {PRIMARY};
    border-radius: {RADIUS_LG};
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
    /* Square top corners: a menu opens directly under its button, so the
       popup connects flush into the element that opened it (same junction
       contract as QComboBox popups above). Only the bottom rounds. */
    border-top-left-radius: 0px;
    border-top-right-radius: 0px;
    border-bottom-left-radius: {RADIUS_LG};
    border-bottom-right-radius: {RADIUS_LG};
    padding: 4px;
}}
QMenu::item:selected {{ background: {SECONDARY_CONTAINER}; border-radius: {RADIUS_LG}; }}

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
    """Self-contained rounded-rectangle styling for critical action buttons.

    Inline styles always win and always paint (unlike app-level rules,
    which demonstrably fail to render QPushButton faces inside some
    main-window subtrees). Includes hover/pressed/disabled states.
    """
    if primary:
        return (
            "QPushButton { background: #004ccd; color: #ffffff; border: none; "
            "border-radius: 8px; padding: 8px 16px; font-weight: 600; font-size: 12px; }"
            "QPushButton:hover { background: #003da9; }"
            "QPushButton:pressed { background: #002a78; }"
            "QPushButton:disabled { background: #8aa9e8; color: #ffffff; }"
        )
    return (
        "QPushButton { background: #ffffff; color: #131b2e; "
        "border: 1px solid #c3c6d8; border-radius: 8px; padding: 7px 14px; "
        "font-weight: 600; font-size: 12px; }"
        "QPushButton:hover { background: #e2e7ff; border: 1px solid #004ccd; }"
        "QPushButton:pressed { background: #d5e3fc; }"
        "QPushButton:disabled { background: #f2f3ff; color: #57657a; }"
    )


# Per-label badge colors (background, text, border): every distinct status /
# curation label gets its own color so dataset-page badges scan at a glance.
# Order matters — substring match on the lowered label, specific phrases
# first ("hold for internal review" must beat bare "review").
_LABEL_BADGE_KNOWN: list[tuple[str, tuple[str, str, str]]] = [
    ("deaccessioned", ("#515F74", "#FFFFFF", "#515F74")),
    ("reject", ("#BA1A1A", "#FFFFFF", "#BA1A1A")),
    ("revisions", ("#FFDAD6", "#93000A", "#FFB4AB")),
    ("needs review", ("#FFEDD5", "#9A3412", "#FDBA74")),
    ("hold", ("#E7E4FF", "#4142CF", "#C0C1FF")),
    ("author contacted", ("#FEF3C7", "#92400E", "#FCD34D")),
    ("contact author", ("#FEF3C7", "#92400E", "#FCD34D")),
    ("approve", ("#16A34A", "#FFFFFF", "#16A34A")),
    ("ready", ("#D7F3F0", "#0F766E", "#99E4DC")),
    ("publish", ("#DFF5E1", "#14532D", "#A7E3B5")),
    ("released", ("#DFF5E1", "#14532D", "#A7E3B5")),
    ("review", ("#D5E3FC", "#1A2E4A", "#B9C7DF")),
    ("draft", ("#E4E7F2", "#424656", "#C3C6D8")),
]

# Fallback for custom instance labels: deterministic (md5, not hash() which
# is salted per process) light bg / dark text pairs.
_LABEL_BADGE_FALLBACK: list[tuple[str, str, str]] = [
    ("#D7F3F0", "#0F766E", "#99E4DC"),
    ("#E2E8FF", "#3730A3", "#C7D2FE"),
    ("#FCE7F3", "#9D174D", "#F9A8D4"),
    ("#ECFCCB", "#3F6212", "#BEF264"),
    ("#E0F2FE", "#0C4A6E", "#BAE6FD"),
    ("#F5EFE6", "#713F12", "#E7D5B7"),
]


def label_badge_colors(label: str) -> tuple[str, str, str]:
    """(background, text, border) for a status/curation label. Never raises."""
    try:
        lowered = (label or "").strip().lower()
    except Exception:
        lowered = ""
    for phrase, colors in _LABEL_BADGE_KNOWN:
        if phrase and phrase in lowered:
            return colors
    try:
        import hashlib

        digest = hashlib.md5(lowered.encode("utf-8")).digest()
        return _LABEL_BADGE_FALLBACK[digest[0] % len(_LABEL_BADGE_FALLBACK)]
    except Exception:
        return _LABEL_BADGE_FALLBACK[0]


def label_badge_style(label: str) -> str:
    """Build an inline badge face with DOI-badge chrome (bordered 8px box).

    Uses the label's own colors. Inline so it always paints (see
    action_button_style).
    """
    bg, fg, border = label_badge_colors(label)
    return (
        f"QLabel {{ background: {bg}; color: {fg}; border: 1px solid {border}; "
        "border-radius: 8px; padding: 3px 8px; font-size: 12px; font-weight: 700; }}"
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
