"""Entry-check params read as a form, not a squeezed table (dv-5nd).

Labels are short and fit on one line, each control is full width inside the
Response pane, every explanation lives in a tooltip, and the two phrase
lists are chip fields with Lucide adds/deletes rather than text areas.
Nothing clips at 1440x900 or 960x720.
"""

from typing import Any

from PySide6.QtWidgets import QCheckBox, QLabel, QSpinBox, QTextEdit

from ui.widgets import AppNumberField, AppValueList


def _pane(rc: Any):
    """Return the Response pane: the splitter's second scroll area."""
    from PySide6.QtWidgets import QSplitter

    splitter = next(s for s in rc.findChildren(QSplitter))
    return splitter.widget(1)


def _shown(win: Any, rule: Any, qapp: Any):
    win._show_review_config()
    rc = win._review_config
    rs = rc._current_ruleset()
    snapshot = rs.get("field_rules")
    rs["field_rules"] = [
        {
            "block": "citation",
            "field": "alternativeUrl",
            "label": "Alternative URL",
            "level": "required",
            "handler": "looks_correct",
            "params": {
                "min_length": 12,
                "regex": "^10\\.\\d+/\\S+$",
                "regex_mode": "full",
                "blocklist": ["todo", "placeholder"],
                "controlled_vocabulary": ["doi", "url"],
                "not_common_placeholders": True,
                "not_all_caps": True,
                "date": True,
                "date_order": True,
                "url": True,
            },
        }
    ]
    rc._refresh_field_table()
    rc._sel_kind = "field"
    rc._sel_key = rc._rule_sel_key("citation", "alternativeUrl", "looks_correct")
    rc._show_template_for_selection()
    for _ in range(6):
        qapp.processEvents()
    return rc, snapshot


def _restore(rc: Any, snapshot: Any):
    rc._current_ruleset()["field_rules"] = snapshot
    rc._refresh_field_table()
    rc._clear_dirty()


def _labels(rc: Any):
    return [
        label
        for label in rc._params_panel.findChildren(QLabel)
        if label.objectName() == "LabelStrongSM"
    ]


def test_every_param_label_fits_one_line(win, qapp):
    rc, snapshot = _shown(win, True, qapp)
    try:
        bad = []
        for label in _labels(rc):
            metrics = label.fontMetrics()
            if metrics.horizontalAdvance(label.text()) > label.width():
                bad.append((label.text(), label.width()))
        assert not bad, f"labels wrapped: {bad}"
    finally:
        _restore(rc, snapshot)


def test_controls_fit_the_pane_at_both_widths(win, qapp):
    rc, snapshot = _shown(win, True, qapp)
    try:
        pane = _pane(rc)
        for width, height in ((1440, 900), (960, 720)):
            win.resize(width, height)
            for _ in range(8):
                qapp.processEvents()
            viewport_right = pane.viewport().mapToGlobal(pane.viewport().rect().topRight()).x()
            assert pane.horizontalScrollBar().maximum() == 0, (
                f"the Response pane scrolls sideways at {width}"
            )
            for control in (
                rc._p_min,
                rc._p_regex,
                rc._p_regex_full,
                rc._p_blocklist,
                rc._p_vocab,
                rc._p_not_common_placeholders,
                rc._p_url,
            ):
                right = control.mapToGlobal(control.rect().topRight()).x()
                assert right <= viewport_right + 1, (
                    f"{type(control).__name__} clips at {width}: {right} > {viewport_right}"
                )
    finally:
        _restore(rc, snapshot)


def test_phrase_lists_are_chip_fields_not_text_areas(win, qapp):
    rc, snapshot = _shown(win, True, qapp)
    try:
        assert isinstance(rc._p_blocklist, AppValueList)
        assert isinstance(rc._p_vocab, AppValueList)
        assert rc._p_blocklist.values() == ["todo", "placeholder"]
        assert rc._p_vocab.values() == ["doi", "url"]
        assert not rc._params_panel.findChildren(QTextEdit)
        # The only QSpinBox in the panel is the one inside the kit's number
        # field; no view may construct a raw one (the guard names it too).
        raw_spins = [
            spin
            for spin in rc._params_panel.findChildren(QSpinBox)
            if not isinstance(spin.parentWidget(), AppNumberField)
        ]
        assert not raw_spins, "no bare spin box in the params panel"
        assert isinstance(rc._p_min, AppNumberField)
    finally:
        _restore(rc, snapshot)


def test_explanations_are_tooltips_not_painted_labels(win, qapp):
    rc, snapshot = _shown(win, True, qapp)
    try:
        texts = [label.text() for label in rc._params_panel.findChildren(QLabel)]
        assert not [text for text in texts if "fails closed" in text]
        assert not [text for text in texts if "one per line" in text]
        assert not [text for text in texts if "regular expression" in text]
        tips = [label.toolTip() for label in _labels(rc) if label.toolTip()]
        flags = [
            box.toolTip()
            for box in rc._params_panel.findChildren(QCheckBox)
            if box.property("param_key") and box.toolTip()
        ]
        assert any("ISO date" in tip for tip in tips + flags)
        assert any("http(s)" in tip for tip in tips + flags)
        assert rc._p_min.toolTip(), "the stepper carries its own help"
        assert rc._p_blocklist.toolTip(), "the chip field carries its own help"
    finally:
        _restore(rc, snapshot)


def test_the_five_flags_are_one_checkbox_per_row(win, qapp):
    rc, snapshot = _shown(win, True, qapp)
    try:
        boxes = [
            box for box in rc._params_panel.findChildren(QCheckBox) if box.property("param_key")
        ]
        assert len(boxes) == 5
        assert all(box.toolTip() for box in boxes)
    finally:
        _restore(rc, snapshot)
