"""Copy config.example.json into dist/curation-app-full/ when present.

Port of the trailing step of the Makefile's big `build` recipe so the
full build folder ships an editable template config. No-op when the file
is absent.
"""

import pathlib
import shutil

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "config.example.json"
DST = ROOT / "dist" / "curation-app-full"

if SRC.exists() and DST.exists():
    shutil.copy(SRC, DST / SRC.name)
    print(f"copied {SRC.name} into {DST}")
else:
    print("config.example.json or dist/curation-app-full missing - skipped")
