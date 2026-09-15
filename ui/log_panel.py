"""Live curation log strip — lives directly under the top nav bar.

Uses QPlainTextEdit with a custom QSyntaxHighlighter that colours:
- ERROR lines red, WARNING/WARN lines yellow
- IP addresses, SQL keywords, XML tags, Java backtrace file:line, quoted strings
- Random consistent colours for identifiers (INAV-style)

Colour palette pulled from ui.theme tokens so the log follows the same brand
palette as the rest of the app while staying deliberately distinct (high
contrast, dark-on-light backgrounds for ERROR/WARN rows).
"""

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import applog
from ui.theme import (
    ERROR,
    ERROR_CONTAINER,
    ON_ERROR_CONTAINER,
    ON_SURFACE,
    ON_SURFACE_VARIANT,
    OUTLINE_VARIANT,
    PRIMARY,
    SURFACE_CONTAINER_LOWEST,
    SURFACE_CONTAINER_LOW,
    TERTIARY,
)
from ui.theme import action_button_style
from ui.widgets import AppButton


class LogHighlighter(QSyntaxHighlighter):
    """INAV-style highlighter for the curation log (themed to brand)."""

    def __init__(self, parent=None):
        super().__init__(parent)

        # Whole-line ERROR (uses brand error colour for foreground, light bg for legibility)
        self.error_format = QTextCharFormat()
        self.error_format.setForeground(QColor("#ffffff"))
        self.error_format.setBackground(QColor(ERROR))
        self.error_format.setFontWeight(QFont.Bold)

        # WARN: dark text on the brand's warm-error-container
        self.warn_format = QTextCharFormat()
        self.warn_format.setForeground(QColor(ON_ERROR_CONTAINER))
        self.warn_format.setBackground(QColor(ERROR_CONTAINER))
        self.warn_format.setFontWeight(QFont.Bold)

        # Detail colours — derived from brand accent steps (primary/tertiary family)
        self.ip_format = QTextCharFormat()
        self.ip_format.setForeground(QColor(PRIMARY))
        self.ip_format.setFontWeight(QFont.Bold)

        self.sql_format = QTextCharFormat()
        self.sql_format.setForeground(QColor(TERTIARY))
        self.sql_format.setFontWeight(QFont.Bold)

        self.xml_format = QTextCharFormat()
        self.xml_format.setForeground(QColor(ON_SURFACE_VARIANT))
        self.xml_format.setFontItalic(True)

        self.java_format = QTextCharFormat()
        self.java_format.setForeground(QColor("#a16207"))  # amber-700 — distinct from brand

        self.string_format = QTextCharFormat()
        self.string_format.setForeground(QColor("#15803d"))  # green-700 — "string" feel

        # SQL keywords (case-insensitive)
        self._sql_keywords = {
            "SELECT", "INSERT", "UPDATE", "DELETE", "FROM", "WHERE",
            "GROUP", "BY", "ORDER", "HAVING", "JOIN", "INNER", "LEFT", "RIGHT",
            "OUTER", "UNION", "CREATE", "ALTER", "DROP", "TRUNCATE",
            "AND", "OR", "NOT", "IN", "LIKE", "BETWEEN", "IS", "NULL",
            "AS", "ON", "LIMIT", "OFFSET", "VALUES", "SET", "TABLE", "INDEX",
        }

        # Cache for random identifier colours (deterministic per identifier)
        self._identifier_formats: dict[str, QTextCharFormat] = {}
        self._palette = [
            "#0e7490",  # cyan-700
            "#a16207",  # amber-700
            "#1d4ed8",  # blue-700
            "#7c3aed",  # violet-600
            "#be185d",  # pink-700
            "#0369a1",  # sky-700
            "#15803d",  # green-700
            "#b45309",  # amber-700 (darker)
            "#6d28d9",  # violet-700
            "#9d174d",  # pink-800
            "#155e75",  # cyan-800
            "#b91c1c",  # red-700
            "#166534",  # green-800
            "#92400e",  # amber-800
            "#1e40af",  # blue-800
        ]

        import re

        self._re_ip = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b|\b(?:[0-9a-fA-F]{0,4}:){2,7}[0-9a-fA-F]{0,4}\b")
        self._re_xml = re.compile(r"<[^>]+>")
        self._re_java = re.compile(r"\(.*\.java:\d+\)|\bat\s+[\w.$]+\(.*\.java:\d+\)")
        self._re_string = re.compile(r'"([^"\\]|\\.)*"|\'([^\'\\]|\\.)*\'')
        self._re_word = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")

    def _format_for_identifier(self, ident: str) -> QTextCharFormat:
        if ident in self._identifier_formats:
            return self._identifier_formats[ident]
        h = hash(ident)
        color = self._palette[h % len(self._palette)]
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        self._identifier_formats[ident] = fmt
        return fmt

    def highlightBlock(self, text: str) -> None:  # type: ignore[override]
        upper = text.upper()

        if "ERROR" in upper:
            self.setFormat(0, len(text), self.error_format)
        elif "WARN" in upper:
            self.setFormat(0, len(text), self.warn_format)

        for m in self._re_ip.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self.ip_format)

        for m in self._re_xml.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self.xml_format)

        for m in self._re_java.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self.java_format)

        string_spans = []
        for m in self._re_string.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self.string_format)
            string_spans.append((m.start(), m.end()))

        for m in self._re_word.finditer(text):
            word = m.group(0)
            if word.upper() in self._sql_keywords:
                inside_string = any(s <= m.start() < e for s, e in string_spans)
                if not inside_string:
                    self.setFormat(m.start(), m.end() - m.start(), self.sql_format)

        for m in self._re_word.finditer(text):
            word = m.group(0)
            if word.upper() in self._sql_keywords:
                continue
            if len(word) < 3:
                continue
            inside_string = any(s <= m.start() < e for s, e in string_spans)
            if inside_string:
                continue
            if word.upper() in {"ERROR", "WARN", "WARNING", "INFO", "DEBUG", "GET", "POST"}:
                continue
            self.setFormat(m.start(), m.end() - m.start(), self._format_for_identifier(word))


