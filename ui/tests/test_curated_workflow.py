"""The CURATE(D) practice view (dv-sce): derivation states/counts, rail rebuild across step sets, badge letters, and toggle persistence."""


from ui.workflow import (
    AVAILABLE,
    BLOCKED,
    CURRENT,
    DONE,
    WorkflowInput,
    derive_curated,
    derive_workflow,
)


def _ready(**kw) -> WorkflowInput:
    """Build a fully-loaded dataset baseline; tests override fields."""
    for key, value in (
        ("staged", 3), ("total_files", 3), ("report_ready", True),
    ):
        kw.setdefault(key, value)
    return WorkflowInput(metadata_loaded=True, **kw)


class TestDeriveCurated:
    def test_seven_steps_with_badges(self):
        wf = derive_curated(_ready(errors=0, warnings=0))
        assert [s.key for s in wf.steps] == [
            "check", "understand", "request", "augment",
            "transform", "evaluate", "document",
        ]
        assert [s.badge for s in wf.steps] == ["C", "U", "R", "A", "T", "E", "D"]

    def test_clean_dataset_all_done_document_current(self):
        wf = derive_curated(_ready(errors=0, warnings=0, decision_committed=False))
        assert all(s.state == DONE for s in wf.steps[:-1])
        assert wf.steps[-1].key == "document"
        assert wf.current == "document"

    def test_counts_surface_on_the_right_steps(self):
        wf = derive_curated(_ready(required_missing=4, optional_missing=2))
        by_key = {s.key: s for s in wf.steps}
        assert "4" in by_key["request"].hint
        assert "2" in by_key["augment"].hint
        assert by_key["request"].state == CURRENT

    def test_outstanding_findings_count_on_evaluate(self):
        wf = derive_curated(_ready(errors=1, warnings=2))
        by_key = {s.key: s for s in wf.steps}
        assert "3" in by_key["evaluate"].hint
        assert by_key["evaluate"].state == CURRENT

    def test_nothing_loaded_blocks_the_front_steps(self):
        wf = derive_curated(WorkflowInput())
        by_key = {s.key: s for s in wf.steps}
        # The first step wears CURRENT even when its base state is blocked
        # (the single-current overlay), so assert the base states behind it.
        assert wf.current == "check"
        assert by_key["request"].state == BLOCKED
        assert by_key["augment"].state == BLOCKED
        # With nothing known yet, "download first" does not apply.
        assert by_key["understand"].state == AVAILABLE
        assert by_key["evaluate"].state == AVAILABLE

    def test_partial_staging_keeps_check_current(self):
        wf = derive_curated(
            _ready(staged=1, total_files=3, errors=0, warnings=0, report_ready=False)
        )
        by_key = {s.key: s for s in wf.steps}
        assert by_key["check"].state == CURRENT
        # Some files staged: checks can run, so understand opens up.
        assert by_key["understand"].state == AVAILABLE

    def test_respond_open_focuses_document(self):
        wf = derive_curated(_ready(errors=0, warnings=0, response_open=True))
        assert wf.current == "document"

    def test_mechanical_derivation_ignores_new_fields(self):
        wf = derive_workflow(_ready(errors=5, warnings=5, required_missing=5))
        assert [s.key for s in wf.steps] == [
            "metadata", "changes", "download", "checks", "export", "respond",
        ]

    def test_pure_no_io(self):
        """Same input -> same workflow (no hidden state, no I/O)."""
        inp = _ready(errors=1, warnings=0, required_missing=1)
        assert derive_curated(inp) == derive_curated(inp)


class TestRail:
    def test_rail_rebuilds_between_step_sets(self, qapp):
        from ui.widgets import WorkflowRail

        rail = WorkflowRail()
        rail.set_workflow(derive_workflow(_ready()))
        assert len(rail.buttons) == 6
        rail.set_workflow(derive_curated(_ready(staged=1, total_files=3)))
        assert len(rail.buttons) == 7
        # Badge letters replace the numbers for available steps.
        assert rail.buttons["check"].text().startswith("C")
        assert rail.buttons["document"].text().startswith("D")
        rail.set_workflow(derive_workflow(WorkflowInput()))
        assert len(rail.buttons) == 6
        assert rail.buttons["metadata"].text().startswith("1")

    def test_toggle_signal_fires(self, qapp):
        from ui.widgets import WorkflowRail

        rail = WorkflowRail()
        fired = []
        rail.viewToggled.connect(lambda: fired.append(True))
        rail._toggle.click()
        assert fired == [True]

    def test_toggle_persists(self, qapp, tmp_path):
        from storage import read_ui_pref, write_ui_pref

        write_ui_pref(tmp_path, "rail_view", "curated")
        assert read_ui_pref(tmp_path, "rail_view", "mechanical") == "curated"
        assert read_ui_pref(tmp_path, "nothing_set", "mechanical") == "mechanical"

    def test_rail_fits_at_960(self, qapp):
        """Both views keep a minimum width inside the app's 960px floor."""
        from ui.widgets import WorkflowRail

        rail = WorkflowRail()
        for workflow in (
            derive_workflow(_ready()),
            derive_curated(_ready(errors=1, warnings=1, required_missing=2)),
        ):
            rail.set_workflow(workflow)
            rail.resize(960, rail.sizeHint().height())
            rail.show()
            for _ in range(5):
                qapp.processEvents()
            assert rail.minimumSizeHint().width() <= 960, workflow.steps[0].key
            rail.hide()
