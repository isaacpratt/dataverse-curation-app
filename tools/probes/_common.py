"""Shared bootstrap for the offscreen UI probes.

Every probe runs against a throwaway workspace: the probes must never
touch the user's ``table_layout.json`` (a probe that writes there leaves
the real app with a layout nobody chose).

The bootstrap also owns two things that are easy to get wrong and
expensive to miss:

* **Fonts.** Qt 6 no longer ships fonts, so an offscreen run without a
  font directory falls back to a substitute face and warns. Point Qt at the
  platform's own fonts before the QApplication exists: probes that assert
  geometry then measure the same metrics a user sees.
* **Warnings.** A Qt message is a defect until someone classifies it: a
  malformed widget stylesheet is dropped silently, so the page looks
  almost right (dv-bjj). Two messages come from the environment rather
  than the app and are allowed; anything else is recorded and fails the
  probe.
"""

from __future__ import annotations

import os
import pathlib
import re
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = pathlib.Path(__file__).resolve().parents[2]

ARTIFACT_DIR = ROOT / "reports" / "probes"

# The Qt messages that come from the platform, not from this app. Each one
# is documented in tools/probes/README.md; nothing else is allowed.
ALLOWED_MESSAGES = (
    # Offscreen QPA with no fontconfig: the platform plugin, not a widget.
    re.compile(r"^QFontDatabase: Cannot find font directory"),
    # The offscreen plugin cannot ask a window manager about a fixed size.
    re.compile(r"^This plugin does not support propagateSizeHints\(\)"),
)

_UNEXPECTED: list[str] = []
_ALLOWED: list[str] = []
_HANDLER: object | None = None
_PRINT_UNEXPECTED = True


def set_print_unexpected(enabled: bool) -> None:
    """Silence the stderr echo while a probe provokes a warning on purpose."""
    global _PRINT_UNEXPECTED
    _PRINT_UNEXPECTED = bool(enabled)


def _platform_font_dir() -> str:
    """Return the platform's font directory, or "" when there is none."""
    if sys.platform.startswith("win"):
        candidates = [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")]
    elif sys.platform == "darwin":
        candidates = ["/System/Library/Fonts", "/Library/Fonts"]
    else:
        candidates = ["/usr/share/fonts", "/usr/local/share/fonts"]
    for candidate in candidates:
        if os.path.isdir(candidate):
            return candidate
    return ""


def configure_fonts() -> str:
    """Point Qt at the platform's fonts before any QApplication exists."""
    if os.environ.get("QT_QPA_FONTDIR"):
        return os.environ["QT_QPA_FONTDIR"]
    path = _platform_font_dir()
    if path:
        os.environ["QT_QPA_FONTDIR"] = path
    return path


def is_allowed(message: str) -> bool:
    """Whether a Qt message is one of the classified platform messages."""
    return any(pattern.search(message) for pattern in ALLOWED_MESSAGES)


def _qt_message_handler(mode, context, message) -> None:  # pragma: no cover - Qt callback
    text = str(message)
    if is_allowed(text):
        _ALLOWED.append(text)
        return
    _UNEXPECTED.append(text)
    if _PRINT_UNEXPECTED:
        print(f"UNEXPECTED Qt message: {text}", file=sys.stderr)


def install_warning_gate() -> None:
    """Record every Qt message; allow the two platform ones (dv-bjj)."""
    global _HANDLER
    if _HANDLER is not None:
        return
    from PySide6.QtCore import qInstallMessageHandler

    _HANDLER = qInstallMessageHandler(_qt_message_handler)


def unexpected_messages() -> list[str]:
    """Qt messages this process emitted that nobody classified."""
    return list(_UNEXPECTED)


def allowed_messages() -> list[str]:
    """Qt messages this process emitted that are classified as platform noise."""
    return list(_ALLOWED)


def reset_messages() -> None:
    """Forget what the handler has seen (a probe that starts a fresh phase)."""
    _UNEXPECTED.clear()
    _ALLOWED.clear()


configure_fonts()


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
    configure_fonts()
    # Before the QApplication: the first stylesheet and the first font lookup
    # happen inside it.
    install_warning_gate()
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

    def check_no_unexpected_warnings(self) -> bool:
        """Fail on any Qt message the allowlist does not cover.

        A malformed stylesheet is dropped by Qt with only a warning, so the
        widget silently loses its face. This is the check that turns that
        into a red probe instead of a line in stderr.
        """
        unexpected = unexpected_messages()
        ok = self.check(
            not unexpected,
            "no unexpected Qt warnings",
            "" if not unexpected else f"{len(unexpected)} message(s)",
        )
        for message in unexpected:
            print(f"    - {message}")
        return ok

    def finish(self) -> int:
        self.check_no_unexpected_warnings()
        state = "OK" if not self.failures else f"{self.failures} FAILED"
        print(f"== {self.name}: {state}")
        return 0 if not self.failures else 1
