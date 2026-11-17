"""Pack dist/DataverseDocent into a Velopack release with vpk, then verify it.

    uv run poe pack                    # build already done: dist/releases/<version>
    uv run python tools/pack_app.py --out dist/releases

Everything users cannot repair by hand - the install folder name, the
shortcut and Apps & Features title, the channel, the executable - comes from
`tools/check_pack.py`, and the same module checks the result, so the builder
and the verifier cannot disagree about what "packed" means.

vpk is a .NET tool, needed only to build: `dotnet tool install -g vpk`
(.NET 8 SDK; the tool is multi-targeted, so no newer SDK is required). Set
`VPK` to point at a specific executable, e.g. a CI-pinned download.

Nothing is published here. `vpk upload` belongs to the release workflow, which
runs only on a version tag (see dv-4t6.4).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import __version__ as APP_VERSION  # noqa: E402
from engine.version import parse  # noqa: E402
from tools import check_pack  # noqa: E402


def find_vpk() -> Path:
    """Return the vpk executable, or explain how to install it."""
    override = os.environ.get("VPK")
    candidates = [
        Path(override) if override else None,
        Path(shutil.which("vpk")) if shutil.which("vpk") else None,
        Path.home() / ".dotnet" / "tools" / ("vpk.exe" if os.name == "nt" else "vpk"),
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return candidate
    raise SystemExit(
        "vpk not found. Install it once per machine (build time only):\n"
        "  winget install Microsoft.DotNet.SDK.8   # or https://dot.net/v1/dotnet-install.ps1\n"
        "  dotnet tool install -g vpk\n"
        "or point VPK at an existing vpk executable."
    )


def pack(
    build_dir: Path,
    out_dir: Path,
    version: str,
    vpk: Path,
    channel: str = check_pack.CHANNEL,
) -> int:
    """Run one `vpk pack` and return its exit code."""
    args = [
        str(vpk),
        "pack",
        "--packId",
        check_pack.PACK_ID,
        "--packTitle",
        check_pack.PACK_TITLE,
        "--packAuthors",
        check_pack.PACK_AUTHORS,
        "--packVersion",
        version,
        "--packDir",
        str(build_dir),
        "--mainExe",
        check_pack.MAIN_EXE,
        "--icon",
        str(check_pack.ICON),
        "--channel",
        channel,
        # Without this vpk warns that it defaults to x86 even though it then
        # reads the real architecture out of the exe; the nuspec must say x64.
        "--runtime",
        check_pack.RUNTIME,
        "--outputDir",
        str(out_dir),
    ]
    return subprocess.run(args, cwd=ROOT).returncode


def _dir_size_mb(path: Path) -> float:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) / 1e6


def clear_version(out_dir: Path, version: str) -> list[str]:
    """Delete an existing package of `version` so vpk will build it again.

    vpk refuses to pack a version that is already in the output folder ("equal
    or greater to the current version"). That is right for a feed it can never
    take a package back from, but it makes the local loop - rebuild, repack,
    run the Setup.exe - impossible without hand-deleting files. The feed is
    regenerated from the folder on every run, so removing this version's
    packages is enough.
    """
    removed = []
    for package in sorted(out_dir.glob(f"{check_pack.PACK_ID}-{version}-*.nupkg")):
        package.unlink()
        removed.append(package.name)
    return removed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Pack the PyInstaller app folder into a Velopack release."
    )
    parser.add_argument(
        "--build-dir",
        default=str(check_pack.BUILD_DIR),
        help="PyInstaller folder to pack (default: dist/DataverseDocent)",
    )
    parser.add_argument(
        "--out",
        default=str(check_pack.RELEASES_DIR),
        help="release output directory (default: dist/releases)",
    )
    parser.add_argument(
        "--version",
        default=APP_VERSION,
        help=f"package version (default: engine.__version__ = {APP_VERSION})",
    )
    parser.add_argument(
        "--channel",
        default=check_pack.CHANNEL,
        choices=check_pack.CHANNELS,
        help="release channel (default: win; win-beta for prereleases)",
    )
    parser.add_argument(
        "--no-replace",
        action="store_true",
        help="refuse to rebuild a version that is already in the output folder",
    )
    args = parser.parse_args(argv)

    version = args.version.strip()
    try:
        parse(version)
    except ValueError as exc:
        print(f"refusing to pack: {exc}", file=sys.stderr)
        return 1

    build_dir = Path(args.build_dir)
    if not (build_dir / check_pack.MAIN_EXE).is_file():
        print(
            f"{build_dir} has no {check_pack.MAIN_EXE} - run `uv run poe build` first",
            file=sys.stderr,
        )
        return 2

    out_dir = Path(args.out)
    had_previous = bool(list(out_dir.glob("*.nupkg"))) if out_dir.is_dir() else False
    if not args.no_replace:
        replaced = clear_version(out_dir, version)
        if replaced:
            print(f"rebuilding {version}: replaced {', '.join(replaced)}")

    vpk = find_vpk()
    started = time.perf_counter()
    code = pack(build_dir, out_dir, version, vpk, args.channel)
    elapsed = time.perf_counter() - started
    if code != 0:
        print(f"vpk pack failed ({code}) after {elapsed:.0f} s", file=sys.stderr)
        return code or 1

    problems = check_pack.check_release(out_dir, version=version, channel=args.channel)
    if problems:
        print(f"{out_dir} is not a shippable release:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    setup = out_dir / check_pack.setup_exe_name(channel=args.channel)
    print(
        f"packed {version} in {elapsed:.0f} s: {setup.name} "
        f"({setup.stat().st_size / 1e6:.0f} MB), "
        f"{_dir_size_mb(out_dir):.0f} MB in {out_dir}"
    )
    if not had_previous:
        print(
            "no earlier release in that folder, so this is a full package only - "
            "deltas appear once a previous .nupkg is there (the release workflow "
            "downloads it first)."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
