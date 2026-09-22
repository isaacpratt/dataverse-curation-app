# PowerShell equivalent of `make rebuild-lite` (no Git Bash / make required).
# Usage: .\build-lite.ps1
$ErrorActionPreference = "Stop"
python -m PyInstaller --noconfirm --name curation-app-lite --windowed --onefile `
  --exclude-module pyreadstat --exclude-module netCDF4 --exclude-module h5py `
  --exclude-module scipy `
  --add-data "ui/assets;ui/assets" `
  --workpath .pyi-cache `
  main.py
Write-Host "Built dist/curation-app-lite.exe"
