"""Selectable message dialogs — replacement for QMessageBox with copyable text."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QTextEdit, QVBoxLayout


def _show(parent, title: str, text: str, icon: str = "") -> None:
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setMinimumSize(560, 220)
    layout = QVBoxLayout(dlg)

    if icon:
        header = QLabel(f"<b>{icon} {title}</b>")
        header.setTextFormat(Qt.RichText)
        layout.addWidget(header)

    # Selectable, word-wrapped label for short messages; QTextEdit for long/scrollable
    if len(text) < 800 and "\n" not in text:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        layout.addWidget(label)
    else:
        edit = QTextEdit()
        edit.setReadOnly(True)
        edit.setPlainText(text)
        edit.setMinimumHeight(160)
        layout.addWidget(edit, 1)

    buttons = QDialogButtonBox(QDialogButtonBox.Ok)
    buttons.accepted.connect(dlg.accept)
    layout.addWidget(buttons)
    dlg.exec()


def show_warning(parent, title: str, text: str) -> None:
    _show(parent, title, text, "⚠")


def show_critical(parent, title: str, text: str) -> None:
    _show(parent, title, text, "⛔")


def show_info(parent, title: str, text: str) -> None:
    _show(parent, title, text, "ℹ")
