"""Build one PyInstaller artefact (lite or full) with the shared flags.

One place for the hidden imports, the verified-safe excludes, the icon and
the data files, so the two variants cannot drift apart - they already had:
the full build shipped ``tkinter`` and the PIL extras the lite build had
long since dropped, and it paid for a ``--clean`` that wiped the Analysis
cache on every rebuild.

    uv run python tools/build_app.py --variant full
    uv run python tools/build_app.py --variant lite --variant full

Variants: ``full`` carries every format library and is the installer
payload; ``lite`` drops the heavy binary libs and relies on the Auto-Checks
card's "Missing ..." path for SPSS/SAS/Stata/NetCDF/HDF5.

Prints the wall time and the artefact size per variant: this is the command
run all day, so the number belongs on screen.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Both variants: same entry point, same windowed onedir shape, same assets.
COMMON_ARGS = [
    "--noconfirm",
    "--windowed",
    "--onedir",
    "--hidden-import",
    "hush",
    "--hidden-import",
    "hush.scanner",
    "--hidden-import",
    "hush.rules",
    "--hidden-import",
    "hush.entropy",
    "--collect-all",
    "piigex",
    "--hidden-import",
    "stdnum",
    "--add-data",
    "ui/assets;ui/assets",
    "--icon",
    "ui/assets/docent-mark.ico",
    "--workpath",
    ".pyi-cache",
]

#: Verified-safe trims, shared by both variants. The app imports only
#: PySide6.QtCore, QtGui, QtSvg and QtWidgets (ui/icons.py needs QtSvg with
#: its plugin); everything here either duplicates the stdlib Tk stack or is
#: a Qt module nothing in the repo imports. Cost of keeping them: ~930 extra
#: files to copy and scan on every build.
SAFE_EXCLUDES = [
    "tkinter",
    "turtle",
    "PIL.ImageTk",
    "PIL.SpiderImagePlugin",
    "PIL._avif",
    "PySide6.QtNetwork",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtMultimedia",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtDBus",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtUiTools",
    "PySide6.QtXml",
    "PySide6.QtPrintSupport",
]

#: Heavy binary libs: bundled in `full`, excluded from `lite`.
HEAVY_EXCLUDES = ["pyreadstat", "netCDF4", "h5py", "scipy"]

VARIANTS = {"lite": "curation-app-lite", "full": "curation-app-full"}


def _dir_size_mb(path: Path) -> float:
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            continue
    return total / (1024 * 1024)


def build(variant: str) -> None:
    """Run PyInstaller for one variant and report time + size."""
    name = VARIANTS[variant]
    excludes = SAFE_EXCLUDES + (HEAVY_EXCLUDES if variant == "lite" else [])
    args = [sys.executable, "-m", "PyInstaller", *COMMON_ARGS, "--name", name]
    for module in excludes:
        args += ["--exclude-module", module]
    args.append("main.py")

    started = time.perf_counter()
    result = subprocess.run(args, cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(f"{name}: PyInstaller failed ({result.returncode})")
    elapsed = time.perf_counter() - started

    dist = ROOT / "dist" / name
    if not dist.is_dir():
        raise SystemExit(f"{name}: PyInstaller reported success but {dist} is missing")
    print(f"{name}: {_dir_size_mb(dist):.0f} MB built in {elapsed:.0f} s")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a PyInstaller artefact.")
    parser.add_argument(
        "--variant",
        action="append",
        choices=sorted(VARIANTS),
        help="variant to build (repeatable; default: full)",
    )
    args = parser.parse_args(argv)
    for variant in args.variant or ["full"]:
        build(variant)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
