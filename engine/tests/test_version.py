"""One version, one tag: `engine.__version__` is the only literal.

The release workflow refuses a tag that disagrees with it, and
`tools/build/check_version.py` is that gate - run here exactly as CI runs it.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

import engine
from engine import version as version_mod

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "build" / "check_version.py"


def test_version_is_semver() -> None:
    major, minor, patch, prerelease = version_mod.parse(engine.__version__)
    assert (major, minor, patch) >= (0, 0, 0)
    assert isinstance(prerelease, str)


def test_pyproject_does_not_duplicate_the_version() -> None:
    tomllib = pytest.importorskip("tomllib")  # 3.11+; 3.10 dev boxes skip
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = data["project"]
    assert "version" not in project, "the version must live only in engine/__init__.py"
    assert project["dynamic"] == ["version"]
    assert data["tool"]["setuptools"]["dynamic"]["version"]["attr"] == "engine.__version__"


def test_tag_matching_the_build_is_accepted() -> None:
    assert version_mod.tag_error(f"v{engine.__version__}") == ""
    # A bare version is a legal tag too.
    assert version_mod.tag_error(engine.__version__) == ""


def test_tag_for_another_version_is_refused() -> None:
    problem = version_mod.tag_error("v9.9.9")
    assert "9.9.9" in problem
    assert engine.__version__ in problem


@pytest.mark.parametrize(
    "tag", ["0.2", "v0.2", "release-0.2.0", "v0.2.0.1", "v01.2.3", "v0.2.0rc1"]
)
def test_malformed_tags_are_refused(tag: str) -> None:
    assert version_mod.tag_error(tag)


def test_prerelease_versions_pick_the_beta_channel() -> None:
    assert version_mod.is_prerelease("0.2.0-beta.1")
    assert not version_mod.is_prerelease("0.2.0")
    assert version_mod.parse("1.2.3-rc.1+build.5") == (1, 2, 3, "rc.1")
    assert version_mod.tag_version("V0.2.0-rc.1") == "0.2.0-rc.1"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.pop("GITHUB_REF_NAME", None)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )


def test_script_accepts_the_matching_tag() -> None:
    result = _run("--tag", f"v{engine.__version__}")
    assert result.returncode == 0, result.stderr
    assert "matches tag" in result.stdout


def test_script_fails_on_a_mismatched_tag() -> None:
    result = _run("--tag", "v9.9.9")
    assert result.returncode == 1
    assert "version check failed" in result.stderr


def test_script_needs_a_tag() -> None:
    result = _run("--tag", "")
    assert result.returncode == 2
    assert "no tag to check" in result.stderr


def test_script_reads_github_ref_name() -> None:
    env = dict(os.environ)
    env["GITHUB_REF_NAME"] = f"v{engine.__version__}"
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
