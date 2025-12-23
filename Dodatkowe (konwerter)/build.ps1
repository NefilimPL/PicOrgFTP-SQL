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
# --exclude-module pyodbc  # tymczasowo, jeśli build nadal się blokuje
pyinstaller --noconfirm --clean --log-level=DEBUG `
  --name PicOrgFTP-SQL `
  --debug=imports `
  --noconsole `
  --collect-data mysql.connector `
  --hidden-import mysql.connector `
  --hidden-import mysql.connector.connection `
  --hidden-import mysql.connector.cursor `
  --hidden-import mysql.connector.errors `
  --add-data "picorgftp_sql/Localization;picorgftp_sql/Localization" `
  PicOrgFTP-SQL.pyw


Write-Host "OK. Wynik: dist\PicOrgFTP-SQL\"


