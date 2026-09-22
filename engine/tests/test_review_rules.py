"""Tests for rule-driven completeness (review_rules) + legacy parity."""

import copy

import metadata_check as mc
import review_rules as rr


def _meta(fields=(), license_name="CC0"):
    return {
        "latestVersion": {
            "license": {"name": license_name} if license_name else {},
            "metadataBlocks": {"citation": {"fields": list(fields)}},
        }
    }


def _f(name, value):
    return {"typeName": name, "value": value}


def test_mcmaster_set_parity_with_legacy():
    meta = _meta([
        _f("title", "T"),
        _f("author", [{"authorName": {"value": "J"}, "authorAffiliation": {"value": "M"}}]),
        _f("datasetContact", [{"datasetContactName": {"value": "J"}}]),
        _f("subject", ["Math"]),
        _f("dsDescription", [{"dsDescriptionValue": {"value": "d"}}]),
        _f("depositor", "J"),
        _f("dateOfDeposit", "2026-01-01"),
    ])
    inv = [{"path": "README.md"}]
    new = mc.check_metadata_completeness(meta, "McMaster", inv)
    old = mc._check_mcmaster(meta, meta["latestVersion"]["metadataBlocks"], inv)
    assert sorted((r["field"], r["requirement"], r["value"], r["status"]) for r in new) == \
        sorted((r["field"], r["requirement"], r["value"], r["status"]) for r in old)


def test_minimal_exact_parity_with_legacy():
    meta = _meta([_f("title", "T")])
    assert mc.check_metadata_completeness(meta, "Minimal", []) == \
        mc._check_minimal(meta, meta["latestVersion"]["metadataBlocks"], [])


def test_unchecked_field_is_skipped():
    rs = copy.deepcopy(rr.get_ruleset("mcmaster-default"))
    for fr in rs["field_rules"]:
        if fr["field"] == "subject":
            fr["level"] = "unchecked"
    res = rr.evaluate_ruleset(_meta([_f("title", "T")]), rs, [])
    assert not any(r["field"] == "Subject" for r in res)


def test_optional_missing_stays_incomplete_with_level():
    rs = copy.deepcopy(rr.get_ruleset("mcmaster-default"))
    res = rr.evaluate_ruleset(_meta([]), rs, [])
    orcid = next(r for r in res if r["rule_id"] == "field:citation.author:orcid")
    assert orcid["status"] == "incomplete" and orcid["level"] == "optional"


def test_content_rule_filename_glob():
    rule = {"id": "readme-present", "label": "README file", "level": "required",
            "requirement": "R", "scope": ["filenames"], "match": "filename-glob",
            "pattern": "readme*", "case_sensitive": False, "response_template": ""}
    assert rr.evaluate_content_rule(rule, {}, None)["pending"] is True
    assert rr.evaluate_content_rule(rule, {}, [])["status"] == "complete"  # no files: not applicable
    assert rr.evaluate_content_rule(rule, {}, [{"path": "data/README.md"}])["status"] == "complete"
    assert rr.evaluate_content_rule(rule, {}, [{"path": "data/myreadme_data.csv"}])["status"] == "incomplete"


def test_filename_glob_case_sensitive_skips_legacy_fallback():
    rule = {"id": "r", "label": "R", "level": "required", "requirement": "R",
            "scope": ["filenames"], "match": "filename-glob",
            "pattern": "readme*", "case_sensitive": True, "response_template": ""}
    # "README.md" does not match case-sensitive "readme*", and the legacy
    # case-insensitive basename fallback must not rescue it.
    assert rr.evaluate_content_rule(rule, {}, [{"path": "README.md"}])["status"] == "incomplete"
    assert rr.evaluate_content_rule(rule, {}, [{"path": "readme.txt"}])["status"] == "complete"


def test_filename_glob_with_slash_matches_full_path():
    rule = {"id": "r", "label": "R", "level": "required", "requirement": "R",
            "scope": ["filenames"], "match": "filename-glob",
            "pattern": "docs/*.md", "case_sensitive": False, "response_template": ""}
    assert rr.evaluate_content_rule(rule, {}, [{"path": "docs/guide.md"}])["status"] == "complete"
    assert rr.evaluate_content_rule(rule, {}, [{"path": "other/guide.md"}])["status"] == "incomplete"