class LogPanel(QWidget):
    """Card strip shown/hidden under the top nav bar (no native title bar)."""

    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("LogCard")
        self.setStyleSheet(
            f"QWidget#LogCard {{ background: {SURFACE_CONTAINER_LOWEST}; "
            f"border-bottom: 1px solid {OUTLINE_VARIANT}; }}"
        )
        # Fixed strip height so open/close never reflows the page oddly.
        self.setFixedHeight(240)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(8)

        # White header bar: title + live toggle + clear + close.
        # Generous fixed heights + expanding spacer so nothing clips.
        header = QHBoxLayout()
        header.setSpacing(8)
        title = QLabel("Curation Log")
        title.setStyleSheet("font-size: 12px; font-weight: 600; color: #131b2e; background: transparent; border: none;")
        title.setSizePolicy(title.sizePolicy().horizontalPolicy(), title.sizePolicy().verticalPolicy())
        header.addWidget(title)
        header.addStretch(1)
        # NOTE: stateful Live toggle one-off (see ui/widgets.py) — not AppButton by design.
        self._live_btn = QPushButton("● Live")
        self._live_btn.setCheckable(True)
        self._live_btn.setChecked(True)
        self._live_btn.setCursor(Qt.PointingHandCursor)
        self._live_btn.setFixedHeight(26)
        self._live_btn.setMinimumWidth(80)
        self._live_btn.setToolTip("Follow new log lines as they arrive (click to pause)")
        self._live_btn.toggled.connect(self._on_live_toggled)
        self._style_live_btn()
        header.addWidget(self._live_btn)
        clear_btn = AppButton("Clear", kind="secondary", size="sm")
        clear_btn.setStyleSheet(action_button_style(False))
        clear_btn.setMinimumWidth(70)
        clear_btn.setToolTip("Clear the log buffer")
        clear_btn.clicked.connect(self._clear)
        header.addWidget(clear_btn)
        close_btn = AppButton("×", kind="ghost", size="sm")
        close_btn.setFixedSize(26, 26)
        close_btn.setToolTip("Hide the log (Ctrl+L to show again)")
        close_btn.clicked.connect(self._on_close)
        header.addWidget(close_btn)
        layout.addLayout(header)

        self._view = QPlainTextEdit()
        self._view.setReadOnly(True)
        font = QFont("Consolas")
        font.setStyleHint(QFont.Monospace)
        self._view.setFont(font)
        self._view.setPlaceholderText("Log will appear here as the app talks to Dataverse…")
        self._view.setStyleSheet(
            f"QPlainTextEdit {{ background: {SURFACE_CONTAINER_LOW}; color: {ON_SURFACE}; border: 1px solid {OUTLINE_VARIANT}; border-radius: 8px; padding: 6px 8px; font-family: 'JetBrains Mono', Consolas, monospace; font-size: 12px; }}"
        )
        self._highlighter = LogHighlighter(self._view.document())
        layout.addWidget(self._view, 1)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(800)
        self._last_len = 0

    def _on_close(self) -> None:
        self.hide()
        try:
            self.closed.emit()
        except Exception:
            pass

    def _style_live_btn(self) -> None:
        live = self._live_btn.isChecked()
        self._live_btn.setText("● Live" if live else "○ Paused")
        self._live_btn.setStyleSheet(
            "QPushButton { background: #dbe1ff; color: #00174c; border: 1px solid #c3c6d8; "
            "border-radius: 6px; padding: 0 8px; font-size: 10px; font-weight: 700; }"
            if live else
            "QPushButton { background: #ffffff; color: #57657a; border: 1px solid #c3c6d8; "
            "border-radius: 6px; padding: 0 8px; font-size: 10px; font-weight: 700; }"
        )

    def _on_live_toggled(self, checked: bool) -> None:
        self._style_live_btn()
        if checked:
            self._live_btn.setToolTip("Follow new log lines as they arrive (click to pause)")
            self._last_len = -1  # force a catch-up refresh
            if not self._timer.isActive():
                self._timer.start(800)
        else:
            self._live_btn.setToolTip("Paused — new lines are buffered (click to resume)")
            self._timer.stop()

    def _refresh(self) -> None:
        lines = applog.lines()
        if len(lines) != self._last_len:
            self._view.setPlainText("\n".join(lines) or "(log is empty)")
            if self._live_btn.isChecked():
                self._view.verticalScrollBar().setValue(self._view.verticalScrollBar().maximum())
            self._last_len = len(lines)
            self._live_btn.setToolTip(
                f"Follow new log lines as they arrive — {len(lines)} line(s) buffered (click to pause)"
            )

    def _clear(self) -> None:
        applog.clear()
        self._refresh()
