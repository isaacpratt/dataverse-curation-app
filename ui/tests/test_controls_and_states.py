"""Control-level guarantees: hit targets, blocked steps, check-run states.

Three small promises the UI now makes, each one a thing a curator can
notice:

* every button is at least 32px tall (and the icon-only ones square),
  so it can be hit with a mouse or a stylus;
* a blocked workflow step is readable (it is guidance, not a disabled
  control) and says so with a lock mark, not with colour alone;
* a check run can be cancelled, and a failed run stays failed on the
  page instead of vanishing behind the dialog.
"""

import pytest
from PySide6.QtWidgets import QHBoxLayout, QWidget


def test_small_buttons_clear_the_hit_target_floor(qapp):
    """The small button token is 32px, not 28."""
    from ui.widgets import BUTTON_HEIGHTS, make_action_button

    assert BUTTON_HEIGHTS["sm"] >= 32, "a 28px chip is a hard target to hit"
    btn = make_action_button("Reset", kind="secondary", size="sm")
    assert btn.height() >= 32
    assert btn.width() >= 32


def test_a_field_placeholder_is_readable(qapp):
    """The placeholder text clears 4.5:1 - it is text, not decoration."""
    from ui.theme import SURFACE_CARD, TEXT_PLACEHOLDER, contrast_ratio
    from ui.widgets import make_search_field

    assert contrast_ratio(TEXT_PLACEHOLDER, SURFACE_CARD) >= 4.5, (
        "a placeholder is text and has to be readable"
    )
    field = make_search_field("Search datasets")
    assert "placeholder-text" in field.styleSheet(), (
        "the field's own sheet replaces the app sheet - it must carry the placeholder colour itself"
    )


def test_field_edges_are_control_edges(qapp):
    """A field's border is a control edge (3:1), not a decorative card edge."""
    from ui.theme import BORDER_CONTROL, SURFACE_CARD, contrast_ratio
    from ui.widgets import AppCheckBox, make_line_edit, make_search_field

    assert contrast_ratio(BORDER_CONTROL, SURFACE_CARD) >= 3.0
    for field in (make_search_field("Search datasets"), make_line_edit("Name")):
        assert BORDER_CONTROL in field.styleSheet(), "a text field's edge must clear the 3:1 floor"
    # The check box paints its indicator itself (dv-7mf), so its edge is a
    # token in the kit, not a line in the sheet.
    _, edge, _ = AppCheckBox.face_colours(enabled=True, checked=False)
    assert edge == BORDER_CONTROL, "a checkbox's edge must clear the 3:1 floor"
    assert contrast_ratio(edge, SURFACE_CARD) >= 3.0


def test_icon_only_buttons_are_square_and_big_enough(qapp):
    """The reset-columns button and the info tip are 32x32."""
    from ui.widgets import add_info_tip, make_reset_columns_button

    reset = make_reset_columns_button("files")
    assert reset.width() >= 32
    assert reset.height() >= 32

    host = QWidget()
    layout = QHBoxLayout(host)
    tip = add_info_tip(layout, "Explains the section")
    assert tip.width() >= 32
    assert tip.height() >= 32


def test_a_blocked_step_is_readable_and_carries_a_lock(qapp):
    """A blocked step is legible text with a lock, not greyed-out text."""
    from ui.theme import SURFACE_CARD, TEXT_BLOCKED, contrast_ratio
    from ui.widgets import WorkflowRail
    from ui.workflow import WorkflowInput, derive_workflow

    rail = WorkflowRail()
    workflow = derive_workflow(WorkflowInput(metadata_loaded=False))
    rail.set_workflow(workflow)
    blocked = [step for step in workflow.steps if step.state == "blocked"]
    assert blocked, "this fixture needs at least one blocked step"
    btn = rail.buttons[blocked[0].key]
    assert not btn.icon().isNull(), (
        "a blocked step must carry a lock mark - colour alone is not a state"
    )
    assert contrast_ratio(TEXT_BLOCKED, SURFACE_CARD) >= 4.5, "a blocked step must stay readable"


def test_a_done_step_wears_a_check_icon(qapp):
    """Done steps lead with the Lucide check, never a text glyph."""
    from ui.widgets import WorkflowRail
    from ui.workflow import WorkflowInput, derive_workflow

    rail = WorkflowRail()
    workflow = derive_workflow(
        WorkflowInput(
            metadata_loaded=True,
            changes_loaded=True,
            staged=3,
            total_files=3,
            report_ready=True,
            exported=True,
            decision_committed=True,
        )
    )
    rail.set_workflow(workflow)
    for step in workflow.steps:
        btn = rail.buttons[step.key]
        assert not btn.icon().isNull(), f"{step.key} must carry its step mark"
        assert "\u2713" not in btn.text(), "the tick must be an icon, not text"


@pytest.fixture(scope="module")
def det(win, qapp):
    win._open_dataset("doi:10.5072/FK2/CTRL", "Controls (tests)")
    detail = None
    for _ in range(100):
        qapp.processEvents()
        detail = getattr(win, "_detail", None)
        if detail is not None and getattr(detail, "_checks_cancel_btn", None) is not None:
            break
    assert detail is not None, "detail view did not open"
    return detail


def test_checks_cancel_is_hidden_until_a_run_starts(det):
    assert det._checks_cancel_btn.isHidden(), "the idle header must not show Cancel"


def test_cancelling_a_check_run_resets_the_header(det):
    det._check_btn.setEnabled(False)
    det._checks_cancel_btn.setVisible(True)
    det._checks_cancel_btn.setEnabled(True)
    det._progress.setVisible(True)
    try:
        det._on_checks_cancelled()
        assert det._check_btn.isEnabled(), "Run checks must come back"
        assert det._checks_cancel_btn.isHidden(), "Cancel must fold away"
        assert det._checks_cancel_btn.isEnabled(), "Cancel must be armed again"
        assert det._progress.isHidden(), "the progress bar must fold away"
        assert "cancelled" in det._status.text().lower()
    finally:
        det._set_status("")


def test_a_failed_check_run_stays_failed_on_the_page(det, monkeypatch):
    """The failure does not disappear when the dialog is closed."""
    monkeypatch.setattr("ui.dialogs.show_critical", lambda *a, **k: None)
    det._on_checks_error("RuntimeError: the check engine fell over")
    try:
        assert det._status.isVisible(), "the failure must stay on the page"
        assert "failed" in det._status.text().lower()
        assert det._check_btn.isEnabled(), "the curator must be able to retry"
        assert det._checks_cancel_btn.isHidden()
    finally:
        det._set_status("")


def test_the_completion_text_is_body_size(det):
    """The status strip reads at body size, not caption size."""
    from ui.theme import FONT_BODY

    sheet = det._status.styleSheet()
    assert f"font-size: {FONT_BODY}px" in sheet, "the run commentary must be body-sized"


def test_check_worker_emits_cancelled_when_interrupted(qapp, tmp_path, monkeypatch):
    """The worker reports a cancelled run instead of a finished one."""
    import engine.runner as runner
    from ui.workers import CheckWorker

    def _run_report(*args, **kwargs):
        worker.cancel()
        return None

    monkeypatch.setattr(runner, "run_report", _run_report)
    hits: list[str] = []
    worker = CheckWorker(tmp_path, "doi:10.5072/FK2/CHK", "title")
    worker.cancelled.connect(lambda: hits.append("cancelled"))
    worker.finished.connect(lambda *_: hits.append("finished"))
    worker.error.connect(lambda _msg: hits.append("error"))
    worker.run()
    assert hits == ["cancelled"], f"expected cancelled only, got {hits}"
