"""Shared Qt fixtures: one offscreen app + one MainWindow for the session.

Promoted from the probe scripts (probe33/34/35/40) so the critique-fix
contracts stay verified in `pytest`. Every test sets its own preconditions
on the shared window. Nothing here touches the network: dashboard reload,
settings reload, and detail loaders only run on explicit nav/save paths
the tests never call (detail loaders fire async and are never awaited).
"""

import os
import tempfile
from pathlib import Path
from typing import cast

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _platform_font_dir() -> str:
    """Return the platform's font directory, or "" when there is none.

    Qt 6 ships no fonts, so an offscreen run without this falls back to a
    substitute face and logs ``QFontDatabase: Cannot find font directory``.
    Tests assert geometry, and the warning gate fails on unclassified Qt
    messages (dv-bjj), so point Qt at the real fonts before the app exists.
    ``tools/probes/_common.py`` does the same for the probes.
    """
    if os.name == "nt":
        candidates = [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")]
    elif os.sys.platform == "darwin":  # type: ignore[attr-defined]
        candidates = ["/System/Library/Fonts", "/Library/Fonts"]
    else:
        candidates = ["/usr/share/fonts", "/usr/local/share/fonts"]
    for candidate in candidates:
        if os.path.isdir(candidate):
            return candidate
    return ""


if not os.environ.get("QT_QPA_FONTDIR"):
    _font_dir = _platform_font_dir()
    if _font_dir:
        os.environ["QT_QPA_FONTDIR"] = _font_dir


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    try:
        from ui.theme import apply_theme

        apply_theme(cast(QApplication, app))
    except Exception:
        pass
    return app


@pytest.fixture(autouse=True)
def _drain_events(qapp):
    """Drain posted events between tests.

    Enumerating ``topLevelWidgets()`` to hide leaked windows is no longer
    done: on Windows xdist workers that enumeration faulted (heap corruption
    0xc0000374) once enough wrappers had accumulated. Leaked windows are
    harmless now that the app stylesheet is palette-based and installed once.
    """
    yield
    qapp.processEvents()


@pytest.fixture
def gallery_without_app_theme(monkeypatch):
    """Build the gallery's two palettes without swapping the app stylesheet.

    ``GalleryWindow`` switches ``ACTIVE_THEME`` while it builds each
    column, and scoped sheets resolve through that. Replacing the
    application stylesheet as well would re-polish every live widget in
    the test process for a view the test is not checking (dv-gkt).
    """
    monkeypatch.setattr("ui.theme.apply_theme", lambda *a, **k: None)


@pytest.fixture(scope="session")
def win(qapp):
    from curation.config import Config
    from ui.main_window import MainWindow

    try:
        cfg = Config.load(None)
    except Exception:
        cfg = Config()
    # The session window must not read a developer's saved table layout or
    # local state: either can re-sort/replace rows mid-test (2026-11-25).
    cfg.app.workspace = Path(tempfile.mkdtemp(prefix="docent-ui-session-"))
    window = MainWindow(cfg)
    try:
        # A detail view constructed without cached metadata fires its load
        # on a 100 ms timer as soon as the event loop runs. Tests never
        # await that fetch; left live it hits the real configured instance
        # from the test process and can take it down with an access
        # violation mid-suite (seen as "Windows fatal exception" on the
        # CI runner). Keep the suite off the network.
        from ui.dataset import DatasetDetailView as _DetailView

        _DetailView._on_load_metadata = lambda self: None  # type: ignore[method-assign]
    except Exception:
        pass
    # Shown so layouts activate (geometry assertions in the status-bar
    # tests) — offscreen, so no real window appears.
    window.show()
    for _ in range(10):
        qapp.processEvents()
    yield window
    window.close()
    window.deleteLater()
    qapp.processEvents()
