"""Version helpers: one number names the build, and the release tag must agree.

`engine.__version__` is the only literal. Everything else derives from it:
the package metadata (`pyproject.toml` reads it through
`[tool.setuptools.dynamic]`), the About pane, the updater's idea of what is
installed, and `vpk pack --packVersion` in the release workflow - which
fails before publishing when the tag and this number disagree.

A mismatch is not cosmetic: Velopack's `UpdateManager.get_current_version()`
compares the installed package's version against the feed, so an app that
reports 0.1.0 while its package says 0.2.0 either keeps offering an update
it already applied or never sees one.
"""

from __future__ import annotations

import re

from engine import __version__

# Semver 2.0.0, anchored: vpk rejects anything else, so a release should
# fail here first with a sentence a human can act on.
_SEMVER = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<pre>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+(?P<build>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)


def parse(version: str) -> tuple[int, int, int, str]:
    """Split `X.Y.Z[-pre][+build]` into (major, minor, patch, prerelease).

    Raises ValueError for anything that is not semver.
    """
    match = _SEMVER.match(version.strip())
    if match is None:
        raise ValueError(f"not a semver version: {version!r}")
    return (
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch")),
        match.group("pre") or "",
    )


def is_prerelease(version: str) -> bool:
    """Return True for `X.Y.Z-something` (the beta feed), False for a stable one."""
    return bool(parse(version)[3])


def tag_version(tag: str) -> str:
    """Strip a release tag's leading `v`: `v0.2.0` and `V0.2.0` both give `0.2.0`."""
    text = tag.strip()
    if text[:1].lower() == "v":
        return text[1:]
    return text


def tag_error(tag: str, version: str = __version__) -> str:
    """Return why this tag cannot release this build, or "" when it can.

    One sentence, printed by `tools/build/check_version.py` and by the release
    workflow, so a bad tag fails before anything is built or published.
    """
    released = tag_version(tag)
    try:
        parse(released)
    except ValueError as exc:
        return f"tag {tag!r} is not semver: {exc}"
    try:
        parse(version)
    except ValueError as exc:
        return f"engine.__version__ {version!r} is not semver: {exc}"
    if released != version:
        return f"tag {tag!r} says {released}, engine.__version__ says {version}"
    return ""
