"""Tests for rule-driven completeness (review_rules) + legacy parity."""

import copy
from pathlib import Path
from typing import Any

import pytest

from curation import metadata_check as mc
from curation import review_rules as rr


def _meta(fields: list[Any] | None = None, license_name: str = "CC0") -> dict[str, Any]:
    return {
        "latestVersion": {
            "license": {"name": license_name} if license_name else {},
            "metadataBlocks": {"citation": {"fields": list(fields or [])}},
        }
    }


def _f(name: str, value: Any) -> dict[str, Any]:
    return {"typeName": name, "value": value}


def test_mcmaster_set_parity_with_legacy() -> None:
    meta = _meta(
        [
            _f("title", "T"),
            _f("author", [{"authorName": {"value": "J"}, "authorAffiliation": {"value": "M"}}]),
            _f("datasetContact", [{"datasetContactName": {"value": "J"}}]),
            _f("subject", ["Math"]),
            _f("dsDescription", [{"dsDescriptionValue": {"value": "d"}}]),
            _f("depositor", "J"),
            _f("dateOfDeposit", "2026-01-01"),
        ]
    )
    inv = [{"path": "README.md"}]
    new = mc.check_metadata_completeness(meta, "McMaster", inv)
    old = mc._check_mcmaster(meta, meta["latestVersion"]["metadataBlocks"], inv)
    assert sorted((r["field"], r["requirement"], r["value"], r["status"]) for r in new) == sorted(
        (r["field"], r["requirement"], r["value"], r["status"]) for r in old
    )


def test_minimal_exact_parity_with_legacy() -> None:
    meta = _meta([_f("title", "T")])
    assert mc.check_metadata_completeness(meta, "Minimal", []) == mc._check_minimal(
        meta, meta["latestVersion"]["metadataBlocks"], []
    )


def test_unchecked_field_is_skipped() -> None:
    rs = copy.deepcopy(rr.get_ruleset("mcmaster-default"))
    for fr in rs["field_rules"]:
        if fr["field"] == "subject":
            fr["level"] = "unchecked"
    res = rr.evaluate_ruleset(_meta([_f("title", "T")]), rs, [])
    assert not any(r["field"] == "Subject" for r in res)


def test_optional_missing_stays_incomplete_with_level() -> None:
    rs = copy.deepcopy(rr.get_ruleset("mcmaster-default"))
    res = rr.evaluate_ruleset(_meta([]), rs, [])
    orcid = next(r for r in res if r["rule_id"] == "field:citation.author.authorIdentifier:orcid")
    assert orcid["status"] == "incomplete"
    assert orcid["level"] == "optional"


def test_content_rule_filename_glob() -> None:
    rule = {
        "id": "readme-present",
        "label": "README file",
        "level": "required",
        "requirement": "R",
        "scope": ["filenames"],
        "match": "filename-glob",
        "pattern": "readme*",
        "case_sensitive": False,
        "response_template": "",
    }
    assert rr.evaluate_content_rule(rule, {}, None)["pending"] is True
    assert (
        rr.evaluate_content_rule(rule, {}, [])["status"] == "complete"
    )  # no files: not applicable
    assert rr.evaluate_content_rule(rule, {}, [{"path": "data/README.md"}])["status"] == "complete"
    assert (
        rr.evaluate_content_rule(rule, {}, [{"path": "data/myreadme_data.csv"}])["status"]
        == "incomplete"
    )


def test_filename_glob_case_sensitive_skips_legacy_fallback() -> None:
    rule = {
        "id": "r",
        "label": "R",
        "level": "required",
        "requirement": "R",
        "scope": ["filenames"],
        "match": "filename-glob",
        "pattern": "readme*",
        "case_sensitive": True,
        "response_template": "",
    }
    # "README.md" does not match case-sensitive "readme*", and the legacy
    # case-insensitive basename fallback must not rescue it.
    assert rr.evaluate_content_rule(rule, {}, [{"path": "README.md"}])["status"] == "incomplete"
    assert rr.evaluate_content_rule(rule, {}, [{"path": "readme.txt"}])["status"] == "complete"


