"""Log dialog: shows all communication with the Dataverse server."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
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

        self._view = QTextEdit()
        self._view.setReadOnly(True)
        font = QFont("Consolas")
        font.setStyleHint(QFont.Monospace)
        self._view.setFont(font)
        layout.addWidget(self._view, 1)

        btn_row = QHBoxLayout()
        refresh_btn = AppButton("Refresh", kind="secondary", size="sm")
        refresh_btn.setStyleSheet(action_button_style(False))
        refresh_btn.clicked.connect(self._refresh)
        clear_btn = AppButton("Clear log", kind="secondary", size="sm")
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
        self._view.setPlainText("\n".join(lines) or "(log is empty)")
        scrollbar = self._view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _clear(self) -> None:
        applog.clear()
        self._refresh()
