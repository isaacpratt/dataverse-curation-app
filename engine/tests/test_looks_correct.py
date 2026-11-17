"""Tests for the looks_correct handler (dv-5id): entry-correctness rules.

Each sub-shape is exercised against fixture metadata blocks; every failure
must carry a bracketed reason so a result is never a silent pass.
"""


import review_rules as rr


def _meta(fields=()):
    return {
        "latestVersion": {
            "metadataBlocks": {"citation": {"fields": list(fields)}},
        }
    }


def _f(name, value):
    return {"typeName": name, "value": value}


def _rule(params, level="required", label="Field", field="title"):
    return {
        "block": "citation",
        "field": field,
        "label": label,
        "level": level,
        "requirement": "Requirement",
        "handler": "looks_correct",
        "params": params,
        "response_template": "Fix it",
    }


def _run(meta, params, field="title", level="required"):
    blocks = rr._blocks(meta)
    return rr._eval_handler(
        "looks_correct", meta, blocks, "citation", field,
        _rule(params, level=level, field=field),
    )


# -- min_length ----------------------------------------------------------------


def test_min_length_passes_and_fails():
    ok_text = "A" * 60
    assert _run(_meta([_f("title", ok_text)]), {"min_length": 50})[0] is True
    ok, val = _run(_meta([_f("title", "short")]), {"min_length": 50})
    assert ok is False
    assert "[too short: 5 of 50 characters]" in val


def test_min_length_counts_concatenated_multi_entry_values():
    desc = [
        {"dsDescriptionValue": {"value": "First half of the description, long enough?", "typeName": "text"}},
        {"dsDescriptionValue": {"value": "Second half of the description.", "typeName": "text"}},
    ]
    assert _run(_meta([_f("dsDescription", desc)]), {"min_length": 50}, field="dsDescription")[0] is True


# -- regex ----------------------------------------------------------------------


def test_regex_search_mode_finds_a_match_anywhere():
    assert _run(_meta([_f("title", "abc123")]), {"regex": r"\d{3}"})[0] is True
    assert _run(_meta([_f("title", "abc")]), {"regex": r"\d{3}"})[0] is False


def test_regex_full_mode_anchors_both_ends():
    assert _run(_meta([_f("title", "abc123")]), {"regex": r"\d{3}", "regex_mode": "full"})[0] is False
    assert _run(_meta([_f("title", "123")]), {"regex": r"\d{3}", "regex_mode": "full"})[0] is True


def test_regex_case_insensitivity_is_left_to_the_pattern():
    assert _run(_meta([_f("title", "DOI 10.5072/FK2/X")]), {"regex": r"^10\.\d{4,9}/\S+$", "regex_mode": "full"})[0] is False
    assert _run(_meta([_f("title", "10.5072/FK2/X")]), {"regex": r"^10\.\d{4,9}/\S+$", "regex_mode": "full"})[0] is True


def test_invalid_regex_fails_closed_instead_of_raising():
    ok, val = _run(_meta([_f("title", "anything")]), {"regex": "([unclosed"})
    assert ok is False
    assert "rule error" in val


# -- blocklist & placeholders ---------------------------------------------------


def test_blocklist_is_case_insensitive():
    meta = _meta([_f("title", "MY DATA SET (draft)")])
    assert _run(meta, {"blocklist": ["DRAFT"]})[0] is False
    assert _run(meta, {"blocklist": ["final"]})[0] is True


def test_builtin_placeholder_blocklist():
    assert _run(_meta([_f("dsDescription", [{"dsDescriptionValue": {"value": "no description yet", "typeName": "text"}}])]),
                {"not_common_placeholders": True}, field="dsDescription")[0] is False
    assert _run(_meta([_f("title", "Results of the 2024 soil survey")]),
                {"not_common_placeholders": True})[0] is True


