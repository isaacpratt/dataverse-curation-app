"""Probe: the Metadata card renders its rows (dv-h70 follow-ups).

Builds a real DatasetDetailView on a temp workspace with a canned
citation block and checks the Auto-Checks-style rows: the Title row
renders, the required bar is present, the author drawer expands and
collapses, the Not-checked filter shows its ghost rows, and the card
carries no inner scrollbars (the page scrolls, the card never does).

Run: python tools/probes/probe_metadata_rows.py
"""

from __future__ import annotations

import sys

from _common import Report, boot


def _fv(value):
    return {"typeName": "text", "multiple": False, "typeClass": "primitive", "value": value}


def _metadata() -> dict:
    return {
        "latestVersion": {
            "license": {"name": "CC0 1.0"},
            "metadataBlocks": {
                "citation": {
                    "fields": [
                        {"typeName": "title", "value": "A study"},
                        {
                            "typeName": "author",
                            "value": [
                                {
                                    "authorName": _fv("Ada Lovelace"),
                                    "authorAffiliation": _fv("Analytical Engine Lab"),
                                    "authorIdentifierScheme": _fv("ORCID"),
                                    "authorIdentifier": _fv("0000-0002-1825-0097"),
                                },
                                {
                                    "authorName": _fv("Grace Hopper"),
                                    "authorAffiliation": _fv(""),
                                },
                            ],
                        },
                        {
                            "typeName": "datasetContact",
                            "value": [
                                {"datasetContactName": _fv("Ada Lovelace")},
                            ],
                        },
                        {
                            "typeName": "dsDescription",
                            "value": [
                                {
                                    "dsDescriptionValue": _fv("Desc."),
                                    "dsDescriptionDate": _fv("2026-01-01"),
                                },
                            ],
                        },
                        {"typeName": "subject", "value": ["Computer and Information Science"]},
                        {"typeName": "depositor", "value": "Ada Lovelace"},
                        {"typeName": "dateOfDeposit", "value": "2026-01-02"},
                    ]
                }
            },
        }
    }


def _rows(view):
    out = []
    lay = view._meta_body_lay
    for i in range(lay.count()):
        widget = lay.itemAt(i).widget()
        if widget is not None and widget.property("meta_field") is not None:
            out.append(widget)
    return out


def _row(view, label):
    for widget in _rows(view):
        if widget.property("meta_field") == label:
            return widget
    return None


def _drawer(view, row):
    lay = view._meta_body_lay
    for i in range(lay.count() - 1):
        if lay.itemAt(i).widget() is row:
            candidate = lay.itemAt(i + 1).widget()
            if candidate is not None and candidate.property("meta_field") is None:
                return candidate
    return None


def main() -> int:
    app, cfg = boot()
    from PySide6.QtWidgets import QFrame, QScrollArea, QScrollBar, QToolButton

    import ui.dataset as dd

    # The view fetches metadata on a timer; the probe only looks at rows.
    dd.DatasetDetailView._on_load_metadata = lambda self: None

    report = Report("metadata rows")
    view = dd.DatasetDetailView(
        cfg,
        "doi:10.5072/FK2/META",
        "Metadata probe",
        cached_metadata=_metadata(),
        cached_inventory=[],
    )
    for _ in range(6):
        app.processEvents()

    rows = _rows(view)
    report.check(len(rows) >= 3, "the Metadata card renders its rows", f"rows={len(rows)}")

    title_row = _row(view, "Title")
    report.check(title_row is not None, "the Title row exists")
    bars = title_row.findChildren(QFrame, "MetaRequiredBar") if title_row is not None else []
    report.check(
        len(bars) == 0,
        "no required bar is painted (dv-onk)",
        f"bars={len(bars)}",
    )
    if title_row is not None:
        report.check(
            "Required" in (title_row.toolTip() or ""),
            "the level wording rides the row tooltip (dv-onk)",
            f"tip={title_row.toolTip()!r}",
        )

    # Compound field: the author drawer expands and collapses.
    author_row = _row(view, "Author Name & Affiliation")
    drawer = _drawer(view, author_row) if author_row is not None else None
    report.check(
        drawer is not None,
        "a compound field carries an inline drawer",
    )
    if drawer is not None:
        hidden_before = drawer.isHidden()
        chevron = next(iter(author_row.findChildren(QToolButton)), None)
        report.check(chevron is not None, "the compound row carries a chevron")
        if chevron is not None:
            chevron.click()
            for _ in range(4):
                app.processEvents()
            report.check(not drawer.isHidden(), "the drawer expands")
            chevron.click()
            for _ in range(4):
                app.processEvents()
            report.check(drawer.isHidden(), "the drawer collapses")
        report.check(hidden_before, "the drawer starts closed")

    # Not-checked filter: ghost rows appear, tagged Not checked.
    view._unchecked_results = [
        {
            "rule_id": "field:citation.title",
            "kind": "field",
            "field": "Title",
            "requirement": "off by ruleset",
            "value": "-",
            "status": "skipped",
            "level": "unchecked",
            "pending": False,
            "response_template": "",
            "block": "citation",
            "name": "title",
        }
    ]
    unchecked_idx = view._meta_filter.findData("unchecked")
    report.check(unchecked_idx >= 0, "the filter offers Not checked")
    if unchecked_idx >= 0:
        view._meta_filter.setCurrentIndex(unchecked_idx)
        for _ in range(4):
            app.processEvents()
        ghost = _rows(view)
        labels = [str(w.property("meta_field")) for w in ghost]
        report.check(
            labels == ["Title"], "the Not-checked filter renders the ghost row", f"rows={labels}"
        )
        view._meta_filter.setCurrentIndex(view._meta_filter.findData("all"))
        for _ in range(4):
            app.processEvents()
        restored = _rows(view)
        report.check(len(restored) >= 3, "the All filter restores the rows")

    # The card carries no inner scrollbars: the page scrolls, the card never
    # does. (The combos' popup views own hidden internal scrollbars; what
    # matters is none of them is visible.)
    card = view._meta_card
    inner_areas = card.findChildren(QScrollArea)
    visible_bars = [b for b in card.findChildren(QScrollBar) if b.isVisible()]
    report.check(not inner_areas, "the metadata card hosts no inner scroll area")
    report.check(
        not visible_bars,
        "the metadata card hosts no visible inner scrollbar",
        f"visible={len(visible_bars)}",
    )

    view.deleteLater()
    for _ in range(2):
        app.processEvents()
    return report.finish()


if __name__ == "__main__":
    sys.exit(main())
