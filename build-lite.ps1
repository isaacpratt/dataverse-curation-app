# PowerShell equivalent of `make rebuild-lite` (no Git Bash / make required).
# Usage: .\build-lite.ps1
$ErrorActionPreference = "Stop"
python -m PyInstaller --noconfirm --name curation-app-lite --windowed --onefile `
  --exclude-module pyreadstat --exclude-module netCDF4 --exclude-module h5py `
  --exclude-module scipy `
  --hidden-import hush --hidden-import hush.scanner --hidden-import hush.rules `
  --hidden-import hush.entropy --collect-all piigex --hidden-import stdnum `
  --add-data "ui/assets;ui/assets" `
  --icon ui/assets/docent.png `
  --workpath .pyi-cache `
  main.py
Write-Host "Built dist/curation-app-lite.exe"
