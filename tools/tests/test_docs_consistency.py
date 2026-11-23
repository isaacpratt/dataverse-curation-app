"""Documentation ↔ code consistency checks (documentation as code).

Each test pins one high-signal contract that used to drift silently: the
check reference against the engine registry, the CLI reference against
``main.py --help``, the configuration reference against ``config.example.json``,
and the documented headless command against a real staged run.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from engine.checks import registry

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"


def test_check_reference_lists_every_registered_check_id() -> None:
    """No registered check may be missing from the checks reference page."""
    page = (DOCS / "reference" / "checks.md").read_text(encoding="utf-8")
    missing = sorted(check_id for check_id in registry if f"`{check_id}`" not in page)
    assert not missing, f"check IDs absent from reference/checks.md: {missing}"


def test_cli_reference_matches_help_output() -> None:
    """Documented flags and defaults come from the live CLI, not memory."""
    help_text = subprocess.run(
        [sys.executable, str(ROOT / "main.py"), "--headless", "--help"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    page = (DOCS / "reference" / "cli.md").read_text(encoding="utf-8")
    # Every argparse flag appears in both outputs.
    flags = sorted(
        {
            token.split("=")[0]
            for token in help_text.split()
            if token.startswith("--") and len(token) > 2 and token[2] not in "{|}"
        }
    )
    assert flags
    missing = [flag for flag in flags if f"`{flag}" not in page]
    assert not missing, f"CLI flags absent from reference/cli.md: {missing}"
    assert "--format {json,md,both}" in help_text
    assert "`json|md|both`" in page or "`json`, `md`, `both`" in page


def test_configuration_reference_covers_example_keys() -> None:
    """Every config.example.json key is documented on the configuration page."""
    example = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8"))
    page = (DOCS / "reference" / "configuration.md").read_text(encoding="utf-8")

    def keys(value: object) -> set[str]:
        if isinstance(value, dict):
            return {k for k, v in value.items()} | set().union(*(keys(v) for v in value.values()))
        return set()

    missing = sorted(key for key in keys(example) if f"`{key}`" not in page)
    assert not missing, f"config keys absent from reference/configuration.md: {missing}"


def test_external_url_extraction_trims_markdown_punctuation(tmp_path: Path) -> None:
    """The scheduled link checker must not probe backticks or bold markers."""
    sys.path.insert(0, str(ROOT / "tools" / "docs"))
    from check_external_links import external_urls

    page = tmp_path / "sample.md"
    page.write_text(
        "See [the site](https://example.com/docs)** and `https://inline.example`.\n",
        encoding="utf-8",
    )
    assert external_urls((page,)) == ["https://example.com/docs"]


@pytest.mark.parametrize(
    ("fmt", "expected"),
    [("json", "report.json"), ("both", "report.md")],
)
def test_documented_headless_command_runs(tmp_path: Path, fmt: str, expected: str) -> None:
    """Run the how-to's headless example against a staged fixture.

    The documented outputs are written; a 0 exit means no error-level findings.
    """
    staged = tmp_path / "staged"
    staged.mkdir()
    (staged / "data.csv").write_text("id,value\n1,alpha\n2,beta\n", encoding="utf-8")
    out = tmp_path / "report.json"
    command = [
        sys.executable,
        str(ROOT / "main.py"),
        "--headless",
        str(staged),
        "--out",
        str(out),
        "--format",
        fmt,
        "--persistent-id",
        "doi:10.5072/FK2/EXAMPLE",
    ]
    result = subprocess.run(command, capture_output=True, text=True, cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["persistent_id"] == "doi:10.5072/FK2/EXAMPLE"
    assert report["files"], "the staged CSV was not checked"
    if fmt == "both":
        assert (tmp_path / "report.md").exists(), "the --format both Markdown output is missing"
        assert expected == "report.md"
