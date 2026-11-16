"""Dataset-level access check: restricted/embargoed files + terms of access."""

import review_rules as rr
from engine.checks.access_check import AccessCheck
from engine.runner import run_report


def _inventory():
    return [
        {"path": "data/open.csv"},
        {
            "path": "data/restricted.csv",
            "restricted": True,
            "embargo_date": "2027-06-01",
        },
        {"path": "data/embargoed.csv", "embargo_date": "2028-01-15"},
    ]


def _metadata(terms="Contact the curator for access"):
    return {"latestVersion": {"termsOfAccess": {"value": terms}}}


def test_access_check_names_restricted_and_embargoed_files():
    results = AccessCheck().run_dataset([], {"inventory": _inventory(), "metadata": _metadata()})
    by_id = {r.check_id: r for r in results}

    restricted = by_id["inventory.restricted_files"]
    assert not restricted.passed
    assert restricted.level == "warning"
    assert "data/restricted.csv" in restricted.message
    assert "Contact the curator for access" in restricted.message

    embargoed = by_id["inventory.embargoed_files"]
    assert not embargoed.passed
    assert "data/restricted.csv (until 2027-06-01)" in embargoed.message
    assert "data/embargoed.csv (until 2028-01-15)" in embargoed.message
    assert "Contact the curator for access" in embargoed.message
    assert embargoed.details["dates"] == ["2027-06-01", "2028-01-15"]


def test_access_check_without_inventory_is_skipped_not_passed():
    results = AccessCheck().run_dataset([], None)
    by_id = {r.check_id: r for r in results}
    assert set(by_id) == {"inventory.restricted_files", "inventory.embargoed_files"}
    assert all(r.passed for r in results)
    assert all(r.details.get("skipped") for r in results)


def test_access_check_clean_inventory_passes():
    results = AccessCheck().run_dataset([], {"inventory": [{"path": "data/open.csv"}]})
    assert all(r.passed for r in results)
    assert all("No restricted" in r.message or "No embargoed" in r.message for r in results)


def test_run_report_wires_access_context():
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        staged = Path(tmp)
        (staged / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")
        report = run_report(
            staged,
            inventory=_inventory(),
            metadata=_metadata(),
        )
    by_id = {c.check_id: c for c in report.dataset_checks}
    assert by_id["inventory.restricted_files"].details["count"] == 1
    assert by_id["inventory.embargoed_files"].details["count"] == 2
    assert "Terms of access" in by_id["inventory.embargoed_files"].message


def test_ruleset_access_rule_presents_embargo_and_terms():
    rs = rr.get_ruleset("mcmaster-default")
    rule = next(fr for fr in rs["field_rules"] if fr.get("handler") == "access_conditions")
    assert rule["field"] == "termsOfAccess"
    assert rule["level"] == "optional"

    meta = {
        "latestVersion": {
            "metadataBlocks": {"citation": {"fields": []}},
            "termsOfAccess": {"value": "Contact the curator"},
        }
    }
    evaluated = rr.evaluate_ruleset(meta, rs, _inventory())
    found = next(r for r in evaluated if r["rule_id"].endswith(":access_conditions"))
    assert found["status"] == "complete"
    assert "restricted" in found["value"]
    assert "2027-06-01" in found["value"]
    assert "Contact the curator" in found["value"]


def test_response_draft_uses_access_templates():
    from engine.report import DatasetReport
    from response_draft import build_response

    results = AccessCheck().run_dataset([], {"inventory": _inventory(), "metadata": _metadata()})
    report = DatasetReport(
        persistent_id="doi:1", label="x", engine_version="t", dataset_checks=results
    )
    md, sections = build_response(rr.get_ruleset("mcmaster-default"), [], report)
    ids = [s["id"] for s in sections]
    assert any("inventory.restricted_files" in i for i in ids)
    assert any("inventory.embargoed_files" in i for i in ids)
    assert "2027-06-01" in md
    assert "Contact the curator for access" in md


def test_ruleset_access_rule_flags_missing_terms():
    rs = rr.get_ruleset("mcmaster-default")
    meta = {"latestVersion": {"metadataBlocks": {"citation": {"fields": []}}}}
    evaluated = rr.evaluate_ruleset(meta, rs, _inventory())
    found = next(r for r in evaluated if r["rule_id"].endswith(":access_conditions"))
    assert found["status"] == "incomplete"
    assert found["level"] == "optional"
    assert "Terms of access: not set" in found["value"]