def test_not_all_caps():
    assert _run(_meta([_f("title", "ALL CAPS TITLE")]), {"not_all_caps": True})[0] is False
    assert _run(_meta([_f("title", "Title case is fine")]), {"not_all_caps": True})[0] is True
    assert _run(_meta([_f("title", "2024 SOIL SURVEY")]), {"not_all_caps": True})[0] is False


# -- controlled vocabulary --------------------------------------------------------


def test_controlled_vocabulary_membership():
    meta = _meta([_f("subject", ["Math", "biology"])])
    assert _run(meta, {"controlled_vocabulary": ["math", "biology"]}, field="subject")[0] is True


def test_controlled_vocabulary_rejects_one_bad_token():
    meta = _meta([_f("subject", ["Math", "Quantum Knitting"])])
    ok, val = _run(meta, {"controlled_vocabulary": ["math", "biology"]}, field="subject")
    assert ok is False
    assert "not in vocabulary" in val


def test_controlled_vocabulary_accepts_comma_separated_string():
    meta = _meta([_f("subject", ["Math"])])
    assert _run(meta, {"controlled_vocabulary": "math, biology"}, field="subject")[0] is True


# -- dates ------------------------------------------------------------------------


def test_date_parses_iso_shapes():
    for good in ("2026", "2026-03", "2026-03-31", "2026-03-31T10:00:00Z"):
        assert _run(_meta([_f("dateOfDeposit", good)]), {"date": True}, field="dateOfDeposit")[0] is True, good
    assert _run(_meta([_f("dateOfDeposit", "2026-13-45")]), {"date": True}, field="dateOfDeposit")[0] is False
    assert _run(_meta([_f("dateOfDeposit", "spring 2026")]), {"date": True}, field="dateOfDeposit")[0] is False


def _time_period(start, end):
    return _f("timePeriodCovered", [
        {"startDate": {"value": start, "typeName": "text"},
         "endDate": {"value": end, "typeName": "text"}},
    ])


def test_date_order_passes_when_start_not_after_end():
    meta = _meta([_time_period("2001", "2010")])
    assert _run(meta, {"date_order": True}, field="timePeriodCovered")[0] is True


def test_date_order_fails_when_start_is_after_end():
    meta = _meta([_time_period("2010", "2005")])
    ok, val = _run(meta, {"date_order": True}, field="timePeriodCovered")
    assert ok is False
    assert "date range reversed" in val


def test_date_order_fails_on_unparseable_dates():
    meta = _meta([_time_period("spring 2001", "2010")])
    ok, val = _run(meta, {"date_order": True}, field="timePeriodCovered")
    assert ok is False
    assert "date not parseable" in val


def test_date_order_fails_closed_when_there_is_no_pair_to_compare():
    meta = _meta([_f("timePeriodCovered", [{"note": {"value": "recent", "typeName": "text"}}])])
    ok, val = _run(meta, {"date_order": True}, field="timePeriodCovered")
    assert ok is False
    assert "no checkable value" in val


# -- urls --------------------------------------------------------------------------


def test_url_requires_scheme_and_dotted_host():
    assert _run(_meta([_f("alternativeUrl", "https://example.com/data")]), {"url": True}, field="alternativeUrl")[0] is True
    assert _run(_meta([_f("alternativeUrl", "example.com")]), {"url": True}, field="alternativeUrl")[0] is False
    assert _run(_meta([_f("alternativeUrl", "https://nodot")]), {"url": True}, field="alternativeUrl")[0] is False
    assert _run(_meta([_f("alternativeUrl", "ftp://example.com")]), {"url": True}, field="alternativeUrl")[0] is False


# -- no silent passes ---------------------------------------------------------------


def test_empty_value_is_incomplete_never_complete():
    ok, val = _run(_meta([_f("title", "")]), {"min_length": 10})
    assert ok is False and val == "—"


def test_rule_with_no_effective_checks_fails_closed():
    ok, val = _run(_meta([_f("title", "Real title")]), {})
    assert ok is False
    assert "no entry checks configured" in val


