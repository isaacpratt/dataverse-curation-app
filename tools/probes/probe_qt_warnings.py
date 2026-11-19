"""Qt messages are a gate, not noise (dv-bjj).

A malformed widget stylesheet is dropped by Qt with one warning and no
exception: the badge renders without its face and the page looks almost
right. This probe proves the gate is wired - the two classified platform
messages stay quiet, everything else is recorded and fails the run.

Run: python tools/probes/probe_qt_warnings.py
"""

from __future__ import annotations

from _common import (
    Report,
    allowed_messages,
    boot,
    install_warning_gate,
    is_allowed,
    reset_messages,
    set_print_unexpected,
    unexpected_messages,
)


def main() -> int:
    app, _cfg = boot()
    install_warning_gate()
    reset_messages()
    report = Report("Qt warnings are a gate")

    from PySide6.QtWidgets import QLabel, QWidget

    from ui.theme import label_badge_style
    from ui.widgets import make_badge

    # The classifier: the two platform messages are allowed, a dropped
    # stylesheet never is (that is the defect this bead fixed).
    report.check(
        is_allowed("This plugin does not support propagateSizeHints()"),
        "the offscreen plugin message is classified",
    )
    report.check(
        is_allowed("QFontDatabase: Cannot find font directory /nowhere"),
        "the missing-font message is classified",
    )
    report.check(
        not is_allowed("Could not parse stylesheet of object QLabel(0x0)"),
        "a dropped stylesheet is never classified",
    )

    # Trigger the one platform message this environment emits: the offscreen
    # plugin cannot honour a fixed-size request.
    fixed = QWidget()
    fixed.setFixedSize(320, 200)
    fixed.show()
    app.processEvents()

    # Prove the gate end to end: a deliberately broken sheet must be caught.
    # This is the failure class this bead fixed, so the probe demonstrates
    # that it would have failed. The stderr echo is muted for this one.
    set_print_unexpected(False)
    broken = QLabel("gate")
    broken.show()
    app.processEvents()
    broken.setStyleSheet("QLabel { color: red; } }")
    app.processEvents()
    report.check(
        any("Could not parse stylesheet" in message for message in unexpected_messages()),
        "the gate records a dropped stylesheet",
        f"{len(unexpected_messages())} message(s)",
    )
    broken.close()
    broken.deleteLater()
    reset_messages()
    set_print_unexpected(True)

    # The badge path that used to lose its face: label-driven sheet, then
    # re-dressed (the two named pills in the header do exactly this).
    badge = make_badge("Draft", label="draft")
    badge.setObjectName("PillDraft")
    badge.show()
    app.processEvents()
    badge.setText("In Review")
    badge.setObjectName("PillInReview")
    badge.show()
    app.processEvents()

    label = QLabel("A polished label")
    label.show()
    app.processEvents()

    sheet = label_badge_style("draft")
    report.check(
        sheet.count("{") == 1 and sheet.count("}") == 1,
        "the label badge sheet is one balanced rule",
        f"braces {sheet.count('{')}/{sheet.count('}')}",
    )

    seen = allowed_messages()
    report.check(
        all(is_allowed(message) for message in seen),
        "the recorded platform messages are all allowlisted",
        f"{len(seen)} allowed",
    )
    report.check(
        not unexpected_messages(),
        "no unexpected Qt messages",
        "" if not unexpected_messages() else f"{len(unexpected_messages())} message(s)",
    )

    for widget in (fixed, badge, label):
        widget.close()
    return report.finish()


if __name__ == "__main__":
    raise SystemExit(main())
