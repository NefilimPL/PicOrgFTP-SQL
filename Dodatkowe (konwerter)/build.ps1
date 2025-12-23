# build.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

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
pyinstaller --noconfirm --clean --log-level=WARN `
  --name PicOrgFTP-SQL `
  --noconsole `
  --add-data "picorgftp_sql/Localization;picorgftp_sql/Localization" `
  --collect-submodules mysql.connector `
  --collect-data mysql.connector `
  PicOrgFTP-SQL.pyw

Write-Host "OK. Wynik: dist\PicOrgFTP-SQL\"
