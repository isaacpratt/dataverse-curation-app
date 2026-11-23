"""Probe: finding-disposition rows (dv-32x).

The Auto-Checks finding rows carry an inline disposition combo and a
Note affordance; picking a disposition must persist to state.db, update
the roll-up suffix in the card header, and survive reopening the state.
The probe drives the real row factory with a throwaway workspace.

Run: python tools/probes/probe_disposition_rows.py
"""

from __future__ import annotations

import sys

from _common import Report, boot


def main() -> int:
    app, cfg = boot()
    from curation.storage import finding_key
    from ui.dataset import DatasetDetailView
    from ui.widgets import DISPOSITION_TOKENS, disposition_label

    report = Report("finding disposition rows")
    view = DatasetDetailView.__new__(DatasetDetailView)  # row factory only, no __init__
    view._pid = "doi:10.5072/FK2/PROBE"
    view._config = cfg
    view._dispositions_cache = {}
    key = finding_key("format.csv.pii", "a.csv", "2 emails found")
    view._finding_keys = [key]
    view._auto_summary_base = "12 passed · 1 warning"
    from PySide6.QtWidgets import QLabel

    view._auto_summary = QLabel()

    def _state():
        from curation.storage import open_state

        return open_state(cfg.app.workspace)

    def _log(action, notes="", details=None):
        view._logged = getattr(view, "_logged", [])
        view._logged.append((action, notes))

    view._state = _state
    view._log_action = _log

    key = finding_key("format.csv.pii", "a.csv", "2 emails found")
    row = view._auto_row(
        "format.csv.pii",
        "a.csv: 2 emails found",
        False,
        "warning",
        disposition_key=key,
    )
    report.check(row is not None, "the finding row built")

    from PySide6.QtWidgets import QComboBox, QPushButton

    combos = row.findChildren(QComboBox)
    report.check(len(combos) == 1, "the row carries one disposition combo")
    if combos:
        combo = combos[0]
        report.check(
            combo.count() == len(DISPOSITION_TOKENS),
            "the combo offers every disposition token",
        )
        report.check(combo.currentData() == "", "the combo starts unset")
        # Pick "Won't fix" through the real signal path.
        index = list(DISPOSITION_TOKENS).index("wontfix")
        combo.setCurrentIndex(index)
        for _ in range(5):
            app.processEvents()
        stored = view._dispositions_map().get(key, {})
        report.check(
            stored.get("disposition") == "wontfix",
            "picking a disposition persists to state.db",
            f"stored={stored}",
        )
        report.check(
            any(a == "disposition" for a, _n in getattr(view, "_logged", [])),
            "the change is logged as a curation action",
        )
        report.check(
            "1 of 1 findings resolved" in view._auto_summary.text(),
            "the header shows the resolved roll-up",
            view._auto_summary.text(),
        )
        # Reopen: a fresh state read must still see it (restart survival).
        del view._dispositions_cache  # drop the cache so the map reloads
        report.check(
            view._dispositions_map().get(key, {}).get("disposition") == "wontfix",
            "the disposition survives a fresh state read",
        )
        report.check(
            disposition_label("wontfix") == "Won't fix",
            "the kit labels the token",
        )
    from ui.i18n import t

    note_label = t("detail.disposition.note_action")
    overflow_buttons = [
        b for b in row.findChildren(QPushButton) if (b.accessibleName() or "").lower() == "copy"
    ]
    report.check(
        len(overflow_buttons) == 0,
        "the per-finding copy (ellipsis) action is gone (dv-gfx.8)",
    )
    note_buttons = [b for b in row.findChildren(QPushButton) if b.text() == note_label]
    report.check(
        len(note_buttons) == 1,
        "the row carries one Note affordance",
        f"buttons={[b.text() for b in row.findChildren(QPushButton)]!a}",
    )
    # A pass row carries no disposition controls.
    clean = view._auto_row("format.csv.content", "a.csv: parsed (utf-8)", True, "info")
    report.check(
        not clean.findChildren(QComboBox),
        "passed rows carry no disposition combo",
    )
    return report.finish()


if __name__ == "__main__":
    sys.exit(main())
