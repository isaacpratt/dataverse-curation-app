"""Probe: the gallery's new input controls render whole (dv-6vv).

The gallery shows the kit's number field and value list. At 1440px the
probe checks the three things a curator would see: every stepper button is
a whole 32px square inside its field (no clipped native stepper), every
chip sits fully inside its wrapping flow (nothing pushed past the edge),
and the controls fit their section (the gallery never grows a horizontal
scrollbar). A screenshot of each half of the window goes to
reports/probes/ to eyeball.

Run: python tools/probes/probe_gallery_inputs.py
"""

from __future__ import annotations

import sys
from itertools import pairwise

from _common import Report, boot, save_artifact
from PySide6.QtWidgets import QPushButton, QScrollArea


def _chips_whole(flow) -> list:
    """Every chip whole inside the flow, one Lucide x each, no overlap."""
    problems = []
    chips = flow.chips()
    for chip in chips:
        if not flow.rect().contains(chip.geometry()):
            problems.append((chip.value, "outside the flow"))
        deletes = chip.findChildren(QPushButton)
        if len(deletes) != 1 or deletes[0].icon().isNull():
            problems.append((chip.value, "no Lucide x delete"))
    tops: dict = {}
    for chip in chips:
        tops.setdefault(round(chip.geometry().top()), []).append(chip)
    for _top, row in tops.items():
        ordered = sorted(row, key=lambda c: c.geometry().left())
        for a, b in pairwise(ordered):
            if a.geometry().right() > b.geometry().left():
                problems.append((a.value, "overlaps its neighbour"))
    return problems


def _stepper_problems(numbers) -> list:
    """Every way a number field could clip its stepper or its spin box."""
    clipped = []
    for field in numbers:
        host = field.rect()
        for btn in (field._down, field._up):
            if btn.width() != 32 or btn.height() != 32:
                clipped.append((field, "size", btn.width(), btn.height()))
            if not host.contains(btn.geometry()):
                clipped.append((field, "edge", btn.geometry()))
            if btn.icon().isNull():
                clipped.append((field, "icon", ""))
        spin = field._spin
        if not host.contains(spin.geometry()):
            clipped.append((field, "spin", spin.geometry()))
    return clipped


def _check_fit(report, window, controls) -> None:
    """No horizontal scrollbar, and every control inside its section."""
    for scroll in window.findChildren(QScrollArea):
        report.check(
            scroll.horizontalScrollBar().maximum() == 0,
            "the gallery never needs a horizontal scrollbar",
            f"need={scroll.horizontalScrollBar().maximum()}px",
        )
    for field in controls:
        host = field.parentWidget()
        if host is not None:
            report.check(
                field.width() <= host.width(),
                f"{type(field).__name__} fits its section width",
                f"control={field.width()}px section={host.width()}px",
            )


def main() -> int:
    app, _cfg = boot()
    from ui.gallery import build_gallery
    from ui.widgets import AppNumberField, AppValueList

    window = build_gallery()
    window.resize(1440, 900)
    window.show()
    for _ in range(10):
        app.processEvents()

    report = Report("gallery input controls")

    numbers = window.findChildren(AppNumberField)
    lists = window.findChildren(AppValueList)
    report.check(len(numbers) >= 3, "the gallery shows number fields", f"fields={len(numbers)}")
    report.check(len(lists) >= 2, "the gallery shows value lists", f"lists={len(lists)}")

    # No clipped stepper: each ghost button is a whole 32px square inside
    # its field, and the spin box between them is inside too.
    clipped = _stepper_problems(numbers)
    report.check(
        not clipped,
        "every stepper is a whole 32px button inside its field",
        f"clipped={clipped[:3]}",
    )

    # Chips: fully inside their flow, aligned on shared rows, one x each.
    chip_problems = []
    for value_list in lists:
        chip_problems.extend(_chips_whole(value_list._flow))
    report.check(
        not chip_problems,
        "every chip sits whole inside the flow with its own delete button",
        f"problems={chip_problems[:3]}",
    )

    _check_fit(report, window, numbers + lists)

    # Eyeball shots: the whole window scrolled to the new controls, and the
    # input section on its own.
    section = numbers[0].parentWidget()
    for scroll in window.findChildren(QScrollArea):
        scroll.ensureWidgetVisible(section)
    for _ in range(6):
        app.processEvents()
    path = save_artifact(window, "gallery_inputs_1440.png")
    print(f"  [note] screenshot: {path.name}")
    path = save_artifact(section, "gallery_inputs_section.png")
    print(f"  [note] screenshot: {path.name}")
    window.deleteLater()
    for _ in range(2):
        app.processEvents()
    return report.finish()


if __name__ == "__main__":
    sys.exit(main())
