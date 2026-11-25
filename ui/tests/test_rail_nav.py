"""Workflow-rail navigation (dv-6wb, dv-gs5): three section buttons.

The rail is the sole jump map: Dataset Checks, File Checks and Response.
Each button is a real QPushButton that only navigates; clicking one logs a
``nav_jump`` action and never runs a download, check or export.
"""

from pathlib import Path

import pytest

# three-button rail -> owning section (or the response page)
NAV = {
    "dataset_checks": "_dataset_checks_heading",
    "file_checks": "_file_checks_heading",
    "response": "respond",
}


@pytest.fixture
def view(qapp, tmp_path):
    from curation.config import Config
    from ui.dataset import DatasetDetailView

    try:
        cfg = Config.load(None)
    except Exception:
        cfg = Config()
    cfg.app.workspace = tmp_path

    v = DatasetDetailView.__new__(DatasetDetailView)
    v._config = cfg
    v._pid = "doi:10.5072/FK2/NAV"
    v._report = None
    v._dl_btn = None  # type: ignore[assignment]
    v._check_btn = None  # type: ignore[assignment]
    v._jumps = []
    v._responses = []
    v._statuses = []
    v._logged = []
    v._goto_section = lambda attr: v._jumps.append(attr)  # type: ignore[method-assign]
    v._show_review_page = lambda: None  # type: ignore[method-assign]
    v._show_response_page = lambda: v._responses.append(1)  # type: ignore[method-assign]
    v._set_status = lambda msg, **_kw: v._statuses.append(msg)  # type: ignore[method-assign]
    v._log_action = lambda a, n="", d=None: v._logged.append((a, n, d))  # type: ignore[assignment]
    return v


class TestRailNavigation:
    def test_three_steps_jump_to_their_sections(self, view):
        for key, expected in NAV.items():
            view._jumps.clear()
            view._responses.clear()
            view._on_workflow_step(key)
            if expected == "respond":
                assert view._responses, f"{key}: no response-page jump"
                assert view._jumps == []
            else:
                assert view._jumps == [expected], f"{key}: {view._jumps}"

    def test_nav_jump_is_logged_with_the_step(self, view):
        view._on_workflow_step("dataset_checks")
        assert view._logged[-1][0] == "nav_jump"
        assert view._logged[-1][2] == {"step": "dataset_checks"}

    def test_unknown_key_is_harmless(self, view):
        view._on_workflow_step("not_a_button")
        assert view._jumps == ["_dataset_checks_heading"]


class TestNavModelsRemoved:
    @staticmethod
    def _dataset_package_source() -> str:
        """All of the ui/dataset/ package source (it replaced dataset_detail.py)."""
        package = Path(__file__).resolve().parents[1] / "dataset"
        return "\n".join(p.read_text(encoding="utf-8") for p in sorted(package.glob("*.py")))

    def test_sidebar_sections_card_and_top_bar_button_are_gone(self):
        src = self._dataset_package_source()
        for forbidden in (
            "_build_nav_card",
            "_SECTION_LINKS",
            "_sections_btn",
            "_sections_menu",
            "_fill_sections_menu",
            "_sidebar_collapse_btn",
        ):
            assert forbidden not in src, forbidden

    def test_rail_is_always_present_and_single(self):
        src = self._dataset_package_source()
        assert "self._rail = WorkflowRail(" in src
        assert "rail" in src  # the rail is created unconditionally

    def test_export_reports_button_is_gone(self):
        src = self._dataset_package_source()
        assert "_history_btn" not in src
        assert "export_reports" not in src


def test_rail_links_are_left_packed_and_stable(qapp):
    """Nav-mode links stay left-packed and keep their size when clicked (2026-11-24)."""
    from ui.theme import workflow_rail_qss
    from ui.widgets import WorkflowRail

    rail = WorkflowRail(
        nav_steps=[
            ("dataset_checks", "Dataset Checks"),
            ("file_checks", "File Checks"),
            ("response", "Response"),
        ]
    )
    rail.resize(1200, 40)
    rail.show()
    for _ in range(5):
        qapp.processEvents()

    lay = rail.layout()
    assert lay is not None
    # A trailing stretch packs the links on the left instead of spreading them.
    assert lay.count() >= 4
    last = lay.itemAt(lay.count() - 1)
    assert last is not None, "the rail has a final item"
    assert last.spacerItem() is not None, "the rail ends with a stretch"

    sizes_before = {k: b.sizeHint() for k, b in rail.buttons.items()}
    positions_before = {k: b.pos() for k, b in rail.buttons.items()}
    rail.set_active_step("file_checks")
    for _ in range(5):
        qapp.processEvents()
    for k, b in rail.buttons.items():
        assert b.sizeHint() == sizes_before[k], f"{k} changed size when activated"
        assert b.pos() == positions_before[k], f"{k} moved when another tab was activated"

    sheet = workflow_rail_qss()
    assert "border-bottom: 1px solid" in sheet
    assert "border: none" in sheet
