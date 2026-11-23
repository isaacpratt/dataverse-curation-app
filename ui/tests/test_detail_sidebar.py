"""Sidebar order, rail counts and the log (dv-gfx.6, dv-gfx.7, dv-gfx.14).

The sidebar reads preview → version log → dataset log, the log content runs
edge to edge inside its card, the rail's counts cover metadata + automated
+ file checks, and the dataset log drops the chrome events a curator does
not want to reread.
"""

from typing import Any

PID = "doi:10.5072/FK2/SIDE"


def _result(check_id: str, level: str, passed: bool, message: str) -> Any:
    from engine.checks.base import CheckResult

    return CheckResult(check_id=check_id, level=level, passed=passed, message=message, details={})


def _report() -> Any:
    from engine.report import DatasetReport, FileEntry

    return DatasetReport(
        persistent_id=PID,
        label="Side",
        engine_version="t",
        dataset_checks=[
            _result("a.one", "warning", True, "one"),
            _result("a.two", "warning", True, "two"),
        ],
        files=[
            FileEntry(
                path="a.csv",
                size_bytes=10,
                mime_type="text/csv",
                checks=[_result("f.one", "error", False, "bad")],
            )
        ],
    )


def _view(qapp, tmp_path) -> Any:
    from curation.config import Config
    from ui.dataset import DatasetDetailView

    cfg = Config()
    cfg.app.workspace = tmp_path
    view = DatasetDetailView(cfg, PID, "Side", cached_metadata={"id": 1}, cached_inventory=[])
    view._report = _report()
    for _ in range(6):
        qapp.processEvents()
    return view


def _order(layout: Any) -> list[Any]:
    out = []
    for i in range(layout.count()):
        item = layout.itemAt(i)
        widget = item.widget() if item is not None else None
        if widget is not None:
            out.append(widget)
    return out


def test_sidebar_order_is_preview_versions_log(qapp, tmp_path):
    view = _view(qapp, tmp_path)
    try:
        widgets = _order(view._side_wrap)
        assert widgets.index(view._preview_card) < widgets.index(view._version_card)
        assert widgets.index(view._version_card) < widgets.index(view._dataset_log_card)
    finally:
        view.deleteLater()


def test_dataset_log_runs_edge_to_edge(qapp, tmp_path):
    """The log list is the card's content, not a box inside it (dv-gfx.17)."""
    view = _view(qapp, tmp_path)
    try:
        body = view._dataset_log.parentWidget()
        assert body is not None
        layout = body.layout()
        assert layout is not None
        margins = layout.contentsMargins()
        assert margins.left() == 0
        assert margins.right() == 0
        # The list paints the card's bottom corners (flush list face).
        sheet = view._dataset_log.styleSheet()
        assert "border-bottom-left-radius" in sheet
    finally:
        view.deleteLater()


def test_rail_counts_cover_every_check_family(qapp, tmp_path):
    """Metadata + automated + file results all count (dv-gfx.14)."""
    view = _view(qapp, tmp_path)
    try:
        text = view._rail.hint.text()
        # Two passing dataset checks + the metadata completeness passes.
        assert text.count("passed") == 1
        assert "error" in text or "warning" in text
    finally:
        view.deleteLater()


def _fake_state(actions: list[dict[str, Any]]) -> Any:
    class _State:
        def list_actions(self, pid, limit=50):
            return list(actions)

        def close(self):
            pass

    return _State()


def test_dataset_log_drops_chrome_events(qapp, tmp_path, monkeypatch):
    """Preview-open and rail-jump entries stay out; a run logs once (dv-gfx.7)."""
    view = _view(qapp, tmp_path)
    try:
        actions = [
            {"action": "preview_rendered", "notes": "a.csv", "timestamp": "2026-01-01T10:00:00Z"},
            {"action": "nav_jump", "notes": "file_checks", "timestamp": "2026-01-01T10:01:00Z"},
            {
                "action": "checks_run",
                "notes": "3 findings in 1 file — report saved to folder",
                "timestamp": "2026-01-01T10:02:00Z",
            },
        ]
        monkeypatch.setattr(view, "_state", lambda: _fake_state(actions))
        view._refresh_dataset_log()

        rows = [view._dataset_log.item(i).text() for i in range(view._dataset_log.count())]
        joined = " ".join(rows).lower()
        assert "preview" not in joined
        assert "jumped" not in joined
        assert joined.count("automated checks run") == 1
        assert "report saved to folder" in joined
    finally:
        view.deleteLater()
