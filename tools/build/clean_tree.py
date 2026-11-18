"""Cross-platform clean for build artifacts.

Port of the Makefile's `clean` recipe, which was already a `python -c`
one-liner because rm/glob don't exist in cmd. Removes build/, dist/,
.pyi-cache/ and any PyInstaller .spec files at the repo root.
Quietly succeeds whatever the state is.
"""

import glob
import pathlib
import shutil

ROOT = pathlib.Path(__file__).resolve().parents[2]

for name in ("build", "dist", ".pyi-cache"):
    shutil.rmtree(ROOT / name, ignore_errors=True)
for spec in glob.glob(str(ROOT / "*.spec")):
    pathlib.Path(spec).unlink(missing_ok=True)
print("cleaned build/, dist/, .pyi-cache/, *.spec")
