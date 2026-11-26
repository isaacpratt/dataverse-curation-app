"""dv-nkip: removed metadata rows must never paint over the rebuilt list.

The pending "Load metadata" row is deleted asynchronously. A widget taken
out of a layout keeps its parent and last geometry until Qt processes the
deferred delete, so an undisposed placeholder was painting across the
completeness rows.
"""

from typing import Any

from PySide6.QtWidgets import QFrame, QLabel, QWidget

from ui.i18n import t

PID = "doi:10.5072/FK2/GHOST"


def _pump(qapp: Any, turns: int = 60) -> None:
    for _ in range(turns):
        qapp.processEvents()


def _meta() -> dict[str, Any]:
    return {
        "latestVersion": {
            "versionState": "DRAFT",
            "metadataBlocks": {
                "citation": {
                    "fields": [
                        {"typeName": "title", "value": "A dataset with metadata"},
                        {"typeName": "depositor", "value": "Ada Lovelace"},
                    ]
                }
            },
        }
    }


def _pending_labels(view: QWidget) -> list[QLabel]:
    """Visible labels still showing the placeholder copy, anywhere in the view."""
    return [
        label
        for label in [view, *view.findChildren(QLabel)]
        if isinstance(label, QLabel)
        and label.isVisible()
        and t("detail.metadata_check.pending_body") in label.text()
    ]


def test_placeholder_disappears_when_completeness_loads(qapp, tmp_path):
    from curation.config import Config
    from ui.dataset import DatasetDetailView

    cfg = Config()
    cfg.app.workspace = tmp_path
    view = DatasetDetailView(cfg, PID, "A dataset with metadata")
    view._auto_load_timer.stop()  # keep this test off the network
    view.show()
    _pump(qapp)

    pending = t("detail.metadata_check.pending_body")
    try:
        assert any(
            pending in label.text() for label in view.findChildren(QLabel) if label.isVisible()
        ), "the pending row must show before metadata loads"

        view._populate_completeness(_meta())
        _pump(qapp)

        assert not _pending_labels(view), "the pending row is still painted"
        # The placeholder was unparented, so it can no longer be found
        # under the view — and it must not be a visible orphan window.
        # Use the tracked registry, not QApplication.topLevelWidgets():
        # wrappers left behind after C++ deletion crashed CI workers (dv-tqi4).
        from ui import theme as _theme

        orphans = [
            w
            for w in _theme.retheme_top_levels()
            if w.isVisible() and hasattr(w, "text") and pending in w.text()
        ]
        assert orphans == []
    finally:
        view.close()
        view.deleteLater()
        _pump(qapp, 10)


def test_cached_metadata_never_shows_the_placeholder(qapp, tmp_path):
    from curation.config import Config
    from ui.dataset import DatasetDetailView

    cfg = Config()
    cfg.app.workspace = tmp_path
    view = DatasetDetailView(
        cfg, PID, "A dataset with metadata", cached_metadata=_meta(), cached_inventory=[]
    )
    view.show()
    _pump(qapp)
    try:
        assert not _pending_labels(view)
        # No AutoCheckRow still carrying the placeholder label/button.
        pending = t("detail.metadata_check.pending_body")
        ghosts = [
            row
            for row in view.findChildren(QFrame, "AutoCheckRow")
            if row.isVisible()
            and any(
                pending in child.text()
                for child in row.findChildren(QWidget)
                if hasattr(child, "text")
            )
        ]
        assert ghosts == []
    finally:
        view.close()
        view.deleteLater()
        _pump(qapp, 10)
