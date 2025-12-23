# build.ps1
$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

# venv
if (!(Test-Path ".\.venv")) {
    py -3.11 -m venv .venv
}

# activate venv
.\.venv\Scripts\Activate.ps1


# deps
python -m pip install --upgrade pip
python -m pip install "pyinstaller>=6.6,<7"
python -m pip install -r requirements-build.txt
# build
# --collect-data mysql.connector  # włącz pojedynczo, aby ustalić blokującą flagę
# --collect-submodules mysql.connector  # włącz pojedynczo po --collect-data
# --exclude-module pyodbc  # tymczasowo, jeśli build nadal się blokuje
$Env:Path = "$Env:VIRTUAL_ENV\Scripts;C:\Windows\System32;C:\Windows"
pyinstaller --noconfirm --clean --log-level=DEBUG `
  --name PicOrgFTP-SQL `
  --debug=imports `
  --noconsole `
  --add-data "picorgftp_sql/Localization;picorgftp_sql/Localization" `
  --exclude-module mysql.connector `
  --exclude-module pyodbc `
  PicOrgFTP-SQL.pyw


Write-Host "OK. Wynik: dist\PicOrgFTP-SQL\"