def test_content_rule_metadata_scope():
    rule = {"id": "x", "label": "X", "level": "required", "requirement": "R",
            "scope": ["metadata"], "match": "substring", "pattern": "funding",
            "case_sensitive": False, "response_template": ""}
    meta = _meta([_f("notesText", "Funding acknowledgement: NSF grant")])
    assert rr.evaluate_content_rule(rule, meta, [])["status"] == "complete"
    assert rr.evaluate_content_rule(rule, _meta([]), [])["status"] == "incomplete"


def test_content_rule_file_content_pending_without_staged(tmp_path):
    rule = {"id": "x", "label": "X", "level": "required", "requirement": "R",
            "scope": ["file-content"], "match": "substring", "pattern": "hello",
            "case_sensitive": False, "response_template": ""}
    assert rr.evaluate_content_rule(rule, {}, [], staged_dir=tmp_path / "missing")["pending"] is True


def test_content_rule_file_content_match(tmp_path):
    (tmp_path / "notes.txt").write_text("hello world", encoding="utf-8")
    rule = {"id": "x", "label": "X", "level": "required", "requirement": "R",
            "scope": ["file-content"], "match": "substring", "pattern": "hello",
            "case_sensitive": False, "response_template": ""}
    assert rr.evaluate_content_rule(rule, {}, [], staged_dir=tmp_path)["status"] == "complete"


def test_field_rule_ids_unique_per_handler():
    rs = copy.deepcopy(rr.get_ruleset("mcmaster-default"))
    res = rr.evaluate_ruleset(_meta([]), rs, [])
    ids = [r["rule_id"] for r in res]
    assert len(ids) == len(set(ids)), ids


def test_rulesets_for_dataverse_wildcard():
    pool = rr.load_rulesets()
    assert any(k == "mcmaster-default" for k, _ in rr.rulesets_for_dataverse("https://demo.borealisdata.ca", pool))


def test_save_load_roundtrip(tmp_path, monkeypatch):
    import review_rules as _rr

    target = tmp_path / "requirements_profiles.json"
    monkeypatch.setattr(_rr, "rulesets_path", lambda: target)
    monkeypatch.setattr(_rr, "_RULESETS_MEMO", {})
    pool = _rr.load_rulesets()
    pool["lab"] = dict(pool["mcmaster-default"])
    pool["lab"]["dataverses"] = ["https://example.invalid"]
    _rr.save_rulesets(pool)
    assert _rr.load_rulesets()["lab"]["dataverses"] == ["https://example.invalid"]


def test_load_memoized_and_invalidated_on_save(tmp_path, monkeypatch):
    import review_rules as _rr

    target = tmp_path / "requirements_profiles.json"
    monkeypatch.setattr(_rr, "rulesets_path", lambda: target)
    monkeypatch.setattr(_rr, "_RULESETS_MEMO", {})
    first = _rr.load_rulesets()
    assert _rr.load_rulesets() is first  # no disk re-read
    pool = dict(first)
    pool["lab2"] = dict(first["mcmaster-default"])
    _rr.save_rulesets(pool)
    assert "lab2" in _rr.load_rulesets()


def test_deleted_ruleset_leaves_profiles(tmp_path, monkeypatch):
    import review_rules as _rr

    target = tmp_path / "requirements_profiles.json"
    monkeypatch.setattr(_rr, "rulesets_path", lambda: target)
    monkeypatch.setattr(_rr, "_RULESETS_MEMO", {})
    import metadata_check as _mc

    pool = _rr.load_rulesets()
    pool["temp-custom"] = dict(pool["mcmaster-default"])
    _rr.save_rulesets(pool)
    _mc.refresh_profiles_from_rulesets()
    assert "temp-custom" in _mc.PROFILES
    del pool["temp-custom"]
    _rr.save_rulesets(pool)
    _mc.refresh_profiles_from_rulesets()
    assert "temp-custom" not in _mc.PROFILES
    assert "McMaster" in _mc.PROFILES and "Minimal" in _mc.PROFILES
