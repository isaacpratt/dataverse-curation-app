"""Probe: the entry-check params form fits at 1440 and 960 (dv-5nd).

Opens a rule with every parameter set and checks the rendered form: labels
one line, both stepper buttons whole and visible, chips aligned, nothing
clipped at the Response pane's right edge. Screenshots at both widths go
to reports/probes/.

Run: python tools/probes/probe_review_params.py
"""

from __future__ import annotations

import sys

from _common import Report, boot, save_artifact


def _panel(page, qapp):
    from PySide6.QtWidgets import QSplitter

    rs = page._current_ruleset()
    original = rs.get("field_rules")
    rs["field_rules"] = [
        {
            "block": "citation",
            "field": "alternativeUrl",
            "label": "Alternative URL",
            "level": "required",
            "handler": "looks_correct",
            "params": {
                "min_length": 25,
                "regex": "^10\\.\\d+/\\S+$",
                "regex_mode": "full",
                "blocklist": ["todo", "placeholder", "lorem ipsum"],
                "controlled_vocabulary": ["doi", "url"],
                "not_common_placeholders": True,
                "not_all_caps": True,
                "date": True,
                "date_order": True,
                "url": True,
            },
        }
    ]
    page._refresh_field_table()
    page._sel_kind = "field"
    page._sel_key = page._rule_sel_key("citation", "alternativeUrl", "looks_correct")
    page._show_template_for_selection()
    for _ in range(8):
        qapp.processEvents()
    splitter = next(s for s in page.findChildren(QSplitter))
    return splitter.widget(1), original


def main() -> int:
    app, cfg = boot()
    from PySide6.QtWidgets import QLabel, QSpinBox

    from ui.review_config import ReviewConfigView
    from ui.widgets import AppNumberField, AppValueList

    report = Report("review entry-check params")
    page = ReviewConfigView(cfg)
    page.resize(1440, 900)
    page.show()
    pane, original = _panel(page, app)
    panel = page._params_panel
    report.check(not panel.isHidden(), "the params panel is shown")

    labels = [
        label for label in panel.findChildren(QLabel) if label.objectName() == "LabelStrongSM"
    ]
    wrapped = [
        (label.text(), label.width())
        for label in labels
        if label.fontMetrics().horizontalAdvance(label.text()) > label.width()
    ]
    report.check(not wrapped, "every label fits on one line", f"wrapped={wrapped}")

    stepper = page._p_min
    report.check(isinstance(stepper, AppNumberField), "the min field is the kit number field")
    buttons = [stepper._down, stepper._up]
    report.check(
        all(b.width() == 32 and b.height() == 32 and not b.isHidden() for b in buttons),
        "both Lucide stepper buttons are whole and visible",
    )

    for name, field in (("blocked", page._p_blocklist), ("allowed", page._p_vocab)):
        report.check(isinstance(field, AppValueList), f"{name} phrases use the chip field")
        tops = {chip.geometry().top() for chip in field._flow.chips()}
        report.check(
            len(tops) <= 2,
            f"{name} chips are aligned (no stray row)",
            f"rows={len(tops)}",
        )

    raw = [
        spin
        for spin in panel.findChildren(QSpinBox)
        if not isinstance(spin.parentWidget(), AppNumberField)
    ]
    report.check(not raw, "no raw spin box is built in the panel")

    problems = []
    for width, height in ((1440, 900), (960, 720)):
        page.resize(width, height)
        for _ in range(10):
            app.processEvents()
        report.check(
            pane.horizontalScrollBar().maximum() == 0,
            f"no horizontal scrollbar at {width}x{height}",
        )
        right = pane.viewport().mapToGlobal(pane.viewport().rect().topRight()).x()
        clipped = []
        for control in (
            page._p_min,
            page._p_regex,
            page._p_regex_full,
            page._p_blocklist,
            page._p_vocab,
        ):
            if control.mapToGlobal(control.rect().topRight()).x() > right + 1:
                clipped.append(type(control).__name__)
        problems.extend((width, name) for name in clipped)
        path = save_artifact(pane, f"review_params_{width}x{height}.png")
        print(f"  [note] screenshot: {path.name}")
    report.check(not problems, "no control clips at either width", f"clipped={problems}")

    # Restore the ruleset before closing the shared page.
    page._current_ruleset()["field_rules"] = original
    page.deleteLater()
    for _ in range(2):
        app.processEvents()
    return report.finish()


if __name__ == "__main__":
    sys.exit(main())
