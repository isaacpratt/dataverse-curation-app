.PHONY: install run test build build-full rebuild-lite clean

# Portable recipes: every shell-specific step runs through `python -c` so
# the same Makefile works under Git Bash `make` and (via the documented
# pyinstaller one-liners) in plain PowerShell/cmd, which have no sh/rm/cp.
PYTHON ?= python

install:
	pip install -r requirements.txt

run:
	python main.py

test:
	python -m pytest -q

# ------------------------------------------------------------------
# Default `make build` produces BOTH artefacts in dist/, side by side:
#
#   dist/curation-app-lite.exe    — single 62.9 MB exe (the runnable app)
#   dist/curation-app-full/       — onedir folder with all heavy libs
#                                    (pyreadstat, netCDF4, h5py, tifffile,
#                                     Pillow, pypdf, lxml, openpyxl, scipy)
#
# The lite exe looks for a sibling `curation-app-full/` folder and
# prepends it to sys.path. If the folder is absent the lite exe still
# runs (heavy checks show as "Missing: pip install …"). If you delete
# the folder, just run `make rebuild-lite` and the lite exe alone works.
#
# This keeps fast iterative testing cheap: only the lite onefile needs
# rebuilding (a few seconds), and the heavy lib folder persists across
# builds until you explicitly `rm -rf dist/curation-app-full`.
# ------------------------------------------------------------------
build:
	pyinstaller --noconfirm --clean --name curation-app-lite --windowed --onefile \
		--exclude-module pyreadstat --exclude-module netCDF4 --exclude-module h5py \
		--exclude-module tifffile --exclude-module PIL --exclude-module pypdf \
		--exclude-module lxml --exclude-module openpyxl --exclude-module scipy \
		--add-data "ui/assets;ui/assets" \
		main.py
	pyinstaller --noconfirm --clean --name curation-app-full --windowed --onedir \
		--add-data "ui/assets;ui/assets" main.py
	# Copy example config + checklist PDFs into the full folder so the
	# lite exe can find them via its sibling lookup (no-op when absent).
	$(PYTHON) -c "import shutil, pathlib; [shutil.copy(f, 'dist/curation-app-full/' + pathlib.Path(f).name) for f in ('config.example.json', 'docs/CurationLog.pdf', 'docs/DepositorChecklist.pdf') if pathlib.Path(f).exists()]"

# Rebuild only the lite exe. Keeps dist/curation-app-full/ intact.
rebuild-lite:
	pyinstaller --noconfirm --clean --name curation-app-lite --windowed --onefile \
		--exclude-module pyreadstat --exclude-module netCDF4 --exclude-module h5py \
		--exclude-module tifffile --exclude-module PIL --exclude-module pypdf \
		--exclude-module lxml --exclude-module openpyxl --exclude-module scipy \
		--add-data "ui/assets;ui/assets" \
		main.py

# Build the full onedir folder only (heavy libs, fast launches).
# Use `dist/curation-app-full/curation-app-full.exe` directly if you don't
# need the lite exe.
build-full:
	pyinstaller --noconfirm --clean --name curation-app-full --windowed --onedir \
		--add-data "ui/assets;ui/assets" main.py

clean:
	$(PYTHON) -c "import shutil, glob, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in ('build', 'dist')]; [pathlib.Path(p).unlink(missing_ok=True) for p in glob.glob('*.spec')]"
