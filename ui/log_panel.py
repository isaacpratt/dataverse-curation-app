"""Live curation log strip — lives directly under the top nav bar.

Uses QPlainTextEdit with a custom QSyntaxHighlighter that colours:
- ERROR lines red, WARNING/WARN lines yellow
- IP addresses, SQL keywords, XML tags, Java backtrace file:line, quoted strings
- Random consistent colours for identifiers (INAV-style)

Colour palette pulled from ui.theme tokens so the log follows the same brand
palette as the rest of the app while staying deliberately distinct (high
contrast, dark-on-light backgrounds for ERROR/WARN rows).
"""

import hashlib

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import applog
from ui.theme import (
    AMBER_700,
    ERROR,
    ERROR_CONTAINER,
    LOG_IDENTIFIER_PALETTE,
    ON_ERROR,
    ON_ERROR_CONTAINER,
    ON_SECONDARY_CONTAINER,
    ON_SURFACE,
    ON_SURFACE_VARIANT,
    OUTLINE_VARIANT,
    PRIMARY,
    PRIMARY_DEEP,
    PRIMARY_FIXED,
    SUCCESS_DARK,
    SURFACE_CONTAINER_LOW,
    SURFACE_CONTAINER_LOWEST,
    TERTIARY,
    action_button_style,
)
from ui.widgets import AppButton


