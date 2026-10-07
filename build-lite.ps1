# PowerShell equivalent of `make rebuild-lite` (no Git Bash / make required).
# Usage: .\build-lite.ps1
# Form: --onedir (decision 2026-10-07) — the former onefile exe re-extracted
# ~250MB (AV-scanned) on every launch (~21s); the folder build opens at
# source speed (~2s measured) and is THE lite artefact (onefile dropped).
# Size trims (verified safe): PIL.SpiderImagePlugin -> PIL.ImageTk -> tkinter ->
# tcl/tk (obscure Spider format + Tk GUI paths the app never uses), PIL._avif
# (optional codec; Pillow tolerates its absence), on top of the original
# pyreadstat/netCDF4/h5py/scipy excludes.
$ErrorActionPreference = "Stop"
python -m PyInstaller --noconfirm --name curation-app-lite --windowed --onedir `
  --exclude-module pyreadstat --exclude-module netCDF4 --exclude-module h5py `
  --exclude-module scipy `
  --exclude-module tkinter --exclude-module turtle `
  --exclude-module PIL.ImageTk --exclude-module PIL.SpiderImagePlugin `
  --exclude-module PIL._avif `
  --hidden-import hush --hidden-import hush.scanner --hidden-import hush.rules `
  --hidden-import hush.entropy --collect-all piigex --hidden-import stdnum `
  --add-data "ui/assets;ui/assets" `
  --icon ui/assets/docent-mark.ico `
  --workpath .pyi-cache `
  main.py
Write-Host "Built dist/curation-app-lite/curation-app-lite.exe"
