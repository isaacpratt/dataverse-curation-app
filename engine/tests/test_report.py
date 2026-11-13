"""Tests for the report contract JSON round-trip."""

from engine.checks.base import CheckResult
from engine.report import DatasetReport, FileEntry


def test_report_roundtrip() -> None:
    report = DatasetReport(
        persistent_id="doi:10.5072/FK2/EXAMPLE",
        label="Example dataset",
        engine_version="0.1.0",
        dataset_checks=[
            CheckResult(
                check_id="inventory.extensions",
                level="info",
                passed=True,
                message="Inventory scanned",
                details={"files": 1},
            )
        ],
        files=[
            FileEntry(
                path="data/raw.csv",
                size_bytes=12345,
                mime_type="text/csv",
                checks=[
                    CheckResult(
                        check_id="format.csv.structure",
                        level="warning",
                        passed=False,
                        message="Mixed line endings",
                    )
                ],
            )
        ],
    )

    restored = DatasetReport.from_dict(report.to_dict())
    assert restored == report
