"""Download approval dialog: shows quote before any bytes are fetched.

When the dataset declares a guestbook, the same window renders the fields
Dataverse requires before it will serve the bundle (name/email/institution/
position plus the guestbook's custom questions). The answers are POSTed with
the download; Dataverse then returns a signed URL for the ZIP.
"""

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from download_manager import DownloadQuote
from ui.theme import ERROR, WARNING_DARK, action_button_style
from ui.widgets import AppButton


def _human_size(n: int) -> str:
    """Human-readable size with B/KB/MB/GB/TB (shared with dashboard)."""
    try:
        n = int(n)
    except Exception:
        return str(n)
    if n < 1024:
        return f"{n} B"
    for unit in ("KB", "MB", "GB", "TB"):
        n /= 1024.0
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}"
    return f"{n:.1f} TB"


class DownloadApprovalDialog(QDialog):
    def __init__(
        self,
        quote: DownloadQuote,
        parent=None,
        guestbook: dict | None = None,
        account: dict | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Approve download")
        self.setMinimumWidth(480)
        self._guestbook = guestbook if isinstance(guestbook, dict) and guestbook else None
        self._account = account if isinstance(account, dict) else {}
        self._base_inputs: dict[str, QLineEdit] = {}
        self._base_specs: list[tuple[str, str, bool]] = []
        self._question_inputs: list[tuple[dict, QWidget]] = []
        self._error = QLabel("")
        layout = QVBoxLayout(self)
        msg = QLabel(
            f"This dataset contains <b>{quote.file_count}</b> file(s) "
            f"totalling <b>{_human_size(quote.total_size_bytes)}</b>.<br><br>"
            "No files have been downloaded yet. Approve to fetch the bundle?"
        )
        msg.setWordWrap(True)
        layout.addWidget(msg)
        if self._guestbook is not None:
            self._build_guestbook(layout)
        if quote.total_size_bytes > 5 * 1024**3:
            from ui.icons import icon_label as _warn_icon

            warn_row = QHBoxLayout()
            warn_row.setSpacing(8)
            try:
                warn_row.addWidget(_warn_icon("triangle-alert", size=16, color=WARNING_DARK))
            except Exception:
                pass
            warn = QLabel("Large dataset — download may take a while.")
            warn.setStyleSheet(f"color: {WARNING_DARK}; border: none; background: transparent;")
            warn_row.addWidget(warn, 1)
            layout.addLayout(warn_row)
        self._error.setWordWrap(True)
        self._error.setStyleSheet(
            f"color: {ERROR}; border: none; background: transparent;"
        )
        self._error.setVisible(False)
        layout.addWidget(self._error)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch(1)
        # Inline faces: app-level QSS demonstrably fails to paint button
        # backgrounds inside some QDialog subtrees, which leaves the white
        # primary text on a white dialog (invisible Download button).
        cancel_btn = AppButton("Cancel", kind="secondary")
        cancel_btn.setStyleSheet(action_button_style(False))
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(cancel_btn)
        download_btn = AppButton("Download", kind="primary")
        download_btn.setStyleSheet(action_button_style(True))
        download_btn.setDefault(True)
        download_btn.clicked.connect(self.accept)
        buttons.addWidget(download_btn)
        layout.addLayout(buttons)
        download_btn.setFocus()

    # -- guestbook form ----------------------------------------------------
    @staticmethod
    def _account_defaults(account: dict) -> dict[str, str]:
        name = " ".join(
            part
            for part in (
                str(account.get("firstName") or "").strip(),
                str(account.get("lastName") or "").strip(),
            )
            if part
        )
        return {
            "name": name or str(account.get("userName") or "").strip(),
            "email": str(account.get("email") or "").strip(),
            "institution": str(account.get("affiliation") or "").strip(),
            "position": str(account.get("position") or "").strip(),
        }

    def _build_guestbook(self, layout: QVBoxLayout) -> None:
        gb = self._guestbook or {}
        title = QLabel(
            f"<b>{gb.get('name') or 'Guestbook'}</b><br>"
            "This dataset asks for a guestbook response before download. "
            "Fields marked * are required (prefilled from your Dataverse "
            "account where available)."
        )
        title.setWordWrap(True)
        layout.addWidget(title)
        host = QWidget()
        form = QVBoxLayout(host)
        form.setContentsMargins(0, 4, 0, 4)
        form.setSpacing(8)
        defaults = self._account_defaults(self._account)
        for key, label, required in (
            ("name", "Name", gb.get("nameRequired")),
            ("email", "Email", gb.get("emailRequired")),
            ("institution", "Institution", gb.get("institutionRequired")),
            ("position", "Position", gb.get("positionRequired")),
        ):
            self._add_base_field(form, key, label, bool(required), defaults.get(key, ""))
        for question in gb.get("customQuestions") or []:
            if not isinstance(question, dict):
                continue
            self._add_question(form, question)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(host)
        scroll.setMinimumHeight(150)
        scroll.setMaximumHeight(340)
        layout.addWidget(scroll)

    def _add_base_field(
        self,
        form: QVBoxLayout,
        key: str,
        label: str,
        required: bool,
        prefill: str = "",
    ) -> None:
        caption = QLabel(f"{label}{' *' if required else ''}")
        form.addWidget(caption)
        edit = QLineEdit()
        edit.setPlaceholderText("From your Dataverse account")
        if prefill:
            edit.setText(prefill)
        caption.setBuddy(edit)
        form.addWidget(edit)
        self._base_inputs[key] = edit
        self._base_specs.append((key, label, required))

    def _add_question(self, form: QVBoxLayout, question: dict) -> None:
        label = str(question.get("question") or "Question")
        if question.get("required"):
            label += " *"
        caption = QLabel(label)
        caption.setWordWrap(True)
        form.addWidget(caption)
        qtype = str(question.get("type") or "text").lower()
        if qtype == "options":
            combo = QComboBox()
            combo.addItem("— Select —", "")
            for option in question.get("optionValues") or []:
                if isinstance(option, dict):
                    value = str(option.get("value") or "")
                    if value:
                        combo.addItem(value, value)
            form.addWidget(combo)
            widget: QWidget = combo
        elif qtype == "textarea":
            text = QPlainTextEdit()
            text.setFixedHeight(70)
            form.addWidget(text)
            widget = text
        else:
            edit = QLineEdit()
            form.addWidget(edit)
            widget = edit
        caption.setBuddy(widget)
        self._question_inputs.append((question, widget))

    @staticmethod
    def _value(widget: QWidget) -> str:
        if isinstance(widget, QComboBox):
            return str(widget.currentData() or "").strip()
        if isinstance(widget, QPlainTextEdit):
            return widget.toPlainText().strip()
        return widget.text().strip()  # type: ignore[attr-defined]

    def accept(self) -> None:
        if self._guestbook is not None:
            missing = [
                label
                for key, label, required in self._base_specs
                if required and not self._base_inputs[key].text().strip()
            ]
            missing += [
                str(q.get("question") or "Question")
                for q, widget in self._question_inputs
                if q.get("required") and not self._value(widget)
            ]
            if missing:
                self._error.setText(
                    "Please fill in the required guestbook field(s): "
                    + ", ".join(missing)
                )
                self._error.setVisible(True)
                return
        super().accept()

    def guestbook_response(self) -> dict | None:
        """Return the JSON body Dataverse expects inside ``guestbookResponse``."""
        if self._guestbook is None:
            return None
        response: dict = {}
        for key, edit in self._base_inputs.items():
            value = edit.text().strip()
            if value:
                response[key] = value
        answers = []
        for question, widget in self._question_inputs:
            value = self._value(widget)
            if not value:
                continue
            try:
                answers.append({"id": int(question.get("id")), "value": value})
            except (TypeError, ValueError):
                continue
        if answers:
            response["answers"] = answers
        return response
