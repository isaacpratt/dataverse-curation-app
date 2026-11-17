"""Curation record export (dv-vwt): folder structure, index binding, dated re-runs, and the headless wiring."""

import hashlib
import json

from curation_record import export_record
from engine.checks.base import CheckResult
from engine.report import DatasetReport, FileEntry
from curation.storage import AppState


def _report():
    return DatasetReport(
        persistent_id="doi:10.5072/FK2/EXAMPLE",
        label="Example",
        engine_version="test",
        files=[
            FileEntry(path="a.csv", size_bytes=3, mime_type="text/csv",
                      checks=[CheckResult("format.csv.content", "info", True, "parsed")]),
        ],
    )


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestExportRecord:
    def test_full_bundle(self, tmp_path):
        staged = tmp_path / "staged"
        staged.mkdir()
        (staged / "a.csv").write_text("a,b\n1,2\n", encoding="utf-8")
        (staged / "doc.md").write_text("# doc", encoding="utf-8")
        st = AppState(tmp_path / "state.db")
        key = "0123456789abcdef0123456789abcdef01234567"
        st.set_finding_disposition("pid", key, "wontfix", "contact person")
        st.set_sensitivity_review("pid", {"human-subjects": "yes"})

        record = export_record(
            tmp_path / "dataset",
            report=_report(),
            response_text="Dear depositor…",
            actions=st.list_actions("pid", limit=500),
            dispositions=st.list_finding_dispositions("pid"),
            sensitivity=st.get_sensitivity_review("pid"),
            decision="Approve — clean",
            curation_label="Approved",
            staged_dir=staged,
        )
        names = {p.name for p in record.iterdir()}
        assert {
            "index.json", "checks_report.json", "checks_report.md",
            "depositor_response.md", "curation_log.md", "dispositions.json",
            "sensitivity.json", "decision.json", "sha256sums.txt",
        } <= names
        index = json.loads((record / "index.json").read_text(encoding="utf-8"))
        assert index["persistent_id"] == "doi:10.5072/FK2/EXAMPLE"
        assert index["curation_label"] == "Approved"
        assert index["disposition_count"] == 1
        assert index["sensitivity_answered"] == 1
        assert index["staged_files"] == 2
        # The index binds every artifact by sha256.
        for artifact, digest in index["artifacts"].items():
            assert digest == _sha(record / artifact), artifact
        # The staged manifest covers both files, sorted.
        manifest = (record / "sha256sums.txt").read_text(encoding="utf-8")
        assert "a.csv" in manifest and "doc.md" in manifest
        assert manifest.index("a.csv") < manifest.index("doc.md")
        # Dispositions + sensitivity round-trip through the JSON artifacts.
        disp = json.loads((record / "dispositions.json").read_text(encoding="utf-8"))
        assert disp[key]["note"] == "contact person"
        sens = json.loads((record / "sensitivity.json").read_text(encoding="utf-8"))
        assert sens["answers"]["human-subjects"] == "yes"
        st.close()

    def test_partial_review_still_exports(self, tmp_path):
        """No report, no dispositions: the record carries what exists."""
        record = export_record(tmp_path / "dataset", response_text="")
        names = {p.name for p in record.iterdir()}
        assert "checks_report.json" not in names
        assert "depositor_response.md" not in names
        assert "curation_log.md" in names
        assert (record / "sha256sums.txt").read_text(encoding="utf-8") == "\n"

    def test_rerun_creates_dated_sibling(self, tmp_path):
        first = export_record(tmp_path / "dataset", response_text="v1")
        second = export_record(tmp_path / "dataset", response_text="v2")
        assert first != second
        assert first.parent == second.parent
        # The earlier record is untouched.
        assert "v1" in (first / "depositor_response.md").read_text(encoding="utf-8")

    def test_log_markdown_renders_actions(self, tmp_path):
        st = AppState(tmp_path / "state.db")
        st.log_action("pid", "downloaded", notes="12 files")
        record = export_record(
            tmp_path / "dataset", actions=st.list_actions("pid", limit=100)
        )
        log = (record / "curation_log.md").read_text(encoding="utf-8")
        assert "[curator] downloaded — 12 files" in log
        st.close()