class LogPage(QWidget):
    """Full-page log view — lives in the main stack alongside dashboard/detail."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("LogPage")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(8)
        title = QLabel("Dataverse Communication Log")
        title.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {ON_SURFACE}; background: transparent; border: none;")
        header.addWidget(title)
        header.addStretch(1)
        # Search box: filter visible lines (case-insensitive substring).
        self._search = QLineEdit()
        self._search.setObjectName("LogSearch")
        self._search.setPlaceholderText("Search log…")
        self._search.setClearButtonEnabled(True)
        self._search.setFixedHeight(28)
        self._search.setMinimumWidth(180)
        self._search.setStyleSheet(
            f"QLineEdit#LogSearch {{ background: {SURFACE_CONTAINER_LOWEST}; border: 1px solid {OUTLINE_VARIANT}; "
            "border-radius: 8px; padding-left: 10px; font-size: 12px; }"
            f"QLineEdit#LogSearch:focus {{ border: 1px solid {PRIMARY}; }}"
        )
        self._search.textChanged.connect(self._on_search_changed)
        header.addWidget(self._search)
        # Live toggle
        self._live_btn = QPushButton("Live")
        self._live_btn.setCheckable(True)
        self._live_btn.setChecked(True)
        self._live_btn.setCursor(Qt.PointingHandCursor)
        self._live_btn.setFixedHeight(28)
        self._live_btn.setMinimumWidth(90)
        self._live_btn.setToolTip("Follow new log lines as they arrive (click to pause)")
        self._live_btn.toggled.connect(self._on_live_toggled)
        self._style_live_btn()
        header.addWidget(self._live_btn)
        clear_btn = AppButton("Clear log", kind="secondary")
        clear_btn.setStyleSheet(action_button_style(False))
        clear_btn.setToolTip("Clear the log buffer")
        clear_btn.setAccessibleName("Clear log buffer")
        clear_btn.clicked.connect(self._clear)
        header.addWidget(clear_btn)
        refresh_btn = AppButton("Refresh", kind="secondary")
        refresh_btn.setStyleSheet(action_button_style(False))
        refresh_btn.setToolTip("Refresh log now")
        refresh_btn.setAccessibleName("Refresh log now")
        refresh_btn.clicked.connect(self._refresh)
        header.addWidget(refresh_btn)
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
        # Debounce search: re-filter at most every 200 ms (matches dashboard).
        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(200)
        self._search_debounce.timeout.connect(self._refresh)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Only poll while visible — a permanent QStackedWidget child would
        # otherwise re-join the full log every 800 ms forever.
        try:
            if self._live_btn.isChecked() and not self._timer.isActive():
                self._timer.start(800)
        except Exception:
            pass

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        try:
            self._timer.stop()
        except Exception:
            pass

    def _style_live_btn(self) -> None:
        from ui.icons import icon as _live_icon

        live = self._live_btn.isChecked()
        self._live_btn.setText("Live" if live else "Paused")
        try:
            self._live_btn.setIcon(
                _live_icon("circle-dot", color=PRIMARY_DEEP)
                if live else _live_icon("circle", color=ON_SECONDARY_CONTAINER)
            )
        except Exception:
            pass
        self._live_btn.setStyleSheet(
            f"QPushButton {{ background: {PRIMARY_FIXED}; color: {PRIMARY_DEEP}; border: 1px solid {OUTLINE_VARIANT}; "
            "border-radius: 8px; padding: 0 8px; font-size: 10px; font-weight: 700; }"
            if live else
            f"QPushButton {{ background: {SURFACE_CONTAINER_LOWEST}; color: {ON_SECONDARY_CONTAINER}; border: 1px solid {OUTLINE_VARIANT}; "
            "border-radius: 8px; padding: 0 8px; font-size: 10px; font-weight: 700; }"
        )

    def _on_live_toggled(self, checked: bool) -> None:
        self._style_live_btn()
        if checked:
            self._live_btn.setToolTip("Follow new log lines as they arrive (click to pause)")
            self._last_len = -1  # force a catch-up refresh
            self._last_display = None
            if not self._timer.isActive():
                self._timer.start(800)
        else:
            self._live_btn.setToolTip("Paused — new lines are buffered (click to resume)")
            self._timer.stop()

    def _refresh(self) -> None:
        lines = applog.lines()
        needle = ""
        try:
            needle = self._search.text().strip().lower()
        except Exception:
            pass
        if needle:
            lines = [ln for ln in lines if needle in ln.lower()]
            display = "\n".join(lines) or "(no matching lines)"
        else:
            display = "\n".join(lines) or "(log is empty)"
        # Length alone no longer tracks the buffer when filtering — compare text.
        if display != getattr(self, "_last_display", None) or len(lines) != self._last_len:
            self._view.setPlainText(display)
            if self._live_btn.isChecked() and not needle:
                self._view.verticalScrollBar().setValue(self._view.verticalScrollBar().maximum())
            self._last_len = len(lines)
            self._last_display = display
            try:
                total = len(applog.lines())
                if needle:
                    self._live_btn.setToolTip(
                        f"Showing {len(lines)} of {total} line(s) matching “{self._search.text().strip()}”"
                    )
                else:
                    self._live_btn.setToolTip(
                        f"Follow new log lines as they arrive — {total} line(s) buffered (click to pause)"
                    )
            except Exception:
                pass

    def _on_search_changed(self, _text: str) -> None:
        self._last_display = None
        # Debounce: typing "error" would otherwise re-join the full buffer
        # five times; match the 200 ms pattern used by dashboard/review.
        if hasattr(self, "_search_debounce"):
            self._search_debounce.start()
        else:
            self._refresh()

    def _clear(self) -> None:
        applog.clear()
        self._refresh()


class LogHighlighter(QSyntaxHighlighter):
    """INAV-style highlighter for the curation log (themed to brand)."""

    def __init__(self, parent=None):
        super().__init__(parent)

        # Whole-line ERROR (uses brand error colour for foreground, light bg for legibility)
        self.error_format = QTextCharFormat()
        self.error_format.setForeground(QColor(ON_ERROR))
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
        self.java_format.setForeground(QColor(AMBER_700))  # amber-700 — distinct from brand

        self.string_format = QTextCharFormat()
        self.string_format.setForeground(QColor(SUCCESS_DARK))  # green-700 — "string" feel

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
        self._palette = list(LOG_IDENTIFIER_PALETTE)

        import re

        self._re_ip = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b|\b(?:[0-9a-fA-F]{0,4}:){2,7}[0-9a-fA-F]{0,4}\b")
        self._re_xml = re.compile(r"<[^>]+>")
        self._re_java = re.compile(r"\(.*\.java:\d+\)|\bat\s+[\w.$]+\(.*\.java:\d+\)")
        self._re_string = re.compile(r'"([^"\\]|\\.)*"|\'([^\'\\]|\\.)*\'')
        self._re_word = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")

    def _format_for_identifier(self, ident: str) -> QTextCharFormat:
        if ident in self._identifier_formats:
            return self._identifier_formats[ident]
        h = int.from_bytes(hashlib.md5(ident.encode("utf-8")).digest()[:4], "big")
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

