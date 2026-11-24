"""Generate the CLI reference in ``docs/reference/cli.md`` from argparse.

``main.build_parser()`` is the single source of truth for the flags. This
script renders its help text and flag table into a marked block; a drift test
in pytest and ``poe docs-gen-cli-check`` fail when the published block is stale.

Usage::

    uv run python tools/docs/gen_cli_reference.py --check
    uv run python tools/docs/gen_cli_reference.py --write
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Running this helper directly puts tools/docs on sys.path, not the repo root.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from main import build_parser  # noqa: E402

PAGE = ROOT / "docs" / "reference" / "cli.md"
BEGIN = "<!-- BEGIN GENERATED CLI REFERENCE -->"
END = "<!-- END GENERATED CLI REFERENCE -->"


def _form(action: argparse.Action) -> str:
    """Describe how argparse accepts one argument."""
    if action.choices:
        return f"choice ({'|'.join(str(choice) for choice in action.choices)})"
    if not action.option_strings:
        return "optional positional" if action.nargs == "?" else "positional"
    if action.nargs == 0:
        return "flag"
    return "value"


def _default(action: argparse.Action) -> str:
    """Render one default value for the lookup table."""
    if action.default is argparse.SUPPRESS or (
        action.default is None and not action.option_strings
    ):
        return "—"
    if action.default is None:
        return "None"
    if action.default == "":
        return '`""`'
    return f"`{action.default}`"


def render_reference() -> str:
    """Return the complete generated block, markers included."""
    parser = build_parser()
    # The generator's argv[0] is this script, not main.py; pin the help's prog.
    parser.prog = "main.py"
    lines = [
        BEGIN,
        "",
        "```text",
        parser.format_help().rstrip(),
        "```",
        "",
        "| Argument | Form | Default | Help |",
        "| --- | --- | --- | --- |",
    ]
    for action in parser._actions:
        name = (
            ", ".join(f"`{option}`" for option in action.option_strings)
            if action.option_strings
            else f"`{action.dest}`"
        )
        lines.append(f"| {name} | {_form(action)} | {_default(action)} | {action.help or ''} |")
    lines.extend(["", END])
    return "\n".join(lines)


def current_block(text: str) -> str:
    """Extract the marked block, or an empty string when it is missing."""
    start = text.find(BEGIN)
    end = text.find(END)
    if start < 0 or end < 0:
        return ""
    return text[start : end + len(END)]


def check() -> bool:
    """Return True when the published block matches the parser."""
    return current_block(PAGE.read_text(encoding="utf-8")) == render_reference()


def write() -> bool:
    """Replace the marked block; True when the file changed."""
    text = PAGE.read_text(encoding="utf-8")
    block = render_reference()
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
        print(f"CLI reference: {'updated' if changed else 'already current'}")
        return 0
    if check():
        print("CLI reference: OK")
        return 0
    print("CLI reference: stale — run `poe docs-gen-cli`", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
