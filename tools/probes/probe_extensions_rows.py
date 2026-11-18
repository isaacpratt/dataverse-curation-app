"""Probe: the Settings -> Extensions table rows fit their buttons (dv-ub0).

Offscreen, against a throwaway workspace (never the user's table_layout.json).
Asserts that every row in the Extensions table is tall enough for its
buttons, and that the last row's bottom edge sits inside the table's
viewport — nothing is clipped by the table's own edge at 960x720.
"""

from __future__ import annotations

import sys

from _common import ROOT, Report, boot

sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QPushButton, QTabWidget

from ui.settings_dialog import SettingsPane


def main() -> int:
    app, cfg = boot()
    # Avoid the size worker touching the real environment.
    SettingsPane._start_size_worker = lambda self: None

    cfg.dataverse.base_url = "https://demo.borealisdata.ca"
    cfg.dataverse.api_token = ""
    cfg.dataverse.collection = "dv"
    cfg.app.tesseract = ""
    cfg.app.exiftool = ""

    report = Report("extensions rows")
    pane = SettingsPane(cfg)
    pane.resize(960, 720)
    # The Extensions page is built but hidden at construction; bring it forward.
    tabs = next(iter(pane.findChildren(QTabWidget)), None)
    if tabs is not None:
        tabs.setCurrentIndex(1)
    pane.show()
    for _ in range(10):
        app.processEvents()

    table = pane.ext_table
    report.check(table.rowCount() >= 3, "the Extensions table rendered its rows",
                 f"rows={table.rowCount()}")

    for row in range(table.rowCount()):
        cell = table.cellWidget(row, 5)
        buttons = cell.findChildren(QPushButton) if cell else []
        if not buttons:
            report.check(False, f"row {row} carries buttons", "cell missing")
            continue
        btn_h = max(b.sizeHint().height() for b in buttons)
        row_h = table.rowHeight(row)
        report.check(
            row_h >= btn_h + 12,
            f"row {row} fits its buttons",
            f"row={row_h} button={btn_h}",
        )

    last = table.rowCount() - 1
    bottom = table.rowViewportPosition(last) + table.rowHeight(last)
    report.check(
        bottom <= table.viewport().height(),
        "the last row is not clipped by the table's own edge",
        f"bottom={bottom} viewport={table.viewport().height()}",
    )
    pane.close()
    pane.deleteLater()
    return report.finish()


if __name__ == "__main__":
    sys.exit(main())
