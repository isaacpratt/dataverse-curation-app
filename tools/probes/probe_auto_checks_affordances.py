"""Probe: the Auto-Checks card's affordances (dv-bph).

Offscreen, against a throwaway workspace (never the user's files).
Asserts that the card carries a findings filter, that the same skipped
check repeated across files collapses into one row carrying the count,
and that the filter narrows the card to one severity and restores it.

Run: python tools/probes/probe_auto_checks_affordances.py
"""

from __future__ import annotations

import sys

from _common import Report, boot


def _report():
    from engine.checks.base import CheckResult
    from engine.report import DatasetReport, FileEntry

    def skip():
        return CheckResult(
            check_id="format.spss",
            level="warning",
            passed=True,
            message="Optional library pyreadstat is not installed",
            details={"skipped": True},
        )

    return DatasetReport(
        persistent_id="doi:1",
        label="study",
        engine_version="t",
        dataset_checks=[
            CheckResult(
                check_id="metadata.license",
                level="warning",
                passed=True,
                message="ok",
                details={},
            ),
        ],
        files=[
            FileEntry(
                path=f"data/{n}.sav",
                size_bytes=10,
                mime_type="application/x-spss-sav",
                checks=[skip()],
            )
            for n in range(5)
        ]
        + [
            FileEntry(
                path="data/bad.xml",
                size_bytes=10,
                mime_type="application/xml",
                checks=[
                    CheckResult(
                        check_id="format.xml",
                        level="error",
                        passed=False,
                        message="malformed XML",
                        details={},
                    )
                ],
            )
        ],
    )


def _rows(view):
    """Return the Auto-Checks rows, in card order (the card body is a layout)."""
    out = []
    lay = view._auto_body
    for i in range(lay.count()):
        item = lay.itemAt(i)
        widget = item.widget() if item is not None else None
        if widget is not None and widget.objectName() == "AutoCheckRow":
            out.append(widget)
    return out


def _shown_kinds(view):
    return sorted(
        str(r.property("auto_class") or "?")
        for r in _rows(view)
        if not r.isHidden()
    )


def main() -> int:
    app, cfg = boot()

    import ui.dataset_detail as dd

    # The view fetches metadata on a timer; the probe only looks at rows.
    dd.DatasetDetailView._on_load_metadata = lambda self: None

    # The refresh's file list comes from the staged directory.
    staged = cfg.app.workspace / "downloads" / "doi_10.5072_FK2_AF" / "files"
    staged.mkdir(parents=True, exist_ok=True)
    for n in range(5):
        (staged / f"{n}.sav").write_bytes(b"")
    (staged / "bad.xml").write_bytes(b"<")

    report = Report("auto-checks affordances")
    view = dd.DatasetDetailView(
        cfg,
        "doi:10.5072/FK2/AF",
        "Auto-checks probe",
        cached_metadata={"id": 1},
        cached_inventory=[],
    )
    view._report = _report()
    view.show()
    for _ in range(6):
        app.processEvents()
    view._refresh_curation_preview()
    for _ in range(4):
        app.processEvents()

    combo = view._auto_filter
    report.check(combo is not None, "the card carries a findings filter")
    if combo is not None:
        report.check(combo.count() == 3, "the filter offers All / Errors / Warnings",
                     f"items={combo.count()}")
        report.check(bool(combo.toolTip()), "the filter explains itself")

    skipped = [r for r in _rows(view) if r.property("auto_class") == "skipped"]
    report.check(len(skipped) == 1, "five identical skipped rows collapse into one",
                 f"rows={len(skipped)}")
    errors = [r for r in _rows(view) if r.property("auto_class") == "failed-error"]
    report.check(len(errors) == 1, "the failed check keeps its own row",
                 f"rows={len(errors)}")

    before = len(_rows(view))
    if combo is not None:
        combo.setCurrentIndex(combo.findData("error"))
        for _ in range(4):
            app.processEvents()
        report.check(_shown_kinds(view) == ["failed-error"],
                     "the Errors filter narrows the card to the failed check",
                     f"shown={_shown_kinds(view)}")
        report.check(len(_rows(view)) == before, "filtering hides rows, it never drops them")

        combo.setCurrentIndex(combo.findData("warning"))
        for _ in range(4):
            app.processEvents()
        report.check(_shown_kinds(view) == ["skipped"],
                     "the Warnings filter keeps the skipped row",
                     f"shown={_shown_kinds(view)}")

        combo.setCurrentIndex(combo.findData("all"))
        for _ in range(4):
            app.processEvents()
        report.check(
            _shown_kinds(view) == ["failed-error", "passed", "skipped"],
            "the All filter restores every row",
            f"shown={_shown_kinds(view)}",
        )

    view.deleteLater()
    for _ in range(2):
        app.processEvents()
    return report.finish()


if __name__ == "__main__":
    sys.exit(main())