def test_every_failure_carries_a_bracketed_reason():
    meta = _meta([
        _f("title", "short"),
        _f("subject", ["Quantum Knitting"]),
        _f("dateOfDeposit", "2026-13-45"),
    ])
    failures = [
        _run(meta, {"min_length": 50}, field="title"),
        _run(meta, {"controlled_vocabulary": ["math"]}, field="subject"),
        _run(meta, {"date": True}, field="dateOfDeposit"),
    ]
    for ok, val in failures:
        assert ok is False
        assert "[" in val and "]" in val, val


# -- dotted paths -------------------------------------------------------------------


def test_dotted_date_order_only_fails_closed():
    """date_order is meaningless per leaf; it must not silently pass."""
    ok, val = _run(
        _meta([_f("author", [{"authorName": {"typeName": "text", "value": "Ada Lovelace"}}])]),
        {"date_order": True}, field="author.authorName",
    )
    assert ok is False
    assert "no entry checks configured" in val


def test_invalid_min_length_fails_closed_not_silently():
    ok, val = _run(_meta([_f("title", "Real title")]), {"min_length": "abc"})
    assert ok is False
    assert "rule error" in val
    ok, val = _run(_meta([_f("title", "Real title")]), {"min_length": -5})
    assert ok is False
    assert "rule error" in val


def test_partial_date_range_fails_closed():
    meta = _meta([_f("timePeriodCovered", [{"startDate": {"value": "2001", "typeName": "text"}}])])
    ok, val = _run(meta, {"date_order": True}, field="timePeriodCovered")
    assert ok is False
    assert "one-sided" in val


def test_partial_pair_alongside_complete_pair_passes():
    meta = _meta([_f("timePeriodCovered", [
        {"startDate": {"value": "2001", "typeName": "text"},
         "endDate": {"value": "2010", "typeName": "text"}},
        {"startDate": {"value": "1999", "typeName": "text"}},
    ])])
    ok, _ = _run(meta, {"date_order": True}, field="timePeriodCovered")
    assert ok is True


def test_dotted_path_checks_each_leaf():
    fields = [_f("author", [
        {"authorName": {"value": "Ada Lovelace", "typeName": "text"},
         "authorAffiliation": {"value": "Analytical Engine Institute", "typeName": "text"}},
        {"authorName": {"value": "Bob", "typeName": "text"},
         "authorAffiliation": {"value": "W", "typeName": "text"}},
    ])]
    meta = _meta(fields)
    ok, val = _run(meta, {"min_length": 3}, field="author.authorAffiliation")
    assert ok is False  # "W" fails the 3-char minimum


def test_dotted_path_fails_when_a_leaf_is_missing():
    fields = [_f("author", [
        {"authorName": {"value": "Ada Lovelace", "typeName": "text"},
         "authorAffiliation": {"value": "", "typeName": "text"}},
    ])]
    ok, val = _run(_meta(fields), {"min_length": 2}, field="author.authorAffiliation")
    assert ok is False and val == "—"


# -- ruleset plumbing ----------------------------------------------------------------


def test_rule_id_and_level_flow_through_evaluate_ruleset():
    meta = _meta([_f("title", "short")])
    rs = {
        "field_rules": [
            _rule({"min_length": 50}, level="optional", label="Title"),
        ],
    }
    results = rr.evaluate_ruleset(meta, rs, [])
    row = next(r for r in results if r["rule_id"] == "field:citation.title:looks_correct")
    assert row["status"] == "incomplete"
    assert row["level"] == "optional"
    assert row["response_template"] == "Fix it"
    assert "[too short" in row["value"]


def test_looks_correct_rule_passes_clean_deposit():
    meta = _meta([_f("title", "A perfectly reasonable deposit title")])
    rs = {"field_rules": [_rule({"min_length": 10, "not_common_placeholders": True}, label="Title")]}
    results = rr.evaluate_ruleset(meta, rs, [])
    row = next(r for r in results if r["rule_id"] == "field:citation.title:looks_correct")
    assert row["status"] == "complete"
    assert row["value"].startswith("A perfectly reasonable deposit title")
