"""Download approval dialog: shows quote before any bytes are fetched."""

from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QVBoxLayout

from download_manager import DownloadQuote
from ui.theme import action_button_style
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
    def __init__(self, quote: DownloadQuote, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Approve download")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        msg = QLabel(
            f"This dataset contains <b>{quote.file_count}</b> file(s) "
            f"totalling <b>{_human_size(quote.total_size_bytes)}</b>.<br><br>"
            "No files have been downloaded yet. Approve to fetch the bundle?"
        )
        msg.setWordWrap(True)
        layout.addWidget(msg)
        if quote.total_size_bytes > 5 * 1024**3:
            from ui.icons import icon_label as _warn_icon

            warn_row = QHBoxLayout()
            warn_row.setSpacing(8)
            try:
                warn_row.addWidget(_warn_icon("triangle-alert", size=16, color="#b45309"))
            except Exception:
                pass
            warn = QLabel("Large dataset — download may take a while.")
            warn.setStyleSheet("color: #b45309; border: none; background: transparent;")
            warn_row.addWidget(warn, 1)
            layout.addLayout(warn_row)
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
