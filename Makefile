.PHONY: install run test lint typecheck build build-full rebuild-lite smoke clean

# Portable recipes: every shell-specific step runs through `python -c` so
# the same Makefile works under Git Bash `make` and (via build-lite.ps1)
# in plain PowerShell/cmd, which have no sh/rm/cp. Always invoke tools via
# $(PYTHON) -m so the active venv interpreter wins.
PYTHON ?= python

install:
	$(PYTHON) -m pip install -r requirements.txt

install-dev:
	$(PYTHON) -m pip install -e ".[dev]"

run:
	$(PYTHON) main.py

test:
	$(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m ruff check .

typecheck:
	$(PYTHON) -m mypy engine/

# ------------------------------------------------------------------
# Default `make build` produces BOTH artefacts in dist/, side by side:
#
#   dist/curation-app-lite/       — onedir folder with common formats
#                                    bundled (jpg/png/pdf/xml/xlsx/tiff work
#                                    offline, no sibling needed)
#   dist/curation-app-full/       — onedir folder that additionally covers
#                                    the heavy binary libs (pyreadstat,
#                                     netCDF4, h5py, scipy for SPSS/SAS/Stata,
#                                     NetCDF/HDF5/MATLAB)
#
# The lite exe still looks for a sibling `curation-app-full/` folder for the
# heavy libs (checked next to the exe and next to the folder holding it, so
# the onedir layout resolves too), but common images/documents no longer
# depend on it: PIL, pypdf, lxml, openpyxl, tifffile, chardet are bundled in
# lite, plus a stdlib header fallback covers JPG/PNG/GIF/BMP/WEBP even
# without Pillow.
# NOTE: sibling sys.path injection only resolves binary .pyd shims — pure-
# Python modules live inside the full exe's archive, so for heavy formats
# run dist/curation-app-full/curation-app-full.exe directly.
#
# This keeps fast iterative testing cheap: only the lite folder needs
# rebuilding (a few seconds), and the heavy lib folder persists across
# builds until you explicitly `rm -rf dist/curation-app-full`.
# ------------------------------------------------------------------
# PyInstaller flags shared by lite recipes: heavy binary libs excluded plus
# verified-safe optional extras (tkinter/tcl-tk and optional PIL codecs —
# Pillow tolerates their absence); hush/piigex are pure-Python secret/PII
# scanners and always ship.
# --collect-all piigex is required: its detectors package walks the on-disk
# tree at import (pkgutil/pathlib), which is invisible when modules only
# live in the PYZ archive — collecting data+submodules materialises the tree.
LITE_EXCLUDES = --exclude-module pyreadstat --exclude-module netCDF4 \
	--exclude-module h5py --exclude-module scipy \
	--exclude-module tkinter --exclude-module turtle \
	--exclude-module PIL.ImageTk --exclude-module PIL.SpiderImagePlugin \
	--exclude-module PIL._avif
# Window/Explorer icon for every exe we ship: multi-size .ico rendered from
# ui/assets/16x16.png (64x64 docent.png stays the About art only).
EXE_ICON = --icon ui/assets/docent-mark.ico
SECRET_HIDDENS = --hidden-import hush --hidden-import hush.scanner \
	--hidden-import hush.rules --hidden-import hush.entropy \
	--collect-all piigex --hidden-import stdnum

build:
	$(PYTHON) -m PyInstaller --noconfirm --clean --name curation-app-lite --windowed --onedir \
		$(LITE_EXCLUDES) $(SECRET_HIDDENS) $(EXE_ICON) \
		--add-data "ui/assets;ui/assets" \
		--workpath .pyi-cache \
		main.py
	$(PYTHON) -m PyInstaller --noconfirm --clean --name curation-app-full --windowed --onedir \
		$(SECRET_HIDDENS) $(EXE_ICON) \
		--add-data "ui/assets;ui/assets" --workpath .pyi-cache main.py
	# Copy the example config into the full folder (no-op when absent).
	$(PYTHON) -c "import shutil, pathlib; [shutil.copy(f, 'dist/curation-app-full/' + pathlib.Path(f).name) for f in ('config.example.json',) if pathlib.Path(f).exists()]"

# Rebuild only the lite folder. Keeps dist/curation-app-full/ intact.
# No --clean here so PyInstaller reuses its Analysis cache (~seconds).
rebuild-lite:
	$(PYTHON) -m PyInstaller --noconfirm --name curation-app-lite --windowed --onedir \
		$(LITE_EXCLUDES) $(SECRET_HIDDENS) $(EXE_ICON) \
		--add-data "ui/assets;ui/assets" \
		--workpath .pyi-cache \
		main.py

# Build the full onedir folder only (heavy libs, fast launches).
# Use `dist/curation-app-full/curation-app-full.exe` directly if you don't
# need the lite exe.
build-full:
	$(PYTHON) -m PyInstaller --noconfirm --clean --name curation-app-full --windowed --onedir \
		$(SECRET_HIDDENS) $(EXE_ICON) \
		--add-data "ui/assets;ui/assets" --workpath .pyi-cache main.py

# Smoke the lite build without a display: --headless --help must exit 0 and
# the exe size is reported (catches missing-asset regressions).
smoke:
	$(PYTHON) -c "import pathlib, subprocess, sys; exe=pathlib.Path('dist/curation-app-lite/curation-app-lite.exe'); print(('exe ' + str(exe.stat().st_size) + ' bytes') if exe.exists() else 'lite exe missing — run make rebuild-lite first'); sys.exit(0)"
	$(PYTHON) main.py --headless --help
	# End-to-end: the frozen lite must run a headless CSV inspection with the
	# bundled secret/PII stack (piigex + stdnum + hush). Catches rebuilds made
	# without $(SECRET_HIDDENS), which previously surfaced as
	# "inspection failed (cannot import name 'vnr' from 'stdnum.at')".
	$(PYTHON) -c "import json, pathlib, subprocess, tempfile; d=pathlib.Path(tempfile.mkdtemp()); (d/'CA-TP4_HH_201601010000_201701010000.csv').write_text('t,v\n2016-01-01 00:00,-5.1\n2016-01-01 01:00,jane@example.com\n', encoding='utf-8'); out=d/'report.json'; subprocess.run(['dist/curation-app-lite/curation-app-lite.exe', '--headless', str(d), '--out', str(out)], check=True); report=json.loads(out.read_text(encoding='utf-8')); msgs=[c.get('message','') for f in report.get('files',[]) for c in f.get('checks',[])]; bad=[m for m in msgs if 'inspection failed' in m]; print('frozen csv checks:', len(msgs), '| inspection failures:', bad); raise SystemExit(1 if bad else 0)"

clean:
	$(PYTHON) -c "import shutil, glob, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in ('build', 'dist', '.pyi-cache')]; [pathlib.Path(p).unlink(missing_ok=True) for p in glob.glob('*.spec')]"
