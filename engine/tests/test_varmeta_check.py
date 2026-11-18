"""Variable-metadata coverage check + dictionary draft (dv-tfy)."""

import csv
from pathlib import Path

from engine.checks.varmeta_check import (
    DRAFT_COLUMNS,
    VarCoverageCheck,
    coverage_of,
    write_dictionary_draft,
)
from engine.runner import run_report


def _inventory():
    return [
        {"path": "data/survey.tab", "tabular": True},
        {"path": "data/readme.txt"},
        {"path": "data/undocumented.tab", "tabular": True},
    ]


def _variables():
    return {
        "data/survey.tab": {
            "age": {"label": "Age in years", "type": "numeric"},
            "sex": {"label": "Sex", "type": "categorical"},
            "income": {"label": "", "type": "numeric"},
        },
    }


def test_coverage_of_counts_labels():
    assert coverage_of(_variables()["data/survey.tab"]) == (2, 3)
    assert coverage_of({}) is None
    assert coverage_of(None) is None
    assert coverage_of({"x": {"label": "  "}}) == (0, 1)


def test_var_coverage_flags_undocumented_tabular_file():
    inventory = [
        {"path": "data/survey.tab", "tabular": True},
        {"path": "data/partial.tab", "tabular": True},
        {"path": "data/undocumented.tab", "tabular": True},
    ]
    variables = dict(_variables())
    variables["data/partial.tab"] = {
        "a": {"label": "A", "type": "text"},
        "b": {"label": "", "type": "text"},
        "c": {"label": "", "type": "text"},
        "d": {"label": "", "type": "text"},
    }
    results = VarCoverageCheck().run_dataset(
        [], {"inventory": inventory, "variable_metadata": variables}
    )
    warnings = [r for r in results if not r.passed]
    assert warnings
    undocumented = next(r for r in warnings if "data/undocumented.tab" in r.message)
    assert undocumented.details["count"] == 1
    # Partial labels ride a second warning when under half are labeled.
    assert any("under half" in r.message for r in warnings)


def test_var_coverage_all_documented_passes():
    inventory = [{"path": "data/survey.tab", "tabular": True}]
    results = VarCoverageCheck().run_dataset(
        [], {"inventory": inventory, "variable_metadata": _variables()}
    )
    assert all(r.passed for r in results)
    assert "all 1 tabular file" in results[0].message


def test_var_coverage_details_carry_maps():
    results = VarCoverageCheck().run_dataset(
        [], {"inventory": _inventory(), "variable_metadata": _variables()}
    )
    details = results[0].details
    assert details["coverage"]["data/survey.tab"] == {"labeled": 2, "total": 3}
    assert details["variables"]["data/survey.tab"]["age"]["label"] == "Age in years"
    assert details["variables"]["data/survey.tab"]["age"]["type"] == "numeric"


def test_var_coverage_without_inventory_is_skipped_not_passed():
    results = VarCoverageCheck().run_dataset([], None)
    assert len(results) == 1
    assert results[0].passed
    assert results[0].details["skipped"] is True
    assert results[0].details["required"] == "inventory"


def test_var_coverage_no_tabular_files_not_applicable():
    results = VarCoverageCheck().run_dataset([], {"inventory": [{"path": "readme.txt"}]})
    assert results[0].passed
    assert results[0].details["tabular_files"] == 0


def test_write_dictionary_draft_round_trips():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        out = write_dictionary_draft(Path(tmp) / "draft.csv", _variables()["data/survey.tab"])
        assert out.exists()
        with open(out, newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.reader(handle))
    assert tuple(rows[0]) == DRAFT_COLUMNS
    names = [r[0] for r in rows[1:]]
    assert names == ["age", "income", "sex"]  # sorted
    age = next(r for r in rows[1:] if r[0] == "age")
    assert age[1] == "Age in years"
    assert age[2] == "numeric"


def test_run_report_wires_variable_metadata():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        staged = Path(tmp)
        (staged / "data").mkdir()
        (staged / "data" / "survey.tab").write_text("a,b\n1,2\n", encoding="utf-8")
        report = run_report(
            staged,
            inventory=[{"path": "data/survey.tab", "tabular": True}],
            variable_metadata={"data/survey.tab": {"a": {"label": "Alpha"}}},
        )
    by_id = {c.check_id: c for c in report.dataset_checks}
    result = by_id["metadata.var_coverage"]
    assert result.details["coverage"]["data/survey.tab"] == {"labeled": 1, "total": 1}


_DDI = """<?xml version="1.0" encoding="UTF-8"?>
<codeBook xmlns="http://www.icpsr.umich.edu/DDI">
  <dataDscr>
    <var name="age" intrvl="contin">
      <labl>Age in years</labl>
    </var>
    <var name="sex" intrvl="discrete">
      <labl></labl>
    </var>
  </dataDscr>
</codeBook>
"""


def test_client_parses_per_file_ddi():
    from curation.client import DataverseClient

    client = DataverseClient.__new__(DataverseClient)
    client._get_text = lambda _path, **_kw: _DDI  # type: ignore[method-assign]
    meta = client.get_variable_metadata("123")
    assert meta == {
        "age": {"label": "Age in years", "type": "contin"},
        "sex": {"label": "", "type": "discrete"},
    }


def test_client_returns_none_on_bad_ddi():
    from curation.client import DataverseClient

    client = DataverseClient.__new__(DataverseClient)
    client._get_text = lambda _path, **_kw: "not xml"  # type: ignore[method-assign]
    assert client.get_variable_metadata("123") is None
