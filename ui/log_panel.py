"""Live curation log strip — lives directly under the top nav bar.

Uses QPlainTextEdit with a custom QSyntaxHighlighter modelled on lnav: it
colours *text*, never a background. A line's severity tints its text (red
for ERROR / failing HTTP responses, amber for warnings) and individual
tokens get their own colour on top:

- timestamps muted, request methods amber
- the repository base URL brand blue, the API path/query indigo
- DOIs green, status codes by class (red 4xx/5xx, amber 3xx, green 2xx)
- quoted JSON keys muted and values in the line's severity colour

Manifest colours are pulled from ui.theme tokens so the log follows the
same brand palette as the rest of the app.
"""

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import (
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)

import applog
from ui.i18n import t
from ui.theme import (
    ACCENT_PRIMARY,
    ACCENT_PRIMARY_DEEP,
    ACCENT_TERTIARY,
    STATE_ERROR_GRAPHIC,
    STATE_WARNING_GRAPHIC,
    TEXT_AMBER,
    TEXT_DANGER,
    TEXT_MUTED,
    TEXT_SUBTLE,
    TEXT_SUCCESS,
)
from ui.widgets import (
    make_action_button,
    make_page_heading,
    make_plain_text_view,
    make_search_field,
    make_text_label,
)


class LogPage(QWidget):
    """Full-page log view — lives in the main stack alongside dashboard/detail."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("LogPage")
        layout = QVBoxLayout(self)
        # Same page padding as every other full-page view (MARGIN_PAGE).
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Shared page-heading contract (HeadlineLG theme token) — the title
        # sits on its own row like Settings/Review configuration/About, and
        # the controls live in the toolbar row below it.
        title, _subtitle = make_page_heading(t("log.title"))
        layout.addWidget(title)

        header = QHBoxLayout()
        header.setSpacing(8)
        # Severity legend: ordinary text, not badges (dv-wp1). Colour is
        # the only decoration - no uppercase, tracking, weight or pill -
        # so the row reads as the key it is, matching the lnav-style log
        # where severity lives in the words' colour alone.
        legend = QHBoxLayout()
        legend.setSpacing(14)
        for text, colour, tip in (
            (t("log.err_chip"), TEXT_DANGER, t("log.err_tip")),
            (t("log.warn_chip"), STATE_WARNING_GRAPHIC, t("log.warn_tip")),
            (t("log.expected_chip"), TEXT_MUTED, t("log.expected_tip")),
            (t("log.plain_chip"), TEXT_MUTED, t("log.plain_tip")),
        ):
            legend.addWidget(make_text_label(text, color=colour, tip=tip))
        header.addLayout(legend)
        header.addStretch(1)
        # Search box: filter visible lines (case-insensitive substring).
        # Standard search field — same 36px box + 13px text as the
        # dashboard/detail/review filters (was a bespoke 28px/12px box).
        self._search = make_search_field(t("log.search"), min_width=180)
        self._search.textChanged.connect(self._on_search_changed)
        header.addWidget(self._search)
        # Live toggle — standard secondary button, same face/height as the
        # Clear log + Refresh buttons beside it (was a bespoke 28px/10px box).
        self._live_btn = make_action_button(t("log.live"), kind="secondary")
        self._live_btn.setCheckable(True)
        self._live_btn.setChecked(True)
        self._live_btn.setToolTip(t("log.live_tip"))
        self._live_btn.toggled.connect(self._on_live_toggled)
        self._style_live_btn()
        header.addWidget(self._live_btn)
        clear_btn = make_action_button(t("log.clear"), kind="secondary")
        clear_btn.setToolTip(t("log.clear_tip"))
        clear_btn.setAccessibleName(t("log.clear_a11y"))
        clear_btn.clicked.connect(self._clear)
        header.addWidget(clear_btn)
        refresh_btn = make_action_button(t("log.refresh"), kind="secondary")
        refresh_btn.setToolTip(t("log.refresh_tip"))
        refresh_btn.setAccessibleName(t("log.refresh_a11y"))
        refresh_btn.clicked.connect(self._refresh)
        header.addWidget(refresh_btn)
        layout.addLayout(header)

        # The log body: the kit's read-only plain-text view (mono face, the
        # standard input chrome) - the highlighter paints the tokens.
        self._view = make_plain_text_view(t("log.placeholder"))
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
        """Sync the Live/Paused label + dot icon (face stays standard)."""
        from ui.icons import icon as _live_icon

        live = self._live_btn.isChecked()
        self._live_btn.setText(t("log.live") if live else t("log.paused"))
        try:
            self._live_btn.setIcon(
                _live_icon("circle-dot", color=ACCENT_PRIMARY_DEEP)
                if live else _live_icon("circle", color=TEXT_SUBTLE)
            )
        except Exception:
            pass

    def _on_live_toggled(self, checked: bool) -> None:
        self._style_live_btn()
        if checked:
            self._live_btn.setToolTip(t("log.live_tip"))
            self._last_len = -1  # force a catch-up refresh
            self._last_display = None
            if not self._timer.isActive():
                self._timer.start(800)
        else:
            self._live_btn.setToolTip(t("log.paused_tip"))
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
            display = "\n".join(lines) or t("log.no_match")
        else:
            display = "\n".join(lines) or t("log.empty")
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
                        t(
                            "log.matching_tip",
                            shown=len(lines),
                            total=total,
                            query=self._search.text().strip(),
                        )
                    )
                else:
                    self._live_btn.setToolTip(
                        t("log.buffered_tip", total=total)
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
    """lnav-style highlighter for the curation log (themed to brand).

    Severity colours the *text*, never a background band, and only the
    matched tokens get a colour — punctuation keeps the line's colour, so
    a failing response no longer draws boxes around colons, commas or
    escaped backslashes.
    """

    # Status codes after an arrow ("→ 403:") tint the number by class.
    _STATUS_RE = r"(?:→|->|=>)\s*(\d{3})\b"

    def __init__(self, parent=None):
        super().__init__(parent)

        def _format(color: str, *, bold: bool = False) -> QTextCharFormat:
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(color))
            if bold:
                fmt.setFontWeight(QFont.Bold)
            return fmt

        # Line severity: plain coloured text for the body, bold for the
        # severity word itself.
        self.line_error_format = _format(STATE_ERROR_GRAPHIC)
        self.line_warn_format = _format(STATE_WARNING_GRAPHIC)
        # An expected refusal is not a problem — it is the server's
        # documented answer, so it stays in the muted tone.
        self.line_expected_format = _format(TEXT_MUTED)
        self.error_format = _format(STATE_ERROR_GRAPHIC, bold=True)
        self.warn_format = _format(STATE_WARNING_GRAPHIC, bold=True)
        self.expected_format = _format(TEXT_MUTED, bold=True)
        self.info_format = _format(ACCENT_PRIMARY, bold=True)

        # Token colours.
        self.timestamp_format = _format(TEXT_SUBTLE)
        self.method_format = _format(TEXT_AMBER, bold=True)
        self.url_base_format = _format(ACCENT_PRIMARY, bold=True)
        self.url_path_format = _format(ACCENT_TERTIARY)
        self.doi_format = _format(TEXT_SUCCESS, bold=True)
        self.key_format = _format(TEXT_MUTED)
        self.value_format = _format(TEXT_SUCCESS)
        self.error_code_format = _format(STATE_ERROR_GRAPHIC, bold=True)
        self.warn_code_format = _format(STATE_WARNING_GRAPHIC, bold=True)
        self.expected_code_format = _format(TEXT_MUTED, bold=True)
        self.ok_code_format = _format(TEXT_SUCCESS, bold=True)

        import re

        self._regex = re
        self._re_time = re.compile(
            r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?"
        )
        self._re_level = re.compile(
            r"\b(CRITICAL|ERROR|WARN(?:ING)?|INFO|DEBUG|TRACE|EXPECTED)\b"
        )
        # The severity word the app wrote for this line, right after the
        # timestamp. A server body carries its own words (Dataverse says
        # "status":"ERROR" in every error response) — those must not
        # decide the line's colour.
        self._re_marker = re.compile(
            r"^(CRITICAL|ERROR|WARN(?:ING)?|INFO|DEBUG|TRACE|EXPECTED)\b"
        )
        # The marker that tags an expected refusal, wherever it sits in
        # the line (the app writes it at the start, and appends it to the
        # raw call line as the context).
        self._re_expected = re.compile(r"EXPECTED:")
        self._re_method = re.compile(
            r"\b(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\b(?=\s+\S)"
        )
        self._re_url_base = re.compile(r"\bhttps?://[^\s/\"'<>]+")
        self._re_status = re.compile(self._STATUS_RE)
        self._re_doi = re.compile(
            r"\bdoi:\s*10\.\d{4,9}/[^\s\"'<>,;)\]}]+", re.IGNORECASE
        )
        self._re_string = re.compile(r'"(?:[^"\\]|\\.)*"')

    def _severity(self, text: str) -> str | None:
        """Return "error", "warning", "expected" or None for a whole line.

        The app's own severity word decides: it is the first word of the
        message, after the timestamp. A response body may contain words
        of its own — Dataverse answers every error with
        ``{"status":"ERROR",...}`` — and those are the response, not the
        app's verdict.
        """
        body = text
        try:
            body = self._re_time.sub("", body, count=1).strip()
        except Exception:
            body = str(text or "").strip()
        marker = self._re_marker.match(body)
        if marker:
            word = marker.group(1).upper()
            if word == "EXPECTED":
                # The server's documented answer, not a failure.
                return "expected"
            if word in ("ERROR", "CRITICAL"):
                return "error"
            if word.startswith("WARN"):
                return "warning"
        if self._re_expected.search(str(text or "")):
            # The raw call line carries the appended context — it is the
            # same expected refusal, so it wears the same muted tone.
            return "expected"
        status = self._re_status.search(text)
        if status and int(status.group(1)) >= 400:
            return "error"
        return None

    def _apply(self, match, fmt: QTextCharFormat) -> None:
        length = match.end() - match.start()
        if length > 0:
            self.setFormat(match.start(), length, fmt)

    def highlightBlock(self, text: str) -> None:  # type: ignore[override]
        severity = self._severity(text)
        if severity == "error":
            self.setFormat(0, len(text), self.line_error_format)
        elif severity == "warning":
            self.setFormat(0, len(text), self.line_warn_format)
        elif severity == "expected":
            self.setFormat(0, len(text), self.line_expected_format)

        stamp = self._re_time.match(text)
        if stamp:
            self._apply(stamp, self.timestamp_format)

        for m in self._re_level.finditer(text):
            word = m.group(1).upper()
            if word in ("ERROR", "CRITICAL"):
                if severity == "expected":
                    # The server's own body says "status":"ERROR" — that
                    # is the response, not the app's verdict. Leave it in
                    # the muted tone of the line.
                    continue
                self._apply(m, self.error_format)
            elif word.startswith("WARN"):
                self._apply(m, self.warn_format)
            elif word == "EXPECTED":
                self._apply(m, self.expected_format)
            else:
                self._apply(m, self.info_format)

        for m in self._re_method.finditer(text):
            self._apply(m, self.method_format)

        # Base URL and the API path/query that follows it are two tones.
        url_spans: list[tuple[int, int]] = []
        for m in self._re_url_base.finditer(text):
            self._apply(m, self.url_base_format)
            stop = m.end()
            path = self._regex.match(r"/[^\s\"'<>]*", text[stop:])
            if path:
                stop += path.end()
                self.setFormat(m.end(), stop - m.end(), self.url_path_format)
            url_spans.append((m.start(), stop))

        for m in self._re_status.finditer(text):
            code = int(m.group(1))
            if severity == "expected":
                # The status is part of the raw call and response — it
                # stays visible, but it is not painted as a failure.
                fmt = self.expected_code_format
            else:
                fmt = (
                    self.error_code_format
                    if code >= 400
                    else (self.warn_code_format if code >= 300 else self.ok_code_format)
                )
            start = m.start(1)
            self.setFormat(start, m.end(1) - start, fmt)

        for m in self._re_doi.finditer(text):
            self._apply(m, self.doi_format)

        for m in self._re_string.finditer(text):
            if any(s <= m.start() < e for s, e in url_spans):
                continue
            # A string followed by a colon is a JSON key, not a value.
            if text[m.end():m.end() + 2].lstrip().startswith(":"):
                self._apply(m, self.key_format)
            elif severity == "error":
                self._apply(m, self.line_error_format)
            elif severity == "warning":
                self._apply(m, self.line_warn_format)
            else:
                self._apply(m, self.value_format)
