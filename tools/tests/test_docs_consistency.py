"""Documentation ↔ code consistency checks (documentation as code).

Each test pins one high-signal contract that used to drift silently: the
check reference against the engine registry, the CLI reference against
``main.py --help``, the configuration reference against ``config.example.json``,
and the documented headless command against a real staged run.
"""

from __future__ import annotations

import json
import re
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


def test_cli_reference_matches_argparse() -> None:
    """The published CLI block is generated from, and matches, the real CLI."""
    sys.path.insert(0, str(ROOT / "tools" / "docs"))
    from gen_cli_reference import check, render_reference

    page = (DOCS / "reference" / "cli.md").read_text(encoding="utf-8")
    assert check(), "run `poe docs-gen-cli` to regenerate the CLI reference"
    block = render_reference()
    assert block in page

    help_text = subprocess.run(
        [sys.executable, str(ROOT / "main.py"), "--headless", "--help"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert help_text.strip() in block
    assert all(
        f"`{flag}`" in block
        for flag in (
            "--headless",
            "--gallery",
            "--out",
            "--format",
            "--persistent-id",
            "--export-record",
            "--config",
            "--dataverse",
        )
    )


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


def test_check_id_index_matches_registry() -> None:
    """The generated Check ID index must not drift from the engine registry."""
    sys.path.insert(0, str(ROOT / "tools" / "docs"))
    from gen_checks_reference import check, render_index

    page = (DOCS / "reference" / "checks.md").read_text(encoding="utf-8")
    assert check(), "run `poe docs-gen-checks` to regenerate the Check ID index"
    block = render_index()
    rows = [line for line in block.splitlines() if line.startswith("| `")]
    assert len(rows) == len(registry)
    assert block in page
    assert str(len(registry)) not in page  # no hardcoded registry count to go stale


def test_documented_api_endpoints_exist_in_source() -> None:
    """Every endpoint on the API reference page is one the code actually calls.

    This is the check that catches a fabricated endpoint (the retired
    ``/api/files/:id/ingestStatus`` claim) without pinning the exact f-string
    used at each call site.
    """
    page = (DOCS / "reference" / "dataverse-api.md").read_text(encoding="utf-8")
    expanded = page.replace("…/", "/api/datasets/:persistentId/")
    endpoints = set(re.findall(r"/api/[A-Za-z0-9_/:{}.-]+", expanded))
    # The page defines `…/` with a literal `resource` placeholder; that is
    # notation, not an endpoint.
    endpoints.discard("/api/datasets/:persistentId/resource")
    assert endpoints

    def normalise(text: str) -> str:
        """Drop dynamic segments so an f-string and a `:placeholder` doc match."""
        text = re.sub(r"\{[^}]*\}|<[^>]*>|:[A-Za-z_][A-Za-z0-9_]*", "", text)
        return re.sub(r"/{2,}", "/", text)

    sources = normalise(
        "\n".join(
            path.read_text(encoding="utf-8")
            for folder in ("curation", "engine", "ui")
            for path in (ROOT / folder).rglob("*.py")
            if "tests" not in path.parts
        )
    )
    # Only URL-construction lines count for the token fallback: an endpoint
    # name can also appear as a payload field (``ingestStatus``) without ever
    # being called as an endpoint.
    markers = ("/api/", "_curation_paths(", "_get_json(", "_get_text(", "_api(")
    api_lines = "\n".join(line for line in sources.splitlines() if any(m in line for m in markers))
    generic = {"api", "datasets", "versions", "access", "datafile", "metadata", "all"}
    missing = []
    for endpoint in endpoints:
        normalised = normalise(endpoint).rstrip("/")
        if normalised in sources:
            continue
        # Some paths are assembled from a `_dataset_endpoint(name)` helper, so
        # the literal name appears at the call site rather than in the path.
        distinctive = [
            segment
            for segment in endpoint.split("?")[0].split("/")
            if len(segment) >= 5 and segment not in generic and not segment.startswith((":", "{"))
        ]
        if not any(token in api_lines for token in distinctive):
            missing.append(endpoint)
    assert not missing, f"documented endpoints not found in source: {missing}"


def test_documented_export_record_command_runs(tmp_path: Path) -> None:
    """The how-to's `--export-record` example writes the documented bundle."""
    staged = tmp_path / "staged"
    staged.mkdir()
    (staged / "data.csv").write_text("id,value\n1,alpha\n", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "main.py"),
            "--headless",
            str(staged),
            "--out",
            str(tmp_path / "report.json"),
            "--format",
            "both",
            "--persistent-id",
            "doi:10.5072/FK2/EXAMPLE",
            "--export-record",
        ],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    records = list((tmp_path / "curation-record").iterdir())
    assert len(records) == 1, records
    assert re.fullmatch(r"\d{8}-\d{6}", records[0].name), records[0].name
    assert {"index.json", "checks_report.json", "sha256sums.txt"} <= {
        p.name for p in records[0].iterdir()
    }


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
