"""Log dialog: shows all communication with the Dataverse server."""

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLineEdit,
    QTextEdit,
    QVBoxLayout,
)

import applog
from ui.theme import action_button_style
from ui.widgets import AppButton


class LogDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Dataverse communication log")
        self.resize(860, 560)
        layout = QVBoxLayout(self)

        search_row = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setObjectName("LogSearch")
        self._search.setPlaceholderText("Search log…")
        self._search.setClearButtonEnabled(True)
        self._search.setFixedHeight(32)
        self._search.setStyleSheet(
            "QLineEdit#LogSearch { background: #ffffff; border: 1px solid #c3c6d8; "
            "border-radius: 8px; padding-left: 10px; font-size: 13px; }"
            "QLineEdit#LogSearch:focus { border: 1px solid #004ccd; }"
        )
        self._search.textChanged.connect(self._refresh)
        search_row.addWidget(self._search, 1)
        layout.addLayout(search_row)

        self._view = QTextEdit()
        self._view.setReadOnly(True)
        font = QFont("Consolas")
        font.setStyleHint(QFont.Monospace)
        self._view.setFont(font)
        layout.addWidget(self._view, 1)

        btn_row = QHBoxLayout()
        refresh_btn = AppButton("Refresh", kind="secondary")
        refresh_btn.setStyleSheet(action_button_style(False))
        refresh_btn.clicked.connect(self._refresh)
        clear_btn = AppButton("Clear log", kind="secondary")
        clear_btn.setStyleSheet(action_button_style(False))
        clear_btn.clicked.connect(self._clear)
        btn_row.addWidget(refresh_btn)
        btn_row.addWidget(clear_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

        self._refresh()

    def _refresh(self) -> None:
        lines = applog.lines()
        try:
            needle = self._search.text().strip().lower()
        except Exception:
            needle = ""
        if needle:
            lines = [ln for ln in lines if needle in ln.lower()]
            text = "\n".join(lines) or "(no matching lines)"
        else:
            text = "\n".join(lines) or "(log is empty)"
        self._view.setPlainText(text)
        scrollbar = self._view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _clear(self) -> None:
        applog.clear()
        self._refresh()