def test_filename_glob_with_slash_matches_full_path() -> None:
    rule = {
        "id": "r",
        "label": "R",
        "level": "required",
        "requirement": "R",
        "scope": ["filenames"],
        "match": "filename-glob",
        "pattern": "docs/*.md",
        "case_sensitive": False,
        "response_template": "",
    }
    assert rr.evaluate_content_rule(rule, {}, [{"path": "docs/guide.md"}])["status"] == "complete"
    assert (
        rr.evaluate_content_rule(rule, {}, [{"path": "other/guide.md"}])["status"] == "incomplete"
    )


def test_content_rule_metadata_scope() -> None:
    rule = {
        "id": "x",
        "label": "X",
        "level": "required",
        "requirement": "R",
        "scope": ["metadata"],
        "match": "substring",
        "pattern": "funding",
        "case_sensitive": False,
        "response_template": "",
    }
    meta = _meta([_f("notesText", "Funding acknowledgement: NSF grant")])
    assert rr.evaluate_content_rule(rule, meta, [])["status"] == "complete"
    assert rr.evaluate_content_rule(rule, _meta([]), [])["status"] == "incomplete"


def test_content_rule_file_content_pending_without_staged(tmp_path: Path) -> None:
    rule = {
        "id": "x",
        "label": "X",
        "level": "required",
        "requirement": "R",
        "scope": ["file-content"],
        "match": "substring",
        "pattern": "hello",
        "case_sensitive": False,
        "response_template": "",
    }
    assert (
        rr.evaluate_content_rule(rule, {}, [], staged_dir=tmp_path / "missing")["pending"] is True
    )


