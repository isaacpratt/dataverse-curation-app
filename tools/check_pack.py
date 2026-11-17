"""One definition of a correctly packed Velopack release, and the fixed identity.

`tools/pack_app.py` builds the release with these values; this module checks
the result, and CI runs the same check on the artefact it uploaded. Keeping
both in one place is the point: the ids below name filesystem locations and
registry-free install paths a user cannot repair by hand, so a typo here is
not a cosmetic bug.

    uv run python tools/check_pack.py                 # dist/releases, engine version
    uv run python tools/check_pack.py --dir some/dir --version 0.2.0

Exit codes: 0 the release directory is complete, 1 something is missing or
disagrees (each problem on its own line), 2 no release directory at all.
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import __version__ as APP_VERSION  # noqa: E402
from engine.version import parse  # noqa: E402

#: Permanent. It names %LocalAppData%\{packId} (the install folder), the
#: uninstaller entry and the package id in the update feed, so changing it
#: orphans every existing install instead of updating it.
PACK_ID = "DataverseDocent"
#: What the Start menu entry, the desktop shortcut and Apps & Features say.
PACK_TITLE = "Dataverse Docent"
#: Publisher line in Apps & Features. vpk defaults to the pack id otherwise,
#: which users read as a typo ("DataverseDocent").
PACK_AUTHORS = "Dataverse Docent"
#: The PyInstaller onedir executable - the file the shortcut launches.
MAIN_EXE = "curation-app-full.exe"
CHANNEL = "win"
#: The build carries a CPython + compiled extensions for this arch only.
RUNTIME = "win-x64"
ICON = ROOT / "ui" / "assets" / "docent-mark.ico"
BUILD_DIR = ROOT / "dist" / "curation-app-full"
RELEASES_DIR = ROOT / "dist" / "releases"

_MIN_PLAUSIBLE_BYTES = 1_000_000  # a Setup.exe under 1 MB is a stub, not an app


def setup_exe_name(pack_id: str = PACK_ID, channel: str = CHANNEL) -> str:
    """`DataverseDocent-win-Setup.exe` - what the release page links to."""
    return f"{pack_id}-{channel}-Setup.exe"


def portable_name(pack_id: str = PACK_ID, channel: str = CHANNEL) -> str:
    """`DataverseDocent-win-Portable.zip` - the no-install option."""
    return f"{pack_id}-{channel}-Portable.zip"


def nupkg_name(version: str, pack_id: str = PACK_ID) -> str:
    """`DataverseDocent-0.1.0-full.nupkg` - the package the updater downloads."""
    return f"{pack_id}-{version}-full.nupkg"


def feed_name(channel: str = CHANNEL) -> str:
    """`releases.win.json` - the feed `GithubSource` reads."""
    return f"releases.{channel}.json"


def _nuspec(zf: zipfile.ZipFile) -> ET.Element | None:
    for name in zf.namelist():
        if name.endswith(".nuspec") and "/" not in name:
            try:
                return ET.fromstring(zf.read(name))
            except ET.ParseError:
                return None
    return None


def _text(root: ET.Element, tag: str) -> str:
    node = root.find(f".//{{*}}{tag}")
    return (node.text or "").strip() if node is not None else ""


def check_release(
    directory: Path | str = RELEASES_DIR,
    *,
    version: str | None = None,
    pack_id: str = PACK_ID,
    main_exe: str = MAIN_EXE,
    channel: str = CHANNEL,
    runtime: str = RUNTIME,
) -> list[str]:
    """Return every way `directory` fails to be a shippable release ([] = fine)."""
    if version is None:
        version = APP_VERSION
    directory = Path(directory)
    if not directory.is_dir():
        return [f"{directory} does not exist - run `uv run poe pack` first"]

    problems: list[str] = []

    setup = directory / setup_exe_name(pack_id, channel)
    if not setup.is_file():
        problems.append(f"missing {setup.name} (the one-click installer)")
    elif setup.stat().st_size < _MIN_PLAUSIBLE_BYTES:
        problems.append(f"{setup.name} is only {setup.stat().st_size} bytes - truncated")

    portable = directory / portable_name(pack_id, channel)
    if not portable.is_file():
        problems.append(f"missing {portable.name} (the portable option)")

    # The package the updater actually downloads: its metadata is what the
    # client compares against the installed version, so it is checked, not
    # just its existence.
    expected_nupkg = nupkg_name(version, pack_id)
    nupkg = directory / expected_nupkg
    if not nupkg.is_file():
        found = sorted(p.name for p in directory.glob("*.nupkg"))
        problems.append(
            f"missing {expected_nupkg} (found: {', '.join(found) or 'none'}) - "
            "does --packVersion match engine.__version__?"
        )
    else:
        try:
            with zipfile.ZipFile(nupkg) as zf:
                names = zf.namelist()
                spec = _nuspec(zf)
        except zipfile.BadZipFile:
            problems.append(f"{expected_nupkg} is not a readable zip")
        else:
            if not any(Path(name).name == main_exe for name in names):
                problems.append(f"{expected_nupkg} does not contain {main_exe}")
            if spec is None:
                problems.append(f"{expected_nupkg} has no readable .nuspec")
            else:
                if _text(spec, "id") != pack_id:
                    problems.append(
                        f"nuspec id {_text(spec, 'id')!r} is not {pack_id!r}"
                    )
                if _text(spec, "version") != version:
                    problems.append(
                        f"nuspec version {_text(spec, 'version')!r} is not {version!r}"
                    )
                if _text(spec, "mainExe") != main_exe:
                    problems.append(
                        f"nuspec mainExe {_text(spec, 'mainExe')!r} is not {main_exe!r}"
                    )
                if _text(spec, "rid") != runtime:
                    problems.append(
                        f"nuspec rid {_text(spec, 'rid')!r} is not {runtime!r} "
                        "(vpk defaults to x86 when --runtime is omitted)"
                    )
                if _text(spec, "channel") != channel:
                    problems.append(
                        f"nuspec channel {_text(spec, 'channel')!r} is not {channel!r}"
                    )

    # The feed the in-app updater reads. Its asset list must name this build,
    # otherwise a published release is invisible to every installed copy.
    feed = directory / feed_name(channel)
    if not feed.is_file():
        problems.append(f"missing {feed.name} (the update feed)")
    else:
        try:
            payload = json.loads(feed.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f"{feed.name} is not readable JSON: {exc}")
        else:
            assets = payload.get("Assets") or []
            matching = [
                asset
                for asset in assets
                if asset.get("PackageId") == pack_id and asset.get("Version") == version
            ]
            if not matching:
                problems.append(
                    f"{feed.name} lists no {pack_id} {version} asset "
                    f"(versions: {sorted({a.get('Version') for a in assets}) or 'none'})"
                )
            elif not matching[0].get("SHA256"):
                problems.append(f"{feed.name} entry for {version} has no SHA256")

    # Legacy delta client (and some proxies) read RELEASES; vpk still writes it.
    releases = directory / "RELEASES"
    if not releases.is_file():
        problems.append("missing RELEASES (legacy feed index)")
    elif expected_nupkg not in releases.read_text(encoding="utf-8", errors="replace"):
        problems.append(f"RELEASES does not mention {expected_nupkg}")

    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check a Velopack release directory is complete and consistent."
    )
    parser.add_argument(
        "--dir",
        default=str(RELEASES_DIR),
        help="release directory (default: dist/releases)",
    )
    parser.add_argument(
        "--version",
        default=None,
        help="expected version (default: engine.__version__)",
    )
    args = parser.parse_args(argv)

    if args.version is not None:
        parse(args.version)  # a non-semver expectation is a usage error, not a finding
    version = args.version or APP_VERSION

    directory = Path(args.dir)
    if not directory.is_dir():
        print(f"{directory} does not exist - run `uv run poe pack` first", file=sys.stderr)
        return 2

    problems = check_release(directory, version=version)
    if problems:
        print(f"{directory} is not a shippable release:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    setup = directory / setup_exe_name()
    nupkg = directory / nupkg_name(version)
    print(
        f"release ok: {setup.name} ({setup.stat().st_size / 1e6:.0f} MB), "
        f"{nupkg.name}, {feed_name()} in {directory}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
