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

from curation.download_manager import DownloadQuote
from ui.i18n import t
from ui.theme import TEXT_WARNING
from ui.widgets import (
    make_action_button,
    make_combo,
    make_line_edit,
    make_multiline_input,
)


def _human_size(n: int) -> str:
    # Re-exported from the shared helper (dv-005): labels are decimal (KB/MB).
    from ui.widgets import human_size as _shared

    return _shared(n)


class DownloadApprovalDialog(QDialog):
    def __init__(
        self,
        quote: DownloadQuote,
        parent=None,
        guestbook: dict | None = None,
        account: dict | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(t("download.title"))
        self.setMinimumWidth(480)
        self._guestbook = guestbook if isinstance(guestbook, dict) and guestbook else None
        self._account = account if isinstance(account, dict) else {}
        self._base_inputs: dict[str, QLineEdit] = {}
        self._base_specs: list[tuple[str, str, bool]] = []
        self._question_inputs: list[tuple[dict, QWidget]] = []
        self._error = QLabel("")
        layout = QVBoxLayout(self)
        msg = QLabel(
            t(
                "download.summary",
                count=quote.file_count,
                size=_human_size(quote.total_size_bytes),
            )
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
                warn_row.addWidget(_warn_icon("triangle-alert", size=16, color=TEXT_WARNING))
            except Exception:
                pass
            warn = QLabel(t("download.large_warning"))
            warn.setObjectName("WarningSM")
            warn_row.addWidget(warn, 1)
            layout.addLayout(warn_row)
        self._error.setWordWrap(True)
        self._error.setObjectName("DangerSM")
        self._error.setVisible(False)
        layout.addWidget(self._error)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch(1)
        # Inline faces: app-level QSS demonstrably fails to paint button
        # backgrounds inside some QDialog subtrees, which leaves the white
        # primary text on a white dialog (invisible Download button).
        cancel_btn = make_action_button(t("common.cancel"), kind="secondary")
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(cancel_btn)
        download_btn = make_action_button(t("download.button"), kind="primary")
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
            f"<b>{gb.get('name') or t('download.guestbook_default_name')}</b><br>"
            f"{t('download.guestbook_intro')}"
        )
        title.setWordWrap(True)
        layout.addWidget(title)
        host = QWidget()
        form = QVBoxLayout(host)
        form.setContentsMargins(0, 4, 0, 4)
        form.setSpacing(8)
        defaults = self._account_defaults(self._account)
        for key, label, required in (
            ("name", t("download.field_name"), gb.get("nameRequired")),
            ("email", t("download.field_email"), gb.get("emailRequired")),
            ("institution", t("download.field_institution"), gb.get("institutionRequired")),
            ("position", t("download.field_position"), gb.get("positionRequired")),
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
        caption = QLabel(f"{label}{t('download.required_marker') if required else ''}")
        form.addWidget(caption)
        edit = make_line_edit(t("download.account_placeholder"))
        if prefill:
            edit.setText(prefill)
        caption.setBuddy(edit)
        form.addWidget(edit)
        self._base_inputs[key] = edit
        self._base_specs.append((key, label, required))

    def _add_question(self, form: QVBoxLayout, question: dict) -> None:
        label = str(question.get("question") or t("download.question_fallback"))
        if question.get("required"):
            label += t("download.required_marker")
        caption = QLabel(label)
        caption.setWordWrap(True)
        form.addWidget(caption)
        qtype = str(question.get("type") or "text").lower()
        if qtype == "options":
            options = [(t("download.select_placeholder"), "")]
            for option in question.get("optionValues") or []:
                if isinstance(option, dict):
                    value = str(option.get("value") or "")
                    if value:
                        options.append((value, value))
            combo = make_combo(options)
            form.addWidget(combo)
            widget: QWidget = combo
        elif qtype == "textarea":
            text = make_multiline_input(plain=True, height=70)
            form.addWidget(text)
            widget = text
        else:
            edit = make_line_edit()
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
                str(q.get("question") or t("download.question_fallback"))
                for q, widget in self._question_inputs
                if q.get("required") and not self._value(widget)
            ]
            if missing:
                self._error.setText(t("download.missing_fields", fields=", ".join(missing)))
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
