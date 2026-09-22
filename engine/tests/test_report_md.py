"""Tests for the Markdown derived view (engine.report_md)."""

from pathlib import Path

from engine.report import DatasetReport
from engine.runner import run_report


def _make_staged(tmp_path: Path) -> Path:
    staged = tmp_path / "staged"
    (staged / "data").mkdir(parents=True)
    (staged / "data" / "table.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (staged / "notes.txt").write_text("hello\n", encoding="utf-8")
    return staged


def test_markdown_shows_passes_and_inventory(tmp_path):
    report = run_report(_make_staged(tmp_path), persistent_id="doi:10/x")
    md = report.to_markdown()
    assert "# Curation report" in md
    assert "inventory.zero_byte" in md
    assert "No zero-byte files" in md
    assert "format.csv.pii" in md
    assert "no email addresses" in md
    assert "JSON is canonical" in md


def test_markdown_roundtrip_via_files(tmp_path):
    report = run_report(_make_staged(tmp_path), persistent_id="doi:10/x")
    out_json = tmp_path / "r.json"
    out_md = tmp_path / "r.md"
    report.save(out_json)
    report.save_markdown(out_md)
    loaded = DatasetReport.load(out_json)
    assert loaded == report
    text = out_md.read_text(encoding="utf-8")
    assert "## Files" in text
    assert "data/table.csv" in text


def test_markdown_skipped_renders_skipped(tmp_path, monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "pypdf", None)
    staged = tmp_path / "staged"
    staged.mkdir()
    (staged / "doc.pdf").write_bytes(b"%PDF-1.4 garbage")
    report = run_report(staged)
    md = report.to_markdown()
    assert "SKIPPED" in md
    assert "Skipped" in md or "skipped" in md
