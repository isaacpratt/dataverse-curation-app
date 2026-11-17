"""Build the Dataverse Docent PyInstaller folder.

One artefact: ``dist/DataverseDocent/DataverseDocent.exe`` plus its
``_internal`` payload, with ``config.example.json`` copied alongside. That
folder is what ``poe pack`` turns into the installer and its portable zip.

    uv run python tools/build_app.py

There is no second "lite" build any more: it existed to offer a smaller
download, and the portable zip Velopack builds from this one package already
is that download - 102 MB instead of a 164 MB folder nobody could reach.

Prints the wall time and the artefact size: this is the command run all day,
so the number belongs on screen.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: The executable and its folder. One name, everywhere: the PyInstaller
#: artefact, the shortcut target, the installer's --mainExe and the file a
#: curator sees in Task Manager.
NAME = "DataverseDocent"

ARGS = [
    "--noconfirm",
    "--windowed",
    "--onedir",
    "--name",
    NAME,
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

#: Verified-safe trims. The app imports only PySide6.QtCore, QtGui, QtSvg and
#: QtWidgets (ui/icons.py needs QtSvg with its plugin); everything here either
#: duplicates the stdlib Tk stack or is a Qt module nothing in the repo
#: imports. Cost of keeping them: ~930 extra files to copy and scan on every
#: build.
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

EXAMPLE_CONFIG = ROOT / "config.example.json"


def _dir_size_mb(path: Path) -> float:
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            continue
    return total / (1024 * 1024)


def build() -> Path:
    """Run PyInstaller and return the folder it produced."""
    args = [sys.executable, "-m", "PyInstaller", *ARGS]
    for module in SAFE_EXCLUDES:
        args += ["--exclude-module", module]
    args.append("main.py")

    started = time.perf_counter()
    result = subprocess.run(args, cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(f"{NAME}: PyInstaller failed ({result.returncode})")
    elapsed = time.perf_counter() - started

    dist = ROOT / "dist" / NAME
    if not dist.is_dir():
        raise SystemExit(f"{NAME}: PyInstaller reported success but {dist} is missing")

    if EXAMPLE_CONFIG.is_file():
        shutil.copy(EXAMPLE_CONFIG, dist / EXAMPLE_CONFIG.name)

    print(f"{NAME}: {_dir_size_mb(dist):.0f} MB built in {elapsed:.0f} s -> {dist}")
    return dist


def main() -> int:
    build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
