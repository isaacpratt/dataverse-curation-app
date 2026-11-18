"""Workflow-rail navigation (dv-6wb): the rail is the sole jump map.

The sidebar Sections card and the top-bar Sections button are gone; the
rail (mechanical or CURATE(D)) navigates to its owning card and logs a
``nav_jump`` action per click.
"""

from pathlib import Path

import pytest

# mechanical step -> owning card it jumps to (or the response page)
MECHANICAL = {
    "metadata": "_meta_card",
    "changes": "_version_card",
    "download": "_file_card",
    "checks": "_auto_card",
    "respond": "respond",
}
# curated step -> owning card (or the response page)
CURATED = {
    "check": "_file_card",
    "understand": "_auto_card",
    "request": "_meta_card",
    "augment": "_meta_card",
    "transform": "_auto_card",
    "evaluate": "_auto_card",
    "document": "respond",
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
    v._history_btn = None  # type: ignore[assignment]
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
    def test_mechanical_steps_jump_to_their_cards(self, view):
        for key, expected in MECHANICAL.items():
            view._jumps.clear()
            view._responses.clear()
            view._on_workflow_step(key)
            if expected == "respond":
                assert view._responses, f"{key}: no response-page jump"
                assert view._jumps == []
            else:
                assert view._jumps == [expected], f"{key}: {view._jumps}"

    def test_curated_steps_jump_to_their_cards(self, view, tmp_path):
        from curation.storage import write_ui_pref

        write_ui_pref(tmp_path, "rail_view", "curated")
        for key, expected in CURATED.items():
            view._jumps.clear()
            view._responses.clear()
            view._on_workflow_step(key)
            if expected == "respond":
                assert view._responses, f"{key}: no response-page jump"
                assert view._jumps == []
            else:
                assert view._jumps == [expected], f"{key}: {view._jumps}"

    def test_export_step_never_crashes_without_a_report(self, view):
        view._on_workflow_step("export")
        assert view._statuses, "export without a report must hint, not crash"

    def test_nav_jump_is_logged_with_step_and_view(self, view):
        view._on_workflow_step("checks")
        assert view._logged[-1][0] == "nav_jump"
        assert view._logged[-1][2] == {"step": "checks", "view": "mechanical"}

    def test_nav_jump_records_curated_view(self, view, tmp_path):
        from curation.storage import write_ui_pref

        write_ui_pref(tmp_path, "rail_view", "curated")
        view._on_workflow_step("evaluate")
        assert view._logged[-1][2] == {"step": "evaluate", "view": "curated"}


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
        assert "self._rail = WorkflowRail()" in src
        assert "rail" in src  # the rail is created unconditionally
