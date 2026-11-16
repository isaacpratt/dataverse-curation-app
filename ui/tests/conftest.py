"""Shared Qt fixtures: one offscreen app + one MainWindow for the session.

Promoted from the probe scripts (probe33/34/35/40) so the critique-fix
contracts stay verified in `pytest`. Every test sets its own preconditions
on the shared window. Nothing here touches the network: dashboard reload,
settings reload, and detail loaders only run on explicit nav/save paths
the tests never call (detail loaders fire async and are never awaited).
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    try:
        from ui.theme import apply_theme

        apply_theme(app)
    except Exception:
        pass
    yield app


@pytest.fixture(scope="session")
def win(qapp):
    from config import Config
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
        from ui.dataset_detail import DatasetDetailView as _DetailView

        _DetailView._on_load_metadata = lambda self: None
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
