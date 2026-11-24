"""Generate the Check ID index in ``docs/reference/checks.md`` from the registry.

The table is a lookup contract: if a check is added, renamed or re-scoped, the
published reference must change with it. ``poe docs-gen-checks`` writes the
block; the pytest drift check (and ``--check`` here) refuses a stale one.

Usage::

    uv run python tools/docs/gen_checks_reference.py --check
    uv run python tools/docs/gen_checks_reference.py --write
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Running this helper directly puts tools/docs on sys.path, not the repo root.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.checks import registry  # noqa: E402

PAGE = ROOT / "docs" / "reference" / "checks.md"
BEGIN = "<!-- BEGIN GENERATED CHECK ID INDEX -->"
END = "<!-- END GENERATED CHECK ID INDEX -->"


def render_index() -> str:
    """Return the complete generated block, markers included."""
    rows = []
    for check_id, check_class in sorted(registry.items()):
        module = check_class.__module__.rsplit(".", 1)[-1]
        scope = getattr(check_class, "scope", "?")
        rows.append(f"| `{check_id}` | `{module}` | `{scope}` |")
    return "\n".join(
        [
            BEGIN,
            "| Check ID | Module | Scope |",
            "| --- | --- | --- |",
            *rows,
            END,
        ]
    )


def current_block(text: str) -> str:
    """Extract the marked block, or an empty string when it is missing."""
    start = text.find(BEGIN)
    end = text.find(END)
    if start < 0 or end < 0:
        return ""
    return text[start : end + len(END)]


def check() -> bool:
    """Return True when the published block matches the registry."""
    return current_block(PAGE.read_text(encoding="utf-8")) == render_index()


def write() -> bool:
    """Replace the marked block; True when the file changed."""
    text = PAGE.read_text(encoding="utf-8")
    block = render_index()
    existing = current_block(text)
    if existing == block:
        return False
    text = text.replace(existing, block, 1) if existing else text.rstrip() + "\n\n" + block + "\n"
    PAGE.write_text(text, encoding="utf-8", newline="")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--check", action="store_true", help="fail when the published block is stale"
    )
    group.add_argument("--write", action="store_true", help="regenerate the published block")
    args = parser.parse_args(argv)
    if args.write:
        changed = write()
        print(f"checks reference: {'updated' if changed else 'already current'}")
        return 0
    if check():
        print(f"checks reference: OK ({len(registry)} registry IDs)")
        return 0
    print("checks reference: stale — run `poe docs-gen-checks`", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
