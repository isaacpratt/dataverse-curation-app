"""Shared bootstrap for the offscreen UI probes.

Every probe runs against a throwaway workspace: the probes must never
touch the user's ``table_layout.json`` (a probe that writes there leaves
the real app with a layout nobody chose).
"""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = pathlib.Path(__file__).resolve().parents[2]
ARTIFACT_DIR = ROOT / "reports" / "probes"


def save_artifact(widget, name: str) -> pathlib.Path:
    """Save a widget screenshot under reports/probes/ and return its path."""
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    path = ARTIFACT_DIR / name
    widget.grab().save(str(path))
    return path


def boot():
    """Return (app, config) with the theme applied and a temp workspace."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from curation.config import Config
    from ui.theme import apply_theme

    apply_theme(app)
    try:
        cfg = Config.load(None)
    except Exception:
        cfg = Config()
    cfg.app.workspace = pathlib.Path(tempfile.mkdtemp(prefix="probe_ws_"))
    return app, cfg


class Report:
    """Tiny PASS/FAIL reporter (exit code 1 when a check fails)."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.failures = 0
        print(f"== {name}")

    def check(self, ok: bool, label: str, detail: str = "") -> bool:
        mark = "PASS" if ok else "FAIL"
        suffix = f"  {detail}" if detail else ""
        print(f"  [{mark}] {label}{suffix}")
        if not ok:
            self.failures += 1
        return bool(ok)

    def finish(self) -> int:
        state = "OK" if not self.failures else f"{self.failures} FAILED"
        print(f"== {self.name}: {state}")
        return 0 if not self.failures else 1
