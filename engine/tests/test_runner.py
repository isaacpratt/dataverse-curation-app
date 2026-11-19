"""Tests for the report runner (dispatcher -> checks -> DatasetReport)."""

from pathlib import Path

import pytest

from engine.runner import run_report, run_report_to_file

CUR_DATA = Path(__file__).resolve().parents[3] / "CUR_Res_CurationTools" / "data"


def _make_staged(tmp_path: Path) -> Path:
    staged = tmp_path / "staged"
    (staged / "data").mkdir(parents=True)
    (staged / "data" / "table.csv").write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
    (staged / "broken.json").write_text("{not valid json", encoding="utf-8")
    (staged / "notes.txt").write_text("hello\n", encoding="utf-8")
    (staged / "unknown.bin").write_bytes(b"\x00\x01\x02")
    return staged


def test_run_report_on_synthetic(tmp_path: Path) -> None:
    staged = _make_staged(tmp_path)

    report = run_report(staged, persistent_id="doi:10.5072/FK2/TEST")

    assert report.persistent_id == "doi:10.5072/FK2/TEST"
    assert len(report.files) == 4

    by_path = {entry.path: entry for entry in report.files}

    csv_entry = by_path["data/table.csv"]
    csv_ids = {c.check_id for c in csv_entry.checks}
    assert "format.csv.openable" in csv_ids
    assert all(c.passed for c in csv_entry.checks if c.check_id == "format.csv.structure")

    json_entry = by_path["broken.json"]
    json_valid = next(c for c in json_entry.checks if c.check_id == "format.json.valid")
    assert not json_valid.passed
    assert json_valid.level == "error"

    bin_entry = by_path["unknown.bin"]
    assert bin_entry.checks == []
    assert bin_entry.mime_type

    inventory = next(c for c in report.dataset_checks if c.check_id == "inventory.extensions")
    assert inventory.passed


def test_report_roundtrip_via_file(tmp_path: Path) -> None:
    staged = _make_staged(tmp_path)
    out = tmp_path / "report.json"

    saved = run_report_to_file(staged, out, persistent_id="pid:x")
    loaded = type(saved).load(out)
    assert loaded == saved


@pytest.mark.samples
@pytest.mark.skipif(not CUR_DATA.exists(), reason="sample data not found")
def test_run_report_on_cur_gpkg_samples() -> None:
    report = run_report(CUR_DATA / "Inspect_gpkg")

    gpkg_entries = [f for f in report.files if f.path.endswith(".gpkg")]
    assert gpkg_entries
    for entry in gpkg_entries:
        ids = {c.check_id for c in entry.checks}
        assert "format.gpkg.valid" in ids
        valid = next(c for c in entry.checks if c.check_id == "format.gpkg.valid")
        assert valid.passed
