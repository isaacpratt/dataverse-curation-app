"""Selectable message dialogs — replacement for QMessageBox with copyable text."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QTextEdit, QVBoxLayout

from ui.theme import ERROR, PRIMARY, WARNING

_ICON_COLORS = {
    "triangle-alert": WARNING,
    "octagon-x": ERROR,
    "info": PRIMARY,
}

# Plain-language rewrites for the failures workers actually raise. Matched
# against the whole worker message (exception + traceback), case-insensitive.
_NETWORK_HINTS = (
    (
        ("max retries exceeded", "failed to establish a new connection",
         "name or service not known", "getaddrinfo", "network is unreachable",
         "temporary failure in name resolution", "connection refused",
         "connectionreset", "connection aborted"),
        "Could not reach the Dataverse server. Check your network connection or "
        "the Base URL in Settings (Ctrl+,), then try again.",
    ),
    (
        ("timed out", "timeout"),
        "The Dataverse server did not respond in time. It may be busy — try again "
        "in a moment.",
    ),
    (
        ("401", "403", "unauthorized", "forbidden", "invalid api token",
         "api token", "authentication"),
        "Dataverse rejected the request — the API token may be missing, expired, or "
        "lacking access. Update it in Settings (Ctrl+,), then try again.",
    ),
    (
        ("404", "not found", "no route to host"),
        "The Dataverse URL or collection looks wrong (404). Check the Base URL and "
        "collection alias in Settings (Ctrl+,).",
    ),
    (
        ("ssl", "certificate", "handshake"),
        "The secure connection to the Dataverse failed (certificate/SSL error). "
        "Check the Base URL, or ask IT about the server certificate.",
    ),
)


def describe_error(msg: str) -> tuple[str, str]:
    """Split a raw worker error into (plain-language headline, technical details).

    Workers emit ``str(exc) + traceback``; users need the problem and the fix,
    the traceback stays copyable underneath for bug reports.
    """
    raw = (msg or "").strip()
    low = raw.lower()
    for needles, headline in _NETWORK_HINTS:
        if any(n in low for n in needles):
            return headline, raw
    first_line = raw.splitlines()[0].strip() if raw else ""
    if not first_line:
        return "Something went wrong. The technical details are below.", raw
    if len(first_line) > 200:
        first_line = first_line[:197] + "..."
    return first_line, raw


def _show(
    parent,
    title: str,
    text: str,
    icon: str = "",
    details: str = "",
    retry=None,
) -> None:
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

    state = {"retry": False}
    buttons = QDialogButtonBox(QDialogButtonBox.Ok)
    if retry is not None:
        buttons.addButton(QDialogButtonBox.Retry)
    buttons.accepted.connect(dlg.accept)
    if retry is not None:
        retry_btn = buttons.button(QDialogButtonBox.Retry)

        def _on_click(btn, _rb=retry_btn) -> None:
            if btn is _rb:
                state["retry"] = True
                dlg.accept()

        buttons.clicked.connect(_on_click)
    layout.addWidget(buttons)
    dlg.exec()
    if state["retry"] and retry is not None:
        retry()


def show_warning(parent, title: str, text: str, details: str = "", retry=None) -> None:
    _show(parent, title, text, "triangle-alert", details, retry)


def show_critical(parent, title: str, text: str, details: str = "", retry=None) -> None:
    _show(parent, title, text, "octagon-x", details, retry)


def show_info(parent, title: str, text: str, details: str = "", retry=None) -> None:
    _show(parent, title, text, "info", details, retry)


def confirm(parent, title: str, text: str, *, confirm_label: str = "Delete") -> bool:
    """Yes/No confirmation for destructive actions. Defaults to No."""
    from PySide6.QtWidgets import QHBoxLayout

    from ui.icons import icon_label as _dlg_icon

    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setMinimumWidth(460)
    layout = QVBoxLayout(dlg)
    try:
        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        header_row.addWidget(_dlg_icon("triangle-alert", size=18, color=WARNING))
        header = QLabel(f"<b>{title}</b>")
        header.setTextFormat(Qt.RichText)
        header_row.addWidget(header, 1)
        layout.addLayout(header_row)
    except Exception:
        pass
    label = QLabel(text)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
    layout.addWidget(label)
    buttons = QDialogButtonBox()
    no_btn = buttons.addButton(QDialogButtonBox.No)
    yes_btn = buttons.addButton(confirm_label, QDialogButtonBox.ButtonRole.AcceptRole)
    no_btn.setDefault(True)
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    layout.addWidget(buttons)
    yes_btn.setAutoDefault(True)
    no_btn.setAutoDefault(True)
    return dlg.exec() == QDialog.DialogCode.Accepted
