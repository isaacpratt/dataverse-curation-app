"""Golden screenshot gate (dv-ufu.1).

Deselected by default: run with ``QT_QPA_PLATFORM=windows pytest -m goldens``.
``--propose-golden`` writes candidate images without judging them;
``--update-golden`` is the human-only bless operation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ui.tests.golden import (
    BASELINE_DIR,
    bless,
    capture,
    check_environment,
    compare,
    golden_boot,
    write_meta,
)

pytestmark = pytest.mark.goldens

SEED_ROWS = [
    {
        "persistent_id": "doi:10.5072/FK2/AAA",
        "title": "Alpha study",
        "state": "DRAFT",
        "curation_label": "Awaiting review",
        "contact": "Ada Lovelace",
        "collection": "science",
        "file_count": 3,
        "total_size_bytes": 4096,
    },
    {
        "persistent_id": "doi:10.5072/FK2/BBB",
        "title": "Beta dataset",
        "state": "IN REVIEW",
        "curation_label": "Approve",
        "contact": "Grace Hopper",
        "collection": "science",
        "file_count": 1,
        "total_size_bytes": 1024,
    },
]

METADATA = {
    "id": 42,
    "latestVersion": {
        "versionState": "DRAFT",
        "metadataBlocks": {
            "citation": {
                "fields": [
                    {"typeName": "title", "value": "Alpha study"},
                    {
                        "typeName": "datasetContact",
                        "value": [
                            {
                                "datasetContactName": {"value": "Ada Lovelace"},
                                "datasetContactEmail": {"value": "ada@example.org"},
                            }
                        ],
                    },
                ]
            }
        },
    },
}

INVENTORY = [
    {"path": "data.csv", "size_bytes": 128, "file_id": 1, "storageIdentifier": "file://x"},
    {"path": "notes.txt", "size_bytes": 64, "file_id": 2, "storageIdentifier": "file://y"},
]

CASES = (
    "dashboard-empty",
    "dashboard-seeded",
    "settings",
    "about",
    "log",
    "review-config",
    "gallery",
    "detail-seeded",
    "kit-states",
)


@pytest.fixture(scope="session")
def golden_session(qapp: Any) -> Any:
    import shutil
    import tempfile

    import ui.dialogs as dialogs
    from ui.dataset import DatasetDetailView

    # Never let a detail view start a real metadata fetch from a golden,
    # and never let a dirty Settings pane open a modal during a case switch.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(DatasetDetailView, "_on_load_metadata", lambda self: None)
        for name in (
            "show_critical",
            "show_warning",
            "show_info",
            "confirm",
            "confirm_save_discard_cancel",
        ):
            patch.setattr(dialogs, name, lambda *_a, **_k: True)
        # A fixed path keeps the rendered workspace string byte-identical
        # across runs; only baselines use this directory, never the app.
        workspace = Path(tempfile.gettempdir()) / "docent-golden-workspace"
        shutil.rmtree(workspace, ignore_errors=True)
        workspace.mkdir(parents=True, exist_ok=True)
        session = golden_boot(workspace)
        yield session
        shutil.rmtree(workspace, ignore_errors=True)


def _build(session: Any, name: str) -> Any:
    win = session.window
    win._show_pane(None)  # stable starting state for every case
    if name in ("dashboard-empty", "dashboard-seeded"):
        rows = [] if name == "dashboard-empty" else list(SEED_ROWS)
        win._dashboard._all_datasets = rows
        win._dashboard._apply_filter()
        win._stack.setCurrentWidget(win._dashboard)
        return win
    if name in ("settings", "about", "log"):
        win._show_pane(name)
        return win
    if name == "review-config":
        win._show_pane(None)
        win._show_review_config()
        return win
    if name == "gallery":
        from ui.gallery import build_gallery

        return build_gallery()
    if name == "detail-seeded":
        from ui.dataset import DatasetDetailView

        detail = DatasetDetailView(
            win._config,
            "doi:10.5072/FK2/AAA",
            "Alpha study",
            cached_metadata=METADATA,
            cached_inventory=INVENTORY,
        )
        detail.resize(1280, 900)
        return detail
    if name == "kit-states":
        from PySide6.QtWidgets import QHBoxLayout, QWidget

        from ui.widgets import make_action_button, make_badge, make_card_title

        panel = QWidget()
        layout = QHBoxLayout(panel)
        active = make_action_button("Run checks", kind="primary")
        disabled = make_action_button("Download", kind="primary")
        disabled.setEnabled(False)
        active.setFocus()
        layout.addWidget(make_badge("Info"))
        layout.addWidget(active)
        layout.addWidget(disabled)
        layout.addWidget(make_card_title("States"))
        panel.resize(480, 90)
        return panel
    raise AssertionError(f"unknown golden case: {name}")


@pytest.mark.parametrize("name", CASES)
def test_golden(golden_session: Any, request: Any, name: str) -> None:
    check_environment()
    widget = _build(golden_session, name)
    candidate = capture(widget, name)

    if request.config.getoption("update_golden"):
        bless(name)
        write_meta()
        return
    if request.config.getoption("propose_golden"):
        pytest.skip(f"candidate proposed at {candidate}; human must bless it")

    baseline = BASELINE_DIR / f"{name}.png"
    if not baseline.exists():
        pytest.fail(
            f"no baseline for {name}: inspect {candidate}, then run `uv run poe golden-update`"
        )
    diff = compare(baseline, candidate)
    assert not diff.fails(name), (
        f"{name}: {diff.changed_percent:.3f}% pixels over tolerance, "
        f"max delta {diff.max_delta}, bbox {diff.bbox}; see {candidate}"
    )
