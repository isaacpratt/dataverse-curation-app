"""Probe: the preview card renders at the 960px minimum width.

Boots a throwaway window at 960px holding the dv-koz preview card,
feeds it a CSV and a too-large file, and checks the card renders
without horizontal clipping (its full width fits the window) and
shows its content.

Run: python tools/probes/probe_preview.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from _common import Report, boot


def _stage_content(tmp: Path) -> tuple[Path, Path]:
    csv_path = tmp / "data.csv"
    csv_path.write_text(
        "region,count,reading\nnorth,12,3.5\nsouth,7,null\neast,18,2.25\n",
        encoding="utf-8",
    )
    big = tmp / "big.csv"
    big.write_bytes(b"a,b\n" + b"1,2\n" * (2 * 1024 * 1024))
    return csv_path, big


def main() -> int:
    app, _cfg = boot()
    from PySide6.QtWidgets import QMainWindow, QVBoxLayout, QWidget

    report = Report("preview card at 960px")
    tmp = Path(tempfile.mkdtemp(prefix="probe_preview_"))
    csv_path, big = _stage_content(tmp)

    from ui.preview import PreviewCard

    win = QMainWindow()
    win.resize(960, 800)
    host = QWidget()
    lay = QVBoxLayout(host)
    lay.setContentsMargins(0, 0, 0, 0)
    card = PreviewCard()
    lay.addWidget(card)
    win.setCentralWidget(host)
    win.show()
    for _ in range(10):
        app.processEvents()

    card.set_path(csv_path, rel="data.csv")
    for _ in range(6):
        app.processEvents()

    report.check(
        card.width() <= win.width(),
        "the preview card fits the 960px window",
        f"card={card.width()} window={win.width()}",
    )
    report.check(
        card._view.isVisible(),
        "the plain-text view carries the preview",
    )
    mono_text = card._view.toPlainText()
    report.check(
        "region" in mono_text and "north" in mono_text,
        "the CSV head renders inside the card",
    )
    report.check(
        card.minimumSizeHint().width() <= win.width(),
        "the card's minimum width fits 960px",
        f"min={card.minimumSizeHint().width()}",
    )

    card.set_path(
        big,
        rel="big.csv",
    )
    for _ in range(6):
        app.processEvents()
    report.check(card._open_btn.isVisible(), "too-large file offers the Open folder fallback")

    card.set_not_staged("missing.sav")
    for _ in range(4):
        app.processEvents()
    report.check(not card._note.isHidden(), "not-staged files explain themselves")

    win.close()
    return report.finish()


if __name__ == "__main__":
    sys.exit(main())
