"""Probe: the About pane shows the Updates section and stays inside 960 px.

The updater is stubbed at the module boundary (no network, no velopack
import): one pass with the feed up-to-date, one pass with an update
already downloaded and pending a restart. Both pass must find the same
card, the same one button, and nothing that clips at 960 px wide. The
scene is captured to PNG for the release notes.

Run: python tools/probes/probe_about_updates.py
"""

from __future__ import annotations

import sys
import time

from _common import Report, boot, save_artifact


def _find_button_by_text(pane, text: str):
    from PySide6.QtWidgets import QPushButton

    return [b for b in pane.findChildren(QPushButton) if b.text() == text]


def _visible_labels(pane):
    from PySide6.QtWidgets import QLabel

    return [lbl.text() for lbl in pane.findChildren(QLabel) if lbl.text()]


def _right_most_edge(pane) -> float:
    """Right edge of every visible widget inside the pane (px)."""
    from PySide6.QtWidgets import QWidget

    edges = [
        (w.geometry().x() + w.width()) for w in pane.findChildren(QWidget) if w.isVisibleTo(pane)
    ]
    return max(edges, default=0.0)


def _seed_pending_pref(pane, cfg, version: str) -> None:
    from pathlib import Path

    from curation.storage import write_ui_pref

    write_ui_pref(Path(cfg.app.workspace), "update_pending_version", version)
    write_ui_pref(Path(cfg.app.workspace), "update_check_last", int(time.time()))


def main() -> int:
    app, cfg = boot()
    report = Report("about pane: updates section")

    from pathlib import Path

    import ui.updater as updater
    from ui.about_pane import AboutPane

    # The pane asks the update module for UI prefs; point every read/write at
    # the throwaway workspace (never the user's ui_prefs.json).
    updater._resolve_workspace = lambda ws: Path(cfg.app.workspace)

    # No feed reachable, nothing pending, but the check clock is fresh:
    # the pane shows the up-to-date state with the action button.
    updater.make_update_manager = lambda: None
    pane = AboutPane()
    pane.resize(960, pane.sizeHint().height() or 700)
    pane.show()
    for _ in range(10):
        app.processEvents()

    report.check("Updates" in " ".join(_visible_labels(pane)), "the Updates heading renders")
    report.check(
        bool(_find_button_by_text(pane, "Check for updates")),
        "the Check for updates button is present",
    )
    report.check(
        not _find_button_by_text(pane, "Restart and install v0.2.0"),
        "the restart action is hidden before an install is downloaded",
    )
    edge = _right_most_edge(pane)
    report.check(edge <= 960, "nothing clipped at 960 px wide", f"rightmost {edge:.0f} px")

    save_artifact(pane, "about-updates-fresh.png")

    # Second pass: an update is already downloaded and pending a restart.
    _seed_pending_pref(pane, cfg, "0.2.0")
    pane2 = AboutPane()
    pane2.resize(960, pane2.sizeHint().height() or 700)
    pane2.show()
    for _ in range(10):
        app.processEvents()

    labels = " ".join(_visible_labels(pane2))
    report.check("0.2.0" in labels, "the pending version is shown")
    report.check(
        bool(_find_button_by_text(pane2, "Restart and install v0.2.0")),
        "the Restart and install action appears",
    )
    edge2 = _right_most_edge(pane2)
    report.check(
        edge2 <= 960, "nothing clipped at 960 px wide (pending state)", f"rightmost {edge2:.0f} px"
    )

    save_artifact(pane2, "about-updates-pending.png")
    pane.close()
    pane2.close()
    return report.finish()


if __name__ == "__main__":
    sys.exit(main())
