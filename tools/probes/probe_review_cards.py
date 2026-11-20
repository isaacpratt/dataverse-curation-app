"""Probe: the two Review configuration cards fit at 1440 and 960 (dv-gcn).

The left pane holds Metadata Field Rules above Content-based Rules, 16px
apart, with one scrollbar on the pane and no clipped controls. Screenshots
of the left pane at both widths go to reports/probes/.

Run: python tools/probes/probe_review_cards.py
"""

from __future__ import annotations

import sys

from _common import Report, boot, save_artifact
from PySide6.QtWidgets import QLabel, QScrollArea


def card_of(widget):
    node = widget
    while node is not None and node.objectName() != "Card":
        node = node.parentWidget()
    return node


def pane_of(widget):
    node = widget
    while node is not None and not isinstance(node, QScrollArea):
        node = node.parentWidget()
    return node


def main() -> int:
    app, cfg = boot()
    from ui.review_config import ReviewConfigView

    report = Report("review rule cards")
    page = ReviewConfigView(cfg)
    page.show()
    for _ in range(8):
        app.processEvents()

    field_card = card_of(page._field_tree)
    content_card = card_of(page._content_list)
    report.check(
        field_card is not None and content_card is not None and field_card is not content_card,
        "the field table and content rules live in separate cards",
    )
    titles = [
        label.text()
        for card in (field_card, content_card)
        for label in card.findChildren(QLabel, "CardTitle")
    ]
    report.check(
        titles == ["Metadata Field Rules", "Content-based Rules"],
        "both cards are titled in order",
        f"titles={titles}",
    )
    host = field_card.parentWidget() if field_card else None
    order = [host.layout().itemAt(i).widget() for i in range(host.layout().count())] if host else []
    report.check(
        order[:2] == [field_card, content_card],
        "the cards are siblings in the pane's host",
    )
    if host is not None:
        report.check(
            host.layout().spacing() == 16,
            "the cards are 16px apart",
            f"spacing={host.layout().spacing()}",
        )

    problems = []
    for width, height in ((1440, 900), (960, 720)):
        page.resize(width, height)
        for _ in range(10):
            app.processEvents()
        left = pane_of(field_card)
        if left is None:
            problems.append((width, "no left scroll pane"))
            continue
        report.check(
            left.horizontalScrollBar().maximum() == 0,
            f"no horizontal scrollbar at {width}x{height}",
            f"need={left.horizontalScrollBar().maximum()}",
        )
        tree = page._field_tree
        report.check(tree.height() > 0, f"the field table keeps its height at {width}")
        report.check(
            tree.verticalScrollBar().maximum() == 0,
            f"the field table still fits its card at {width}",
        )
        for card in (field_card, content_card):
            if card is not None and card.width() > left.viewport().width():
                problems.append((width, f"card {card.width()} in {left.viewport().width()}"))
        path = save_artifact(left, f"review_cards_{width}x{height}.png")
        print(f"  [note] screenshot: {path.name}")
    report.check(not problems, "both cards fit the pane at both widths", f"problems={problems}")
    page.deleteLater()
    for _ in range(2):
        app.processEvents()
    return report.finish()


if __name__ == "__main__":
    sys.exit(main())
