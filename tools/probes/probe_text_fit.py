"""Probe: body-size labels must not clip after the 13px promotion.

`BodySM`, `CaptionSM` and `HintSM` moved from 12px to `FONT_BODY` (13px),
which touches roughly 60 call sites. This probe builds the busiest views
(dataset detail with populated check rows, Settings, Review configuration
and the gallery) at the 960px floor and at 1280px, then checks every
visible QLabel: unwrapped text must fit its width, wrapped text must fit
the height Qt computes for that width. `ElidedLabel` is exempt — it is the
kit's deliberate elide-with-tooltip control.

Run: python tools/probes/probe_text_fit.py
"""

from __future__ import annotations

import sys
from typing import Any

from _common import Report, boot


def _metadata() -> dict[str, Any]:
    def fv(value: str) -> dict[str, Any]:
        return {"typeName": "text", "multiple": False, "typeClass": "primitive", "value": value}

    return {
        "latestVersion": {
            "metadataBlocks": {
                "citation": {
                    "fields": [
                        {"typeName": "title", "value": "A curation study with a long title"},
                        {
                            "typeName": "author",
                            "value": [
                                {
                                    "authorName": fv("Ada Lovelace"),
                                    "authorAffiliation": fv("Analytical Engine Laboratory"),
                                },
                                {"authorName": fv("Grace Hopper")},
                            ],
                        },
                        {
                            "typeName": "datasetContact",
                            "value": [{"datasetContactName": fv("Ada Lovelace")}],
                        },
                        {"typeName": "dsDescription", "value": [{"dsDescriptionValue": fv("A study of persisted review state")}]},
                    ]
                }
            }
        }
    }


def _report() -> Any:
    from engine.checks.base import CheckResult
    from engine.report import DatasetReport, FileEntry

    def result(cid: str, level: str, passed: bool, msg: str) -> CheckResult:
        return CheckResult(check_id=cid, level=level, passed=passed, message=msg, details={})

    return DatasetReport(
        persistent_id="doi:10.5072/FK2/TEXTFIT",
        label="Text fit",
        engine_version="probe",
        dataset_checks=[
            result("inventory.extensions", "info", True, "3 files; .csv: 2, .txt: 1"),
            result(
                "inventory.unchecked_types",
                "warning",
                False,
                "2 files with no automated check (.bin) — manual review required",
            ),
        ],
        files=[
            FileEntry(
                path="data/a.csv",
                size_bytes=2048,
                mime_type="text/csv",
                checks=[result("format.csv.openable", "info", True, "openable")],
            )
        ],
    )


def _check_widget(app: Any, report: Report, widget: Any, tag: str) -> None:
    from PySide6.QtWidgets import QLabel

    from ui.widgets import ElidedLabel

    for _ in range(4):
        app.processEvents()

    bad: list[str] = []
    checked = 0
    for label in widget.findChildren(QLabel):
        if not label.isVisible() or isinstance(label, ElidedLabel):
            continue
        text = label.text()
        if not text:
            continue
        checked += 1
        if label.wordWrap():
            needed = label.heightForWidth(label.width())
            if needed > 0 and needed > label.height() + 1:
                bad.append(
                    f"{label.objectName() or 'QLabel'} wrapped {text[:36]!r}: "
                    f"needs {needed}px, has {label.height()}px"
                )
        elif label.sizeHint().width() > label.width() + 1:
            bad.append(
                f"{label.objectName() or 'QLabel'} {text[:36]!r}: "
                f"needs {label.sizeHint().width()}px, has {label.width()}px"
            )
    report.check(not bad, f"{tag}: no visible label clips", "; ".join(bad[:6]))
    report.check(checked > 0, f"{tag}: the check measured real labels", f"labels={checked}")


def _prove_the_detector(app: Any, report: Report) -> None:
    """A tiny label with long text must be flagged, or the gate is theatre."""
    from PySide6.QtWidgets import QLabel, QWidget

    host = QWidget()
    clipped = QLabel("A sentence far too long for thirty pixels of width", host)
    clipped.setWordWrap(False)
    clipped.resize(30, 20)
    host.show()
    for _ in range(3):
        app.processEvents()
    report.check(
        clipped.sizeHint().width() > clipped.width() + 1,
        "the fit detector notices a clipped label",
        f"needs={clipped.sizeHint().width()} has={clipped.width()}",
    )
    host.close()
    host.deleteLater()


def main() -> int:
    app, cfg = boot()
    report = Report("body-size text fit")
    _prove_the_detector(app, report)

    import ui.dataset as dd

    dd.DatasetDetailView._on_load_metadata = lambda self: None  # type: ignore[method-assign]
    view = dd.DatasetDetailView(
        cfg,
        "doi:10.5072/FK2/TEXTFIT",
        "Text fit probe",
        cached_metadata=_metadata(),
        cached_inventory=[],
    )
    view._report = _report()
    view._populate_completeness(view._metadata or {})
    view._refresh_curation_preview()

    from ui.settings_dialog import SettingsPane

    settings = SettingsPane(cfg)

    from ui.gallery import build_gallery

    gallery = build_gallery()

    from ui.main_window import MainWindow

    window = MainWindow(cfg)
    window._show_review_config()

    widgets = [
        ("dataset detail @960", view, 960, 800),
        ("dataset detail @1280", view, 1280, 900),
        ("settings @960", settings, 960, 800),
        ("review config @960", window, 960, 800),
        ("gallery @960", gallery, 960, 800),
    ]
    for tag, widget, width, height in widgets:
        widget.resize(width, height)
        widget.show()
        for _ in range(10):
            app.processEvents()
        _check_widget(app, report, widget, tag)
        widget.hide()

    gallery.close()
    gallery.deleteLater()
    settings.close()
    settings.deleteLater()
    view.close()
    view.deleteLater()
    window.close()
    window.deleteLater()
    return report.finish()


if __name__ == "__main__":
    sys.exit(main())
