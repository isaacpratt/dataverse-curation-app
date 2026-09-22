"""Selectable message dialogs — replacement for QMessageBox with copyable text."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QTextEdit, QVBoxLayout


_ICON_COLORS = {
    "triangle-alert": "#d97706",
    "octagon-x": "#ba1a1a",
    "info": "#004ccd",
}


def _show(parent, title: str, text: str, icon: str = "", details: str = "") -> None:
    from PySide6.QtWidgets import QHBoxLayout

    from ui.icons import icon_label as _dlg_icon

    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setMinimumSize(560, 220)
    layout = QVBoxLayout(dlg)

    if icon:
        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        try:
            header_row.addWidget(
                _dlg_icon(icon, size=18, color=_ICON_COLORS.get(icon))
            )
        except Exception:
            pass
        header = QLabel(f"<b>{title}</b>")
        header.setTextFormat(Qt.RichText)
        header_row.addWidget(header, 1)
        layout.addLayout(header_row)

    # User-actionable message first; technical details collapsible below.
    if len(text) < 800 and "\n" not in text:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        layout.addWidget(label)
    else:
        edit = QTextEdit()
        edit.setReadOnly(True)
        edit.setPlainText(text)
        edit.setMinimumHeight(120 if details else 160)
        layout.addWidget(edit, 1)
    if details:
        det = QTextEdit()
        det.setReadOnly(True)
        det.setPlainText(details)
        det.setMinimumHeight(120)
        det.setPlaceholderText("Technical details")
        layout.addWidget(det, 1)

    buttons = QDialogButtonBox(QDialogButtonBox.Ok)
    buttons.accepted.connect(dlg.accept)
    layout.addWidget(buttons)
    dlg.exec()


def show_warning(parent, title: str, text: str, details: str = "") -> None:
    _show(parent, title, text, "triangle-alert", details)


def show_critical(parent, title: str, text: str, details: str = "") -> None:
    _show(parent, title, text, "octagon-x", details)


def show_info(parent, title: str, text: str, details: str = "") -> None:
    _show(parent, title, text, "info", details)
