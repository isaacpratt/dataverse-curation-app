"""Review configuration: the Check picker and entry-check params (dv-5id).

A field rule may carry the ``looks_correct`` handler with ``params``; the
Response card shows a Check picker for field rules and the params panel
only while that check is picked. Edits round-trip straight into the rule
dict (JSON on disk), which is what the Response draft evaluates.
"""

import copy


def _with_rule(win, fn):
    """Inject a looks_correct rule, run fn(rc), restore the ruleset after."""
    win._show_review_config()
    rc = win._review_config
    rs = rc._current_ruleset()
    snapshot = copy.deepcopy(rs.get("field_rules") or [])
    probe = {
        "block": "citation",
        "field": "alternativeUrl",
        "label": "Alternative URL",
        "level": "required",
        "requirement": "Requirement",
        "handler": "looks_correct",
        "params": {"min_length": 10},
        "response_template": "Fix it",
    }
    try:
        rs.setdefault("field_rules", []).append(probe)
        rc._refresh_field_table()
        rc._sel_kind = "field"
        rc._sel_key = rc._rule_sel_key("citation", "alternativeUrl", "looks_correct")
        rc._show_template_for_selection()
        return fn(rc, probe)
    finally:
        rs["field_rules"] = snapshot
        rc._refresh_field_table()
        rc._sel_kind = "field"
        rc._sel_key = ""
        rc._show_template_for_selection()
        # The session-scoped window is shared: leave no dirty marker behind.
        rc._clear_dirty()


def test_params_panel_shows_only_for_looks_correct(win):
    def _check(rc, probe):
        assert not rc._check_row.isHidden()
        assert not rc._params_panel.isHidden()
        # Switch the picker to nonempty: params panel hides, Check stays.
        idx = rc._handler_combo.findData("nonempty")
        rc._handler_combo.setCurrentIndex(idx)
        assert rc._params_panel.isHidden()
        assert probe["handler"] == "nonempty"
        # Params survive the round trip (engine ignores them, JSON keeps them).
        assert probe["params"] == {"min_length": 10}

    _with_rule(win, _check)


def test_params_round_trip_into_the_rule(win):
    def _check(rc, probe):
        assert rc._p_min.value() == 10
        rc._p_min.setValue(50)
        assert probe["params"]["min_length"] == 50

        rc._p_regex.setText(r"^10\.\d+/\S+$")
        rc._p_regex_full.setChecked(True)
        assert probe["params"]["regex"] == r"^10\.\d+/\S+$"
        assert probe["params"]["regex_mode"] == "full"

        rc._p_not_common_placeholders.setChecked(True)
        rc._p_url.setChecked(True)
        assert probe["params"]["not_common_placeholders"] is True
        assert probe["params"]["url"] is True

        # Clearing every knob removes params wholesale (fail closed: the
        # engine reports [no entry checks configured]).
        rc._p_min.setValue(0)
        rc._p_regex.setText("")
        rc._p_regex_full.setChecked(False)
        rc._p_not_common_placeholders.setChecked(False)
        rc._p_url.setChecked(False)
        assert "params" not in probe

    _with_rule(win, _check)


def test_handler_picker_seeds_a_sensible_default(win):
    def _check(rc, probe):
        # Start from plain nonempty: params panel hidden, seeded nothing.
        probe["handler"] = "nonempty"
        probe.pop("params", None)
        rc._sel_key = rc._rule_sel_key("citation", "alternativeUrl", "nonempty")
        rc._show_template_for_selection()
        assert rc._params_panel.isHidden()
        idx = rc._handler_combo.findData("looks_correct")
        rc._handler_combo.setCurrentIndex(idx)
        assert probe["handler"] == "looks_correct"
        assert probe["params"] == {"not_common_placeholders": True}
        assert not rc._params_panel.isHidden()

    _with_rule(win, _check)


def test_engine_reads_what_the_ui_writes(win):
    import curation.review_rules as rr

    def _check(rc, probe):
        rc._p_min.setValue(60)
        rc._p_not_common_placeholders.setChecked(True)
        rs = {"field_rules": [probe]}
        meta = {
            "latestVersion": {
                "metadataBlocks": {
                    "citation": {
                        "fields": [
                            {
                                "typeName": "alternativeUrl",
                                "value": "Results of the 2024 soil survey and everything else worth saying here",
                            },
                        ]
                    }
                },
            },
        }
        row = next(
            r
            for r in rr.evaluate_ruleset(meta, rs, [])
            if r["rule_id"] == "field:citation.alternativeUrl:looks_correct"
        )
        assert row["status"] == "complete"
        meta["latestVersion"]["metadataBlocks"]["citation"]["fields"][0]["value"] = (
            "no description yet"
        )
        row = next(
            r
            for r in rr.evaluate_ruleset(meta, rs, [])
            if r["rule_id"] == "field:citation.alternativeUrl:looks_correct"
        )
        assert row["status"] == "incomplete"
        assert "[too short" in row["value"]

    _with_rule(win, _check)
