"""Fail a release when the tag and `engine.__version__` disagree.

The release workflow runs this before it builds anything, and so can a
maintainer, to see what a tag would do:

    uv run python tools/build/check_version.py --tag v0.2.0

With no `--tag` it reads `GITHUB_REF_NAME`, which is the tag on a tag push.
Exit codes: 0 the tag matches (prints the version and channel), 1 mismatch
or a malformed tag/version, 2 no tag to check.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.version import is_prerelease, tag_error, tag_version  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check that a release tag matches engine.__version__."
    )
    parser.add_argument(
        "--tag",
        default=os.environ.get("GITHUB_REF_NAME", ""),
        help="release tag (default: $GITHUB_REF_NAME)",
    )
    args = parser.parse_args(argv)

    tag = (args.tag or "").strip()
    if not tag:
        print("no tag to check: pass --tag or set GITHUB_REF_NAME", file=sys.stderr)
        return 2

    problem = tag_error(tag)
    if problem:
        print(f"version check failed: {problem}", file=sys.stderr)
        return 1

    version = tag_version(tag)
    channel = "beta" if is_prerelease(version) else "stable"
    print(f"version {version} matches tag {tag} ({channel} channel; engine.__version__)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
