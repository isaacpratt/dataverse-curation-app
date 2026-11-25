"""Shared Qt fixtures: one offscreen app + one MainWindow for the session.

Promoted from the probe scripts (probe33/34/35/40) so the critique-fix
contracts stay verified in `pytest`. Every test sets its own preconditions
on the shared window. Nothing here touches the network: dashboard reload,
settings reload, and detail loaders only run on explicit nav/save paths
the tests never call (detail loaders fire async and are never awaited).
"""

import os
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


def pytest_addoption(parser):
    parser.addoption(
        "--update-golden",
        action="store_true",
        default=False,
        help="Bless the current golden candidates (dv-ufu.1, human only)",
    )
    parser.addoption(
        "--propose-golden",
        action="store_true",
        default=False,
        help="Render golden candidates without judging them",
    )


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
def _no_leaked_windows(qapp):
    """Take top-level windows a test left open out of the paint path.

    A widget built without a parent is a top-level window: left visible it
    stays for the rest of the session and keeps taking part in style
    recalculation and event delivery. That is not a correctness failure in
    the test that leaked, but it makes every *later* test slower - the
    gallery test measured 1.3 s alone and 80 s after a few hundred leaked
    windows.

    Deliberately non-destructive: hide and close, never delete. A leaked
    window may still be owned by a fixture that tears down after this one,
    or have a queued signal or background load still aimed at it, and
    forcing deletion here left the worker holding a dangling pointer (seen
    as a silent crash in test_lazy_startup). Hiding is idempotent and is
    enough to stop the cost.
    """
    from typing import cast

    from PySide6.QtWidgets import QApplication

    # instance() is typed as QCoreApplication | None; only QApplication has
    # topLevelWidgets().
    app = cast("QApplication | None", QApplication.instance())
    if app is None:
        yield
        return
    # Only windows that appear during the test are candidates: the session
    # ``win`` fixture is shown before the first test and must stay shown.
    before = set(app.topLevelWidgets())
    yield
    for widget in set(app.topLevelWidgets()) - before:
        try:
            widget.hide()
            widget.close()
        except Exception:
            pass
    qapp.processEvents()


@pytest.fixture(scope="session")
def win(qapp):
    from curation.config import Config
    from ui.main_window import MainWindow

    try:
        cfg = Config.load(None)
    except Exception:
        cfg = Config()
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