def test_content_rule_file_content_match(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("hello world", encoding="utf-8")
    rule = {
        "id": "x",
        "label": "X",
        "level": "required",
        "requirement": "R",
        "scope": ["file-content"],
        "match": "substring",
        "pattern": "hello",
        "case_sensitive": False,
        "response_template": "",
    }
    assert rr.evaluate_content_rule(rule, {}, [], staged_dir=tmp_path)["status"] == "complete"


def test_field_rule_ids_unique_per_handler() -> None:
    rs = copy.deepcopy(rr.get_ruleset("mcmaster-default"))
    res = rr.evaluate_ruleset(_meta([]), rs, [])
    ids = [r["rule_id"] for r in res]
    assert len(ids) == len(set(ids)), ids


def test_author_count_handler_bounds_and_display() -> None:
    rs = copy.deepcopy(rr.get_ruleset("mcmaster-default"))
    # Configure min/max on the Author count rule.
    for fr in rs["field_rules"]:
        if fr.get("handler") == "author_count":
            fr["min"] = 2
            fr["max"] = 5
    meta = _meta(
        [
            _f(
                "author",
                [
                    {"authorName": {"value": "A"}},
                    {"authorName": {"value": "B"}},
                ],
            ),
        ]
    )
    res = rr.evaluate_ruleset(meta, rs, [])
    ac = next(r for r in res if r["rule_id"].endswith(":author_count"))
    assert ac["status"] == "complete"
    assert "2 author" in ac["value"]
    # Below min → incomplete.
    meta1 = _meta([_f("author", [{"authorName": {"value": "A"}}])])
    res1 = rr.evaluate_ruleset(meta1, rs, [])
    ac1 = next(r for r in res1 if r["rule_id"].endswith(":author_count"))
    assert ac1["status"] == "incomplete"
    assert ac1["level"] == "optional"


def test_license_terms_handler_reads_version_surface() -> None:
    rs = copy.deepcopy(rr.get_ruleset("mcmaster-default"))
    meta = _meta([])
    meta["latestVersion"]["termsOfUse"] = {"value": "CC BY 4.0 attribution"}
    meta["latestVersion"]["termsOfAccess"] = {"value": "contact curator"}
    res = rr.evaluate_ruleset(meta, rs, [])
    lt = next(r for r in res if r["rule_id"].endswith(":license_terms"))
    assert lt["status"] == "complete"  # license CC0 present in _meta()
    assert "CC0" in lt["value"]
    assert "CC BY 4.0" in lt["value"]
    assert "contact curator" in lt["value"]


def test_orcid_handler_requires_every_author() -> None:
    rs = copy.deepcopy(rr.get_ruleset("mcmaster-default"))
    meta = _meta(
        [
            _f(
                "author",
                [
                    {
                        "authorName": {"value": "A"},
                        "authorIdentifierScheme": {"value": "ORCID"},
                        "authorIdentifier": {"value": "0000-0002-1825-0097"},
                    },
                    {"authorName": {"value": "B"}},
                ],
            ),
        ]
    )
    res = rr.evaluate_ruleset(meta, rs, [])
    orc = next(r for r in res if r["rule_id"].endswith(":orcid"))
    assert orc["status"] == "incomplete"
    assert "B" in orc["value"]  # missing author named
    # Both valid → complete.
    meta2 = _meta(
        [
            _f(
                "author",
                [
                    {
                        "authorName": {"value": "A"},
                        "authorIdentifierScheme": {"value": "ORCID"},
                        "authorIdentifier": {"value": "0000-0002-1825-0097"},
                    },
                    {
                        "authorName": {"value": "B"},
                        "authorIdentifierScheme": {"value": "ORCID"},
                        "authorIdentifier": {"value": "0000-0001-5109-3700"},
                    },
                ],
            ),
        ]
    )
    res2 = rr.evaluate_ruleset(meta2, rs, [])
    orc2 = next(r for r in res2 if r["rule_id"].endswith(":orcid"))
    assert orc2["status"] == "complete"


def test_orcid_dotted_identifier_rule_complete_and_incomplete() -> None:
    """Builtin mcmaster ORCID rule now targets author.authorIdentifier."""
    rs = copy.deepcopy(rr.get_ruleset("mcmaster-default"))
    orc_rules = [r for r in rs["field_rules"] if r.get("handler") == "orcid"]
    assert orc_rules, "mcmaster must carry an ORCID rule"
    assert orc_rules[0]["field"] == "author.authorIdentifier"
    meta = _meta(
        [
            _f(
                "author",
                [
                    {
                        "authorName": {"value": "A"},
                        "authorIdentifierScheme": {"value": "ORCID"},
                        "authorIdentifier": {"value": "0000-0002-1825-0097"},
                    },
                    {"authorName": {"value": "B"}},
                ],
            ),
        ]
    )
    res = rr.evaluate_ruleset(meta, rs, [])
    orc = next(r for r in res if r["rule_id"].endswith(":orcid"))
    assert orc["status"] == "incomplete"
    assert "B" in orc["value"]
    assert orc["rule_id"] == "field:citation.author.authorIdentifier:orcid"
    meta2 = _meta(
        [
            _f(
                "author",
                [
                    {
                        "authorName": {"value": "A"},
                        "authorIdentifierScheme": {"value": "ORCID"},
                        "authorIdentifier": {"value": "0000-0002-1825-0097"},
                    },
                ],
            ),
        ]
    )
    res2 = rr.evaluate_ruleset(meta2, rs, [])
    orc2 = next(r for r in res2 if r["rule_id"].endswith(":orcid"))
    assert orc2["status"] == "complete"


def test_dotted_nonempty_rule_requires_every_identifier() -> None:
    ruleset = {
        "label": "t",
        "description": "",
        "dataverses": ["*"],
        "field_rules": [
            {
                "block": "citation",
                "field": "author.authorIdentifier",
                "label": "Identifier",
                "handler": "nonempty",
                "level": "required",
                "requirement": "",
                "response_template": "",
            },
        ],
        "content_rules": [],
        "filecheck_templates": {"*": "{check_id}: {message}"},
        "response_header": "",
        "response_footer": "",
    }
    meta = _meta(
        [
            _f(
                "author",
                [
                    {"authorName": {"value": "A"}, "authorIdentifier": {"value": "X"}},
                    {"authorName": {"value": "B"}},
                ],
            ),
        ]
    )
    res = rr.evaluate_ruleset(meta, ruleset, [])
    r = next(x for x in res if x["block"] == "citation")
    assert r["status"] == "incomplete"
    meta2 = _meta(
        [
            _f(
                "author",
                [
                    {"authorName": {"value": "A"}, "authorIdentifier": {"value": "X"}},
                    {"authorName": {"value": "B"}, "authorIdentifier": {"value": "Y"}},
                ],
            ),
        ]
    )
    res2 = rr.evaluate_ruleset(meta2, ruleset, [])
    r2 = next(x for x in res2 if x["block"] == "citation")
    assert r2["status"] == "complete"
    assert "X" in r2["value"]
    assert "Y" in r2["value"]


def test_legacy_orcid_field_author_migrates_on_load() -> None:
    merged = rr._normalize_ruleset(
        "legacy",
        {
            "field_rules": [
                {
                    "block": "citation",
                    "field": "author",
                    "label": "ORCiD for authors",
                    "handler": "orcid",
                    "level": "optional",
                    "requirement": "",
                    "response_template": "",
                },
            ]
        },
    )
    assert merged is not None
    assert merged["field_rules"][0]["field"] == "author.authorIdentifier"


def test_rulesets_for_dataverse_wildcard() -> None:
    pool = rr.load_rulesets()
    assert any(
        k == "mcmaster-default"
        for k, _ in rr.rulesets_for_dataverse("https://demo.borealisdata.ca", pool)
    )


def test_save_load_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from curation import review_rules as _rr

    target = tmp_path / "requirements_profiles.json"
    monkeypatch.setattr(_rr, "rulesets_path", lambda: target)
    monkeypatch.setattr(_rr, "_RULESETS_MEMO", {})
    pool = _rr.load_rulesets()
    pool["lab"] = dict(pool["mcmaster-default"])
    pool["lab"]["dataverses"] = ["https://example.invalid"]
    _rr.save_rulesets(pool)
    assert _rr.load_rulesets()["lab"]["dataverses"] == ["https://example.invalid"]


def test_load_memoized_and_invalidated_on_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from curation import review_rules as _rr

    target = tmp_path / "requirements_profiles.json"
    monkeypatch.setattr(_rr, "rulesets_path", lambda: target)
    monkeypatch.setattr(_rr, "_RULESETS_MEMO", {})
    first = _rr.load_rulesets()
    assert _rr.load_rulesets() is first  # no disk re-read
    pool = dict(first)
    pool["lab2"] = dict(first["mcmaster-default"])
    _rr.save_rulesets(pool)
    assert "lab2" in _rr.load_rulesets()


def test_deleted_ruleset_leaves_profiles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from curation import review_rules as _rr

    target = tmp_path / "requirements_profiles.json"
    monkeypatch.setattr(_rr, "rulesets_path", lambda: target)
    monkeypatch.setattr(_rr, "_RULESETS_MEMO", {})
    from curation import metadata_check as _mc

    pool = _rr.load_rulesets()
    pool["temp-custom"] = dict(pool["mcmaster-default"])
    _rr.save_rulesets(pool)
    _mc.refresh_profiles_from_rulesets()
    assert "temp-custom" in _mc.PROFILES
    del pool["temp-custom"]
    _rr.save_rulesets(pool)
    _mc.refresh_profiles_from_rulesets()
    assert "temp-custom" not in _mc.PROFILES
    assert "McMaster" in _mc.PROFILES
    assert "Minimal" in _mc.PROFILES
