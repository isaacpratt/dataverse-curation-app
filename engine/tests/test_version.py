"""Version single-sourcing: one literal feeds the package metadata and the runtime.

pyproject.toml carries the PEP 621 version for packaging tools; engine.__version__
carries it for the running app (About pane, report engine_version). They must
always agree, so they are pinned to the same value here and checked in CI.

Canonical bump procedure: bump BOTH to the same literal in one commit; the
consistency test fails otherwise.
"""

import tomllib
from pathlib import Path

import engine

_PYPROJECT = Path(__file__).resolve().parent.parent.parent / "pyproject.toml"


def test_version_is_semver_ish() -> None:
    parts = engine.__version__.split(".")
    assert len(parts) == 3
    assert all(part.isdigit() for part in parts)


def test_pyproject_and_engine_agree() -> None:
    with _PYPROJECT.open("rb") as fh:
        meta = tomllib.load(fh)
    assert meta["project"]["version"] == engine.__version__


def test_report_version_matches(tmp_path: Path) -> None:
    from engine.report import DatasetReport

    report = DatasetReport(persistent_id="doi:x", label="t", engine_version=engine.__version__)
    assert report.to_dict()["engine_version"] == engine.__version__
