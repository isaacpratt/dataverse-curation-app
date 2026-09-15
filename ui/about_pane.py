"""About pane: non-modal stack page describing the app (replaces the popup)."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ui.widgets import AppButton


def _app_version() -> str:
    try:
        from engine import __version__

        return str(__version__)
    except Exception:
        return "0.1.0"


class AboutPane(QWidget):
    """Short product overview with a Back button. Emits `discarded` on Back."""

    discarded = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: #faf8ff;")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(16)

        heading = QLabel("About")
        heading.setStyleSheet(
            "font-size: 22px; font-weight: 600; color: #131b2e; "
            "border: none; background: transparent;"
        )
        outer.addWidget(heading)

        card = QFrame()
        card.setObjectName("Card")
        card.setStyleSheet(
            "QFrame#Card { background: #ffffff; border: 1px solid #c3c6d8; border-radius: 12px; }"
        )
        body = QVBoxLayout(card)
        body.setContentsMargins(20, 20, 20, 20)
        body.setSpacing(10)

        title = QLabel(f"Dataverse Curation App <span style='color:#57657a'>v{_app_version()}</span>")
        title.setTextFormat(Qt.RichText)
        title.setStyleSheet(
            "font-size: 16px; font-weight: 600; color: #131b2e; "
            "border: none; background: transparent;"
        )
        title.setWordWrap(True)
        body.addWidget(title)

        blurb = QLabel(
            "Desktop assistant for curating Dataverse datasets: discover drafts, "
            "approve downloads, run format checks, verify metadata completeness, "
            "compare versions, and record decisions — all against the Dataverse "
            "Native/Search API with an API token. No direct database access; "
            "downloads, reports, and metadata caches live under your workspace."
        )
        blurb.setWordWrap(True)
        blurb.setStyleSheet(
            "font-size: 13px; color: #424656; border: none; background: transparent;"
        )
        body.addWidget(blurb)

        bullets = QLabel(
            "• Dashboard of datasets in review with status, label, and collection filters<br>"
            "• Per-file format checks (20 engines) plus dataset-level findings<br>"
            "• Metadata completeness profiles and published-vs-draft comparison<br>"
            "• Per-dataset timeline: versions, curation labels, local actions<br>"
            "• Headless mode: <span style='font-family:monospace'>python main.py --headless &lt;dir&gt;</span>"
        )
        bullets.setTextFormat(Qt.RichText)
        bullets.setWordWrap(True)
        bullets.setStyleSheet(
            "font-size: 13px; color: #424656; border: none; background: transparent;"
        )
        body.addWidget(bullets)

        try:
            from ui.theme import selectable_labels

            selectable_labels(card)
        except Exception:
            pass
        outer.addWidget(card)
        outer.addStretch(1)

        row = QHBoxLayout()
        row.setSpacing(8)
        back_btn = AppButton("× Close", kind="secondary")
        back_btn.clicked.connect(lambda: self.discarded.emit())
        row.addWidget(back_btn)
        row.addStretch(1)
        outer.addLayout(row)
