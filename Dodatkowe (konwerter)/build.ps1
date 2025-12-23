# build.ps1
$ErrorActionPreference = "Stop"
$ProgressPreference = "Continue"
$VerbosePreference = "Continue"

function Write-Status([string]$Message) {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$timestamp] $Message"
}
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

# venv
if (!(Test-Path ".\.venv")) {
    Write-Status "Tworzenie venv (.venv)"
    py -3.11 -m venv .venv
}

# activate venv
Write-Status "Aktywacja venv"
.\.venv\Scripts\Activate.ps1

# deps
Write-Status "Aktualizacja pip"
python -m pip install --upgrade pip -v
Write-Status "Instalacja PyInstaller"
python -m pip install "pyinstaller>=6.6,<7" -v
Write-Status "Instalacja zależności z requirements-build.txt"
python -m pip install -r requirements-build.txt -v

# build
Write-Status "Budowanie EXE (PyInstaller)"
pyinstaller --noconfirm --clean --log-level=WARN `
  --name PicOrgFTP-SQL `
  --noconsole `
  --add-data "picorgftp_sql/Localization;picorgftp_sql/Localization" `
  --collect-submodules mysql.connector `
  --collect-data mysql.connector `
  PicOrgFTP-SQL.pyw

Write-Host "OK. Wynik: dist\PicOrgFTP-SQL\"
