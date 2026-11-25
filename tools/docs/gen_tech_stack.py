"""Generate the tech-stack reference in ``docs/reference/tech-stack.md``.

Declared floors come from ``pyproject.toml``; exact versions come from
``uv.lock`` for the Python version pinned in ``.python-version``. The .NET SDK
pin comes from ``global.json`` (it is only needed to build releases). The
marked block is generated: a dependency change or a lock refresh must be
followed by ``poe docs-gen-tech-stack``.

Usage::

    uv run python tools/docs/gen_tech_stack.py --check
    uv run python tools/docs/gen_tech_stack.py --write
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "docs" / "reference" / "tech-stack.md"
BEGIN = "<!-- BEGIN GENERATED TECH STACK -->"
END = "<!-- END GENERATED TECH STACK -->"


def _load_toml(path: Path) -> dict[str, Any]:
    """Read one TOML file as a dictionary."""
    with path.open("rb") as stream:
        return tomllib.load(stream)


def _target_marker(lock: dict[str, Any], python_version: str) -> str:
    """Return the lockfile resolution marker for the pinned Python version.

    A lock can carry several versions of the same package, one per supported
    Python range. The marker with ``>= '<pinned>.<minor>'`` selects the branch
    this project actually runs; e.g. Python 3.11 selects the
    ``>= '3.11.5' and < '3.12'`` branch, not the 3.12+ one.
    """
    needle = f">= '{python_version}"
    matches = [marker for marker in lock.get("resolution-markers", []) if needle in marker]
    if len(matches) != 1:
        raise ValueError(
            f"expected one {python_version!r} resolution marker in uv.lock, got {matches}"
        )
    return matches[0]


def _locked_versions(lock: dict[str, Any], marker: str) -> dict[str, str]:
    """Map lowercase package names to the version selected by ``marker``."""
    versions: dict[str, str] = {}
    for package in lock.get("package", []):
        name = str(package.get("name", "")).lower()
        version = package.get("version")
        if not name or version is None:
            continue
        markers = package.get("resolution-markers")
        if markers is None:
            if name in versions:
                raise ValueError(f"multiple unlocked versions for {name!r}")
            versions[name] = str(version)
        elif marker in markers:
            versions[name] = str(version)
    return versions


def _rows(declarations: list[str], versions: dict[str, str], marker: str) -> list[str]:
    """Render one declared-versus-locked table."""
    lines = [
        "| Package | Declared floor | Locked for this Python |",
        "| --- | --- | --- |",
    ]
    for declaration in declarations:
        name, _, floor = declaration.partition(">=")
        if not floor:
            name, _, floor = declaration.partition("==")
        key = name.strip().lower()
        locked = versions.get(key)
        if locked is None:
            raise ValueError(f"{name!r} has no locked version for marker {marker!r}")
        lines.append(f"| `{name.strip()}` | `{floor.strip()}` | `{locked}` |")
    return lines


def render_stack() -> str:
    """Return the complete generated block, markers included."""
    project = _load_toml(ROOT / "pyproject.toml")
    lock = _load_toml(ROOT / "uv.lock")
    python_version = (ROOT / ".python-version").read_text(encoding="utf-8").strip()
    sdk = json.loads((ROOT / "global.json").read_text(encoding="utf-8"))["sdk"]["version"]
    marker = _target_marker(lock, python_version)
    versions = _locked_versions(lock, marker)

    runtime = list(project["project"]["dependencies"])
    dev = list(project["dependency-groups"]["dev"])
    lines = [
        BEGIN,
        "",
        f"Resolution marker: `{marker}`. Exact versions are locked in `uv.lock`; "
        "the floors below are what `pyproject.toml` declares.",
        "",
        "## Runtime",
        "",
        *_rows(runtime, versions, marker),
        "",
        "## Development",
        "",
        *_rows(dev, versions, marker),
        "",
        "## Platform and packaging",
        "",
        "| Component | Source | Version |",
        "| --- | --- | --- |",
        f"| Python | `.python-version` | `{python_version}` |",
        f"| .NET SDK (Velopack packaging) | `global.json` | `{sdk}` |",
        "",
        END,
    ]
    return "\n".join(lines)


def current_block(text: str) -> str:
    """Extract the marked block, or an empty string when it is missing."""
    start = text.find(BEGIN)
    end = text.find(END)
    if start < 0 or end < 0:
        return ""
    return text[start : end + len(END)]


def check() -> bool:
    """Return True when the published block matches the lockfile."""
    return current_block(PAGE.read_text(encoding="utf-8")) == render_stack()


def write() -> bool:
    """Replace the marked block; True when the file changed."""
    text = PAGE.read_text(encoding="utf-8")
    block = render_stack()
    existing = current_block(text)
    if existing == block:
        return False
    text = text.replace(existing, block, 1) if existing else text.rstrip() + "\n\n" + block + "\n"
    PAGE.write_text(text, encoding="utf-8", newline="")
    return True


def main(argv: list[str] | None = None) -> int:
    """Run the --check or --write mode."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--check", action="store_true", help="fail when the published block is stale"
    )
    group.add_argument("--write", action="store_true", help="regenerate the published block")
    args = parser.parse_args(argv)
    if args.write:
        changed = write()
        print(f"tech-stack reference: {'updated' if changed else 'already current'}")
        return 0
    if check():
        print("tech-stack reference: OK")
        return 0
    print("tech-stack reference: stale — run `poe docs-gen-tech-stack`", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
