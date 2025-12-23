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

# locate ODBC driver DLL without scanning PATH
$OdbcSearchPaths = @(
    (Join-Path $Env:WINDIR "System32\msodbcsql*.dll"),
    (Join-Path $Env:ProgramFiles "Microsoft SQL Server\Client SDK\ODBC\*\Tools\Binn\msodbcsql*.dll"),
    (Join-Path ${Env:ProgramFiles(x86)} "Microsoft SQL Server\Client SDK\ODBC\*\Tools\Binn\msodbcsql*.dll")
) | Where-Object { $_ -and (Test-Path $_) }

$OdbcDll = $null
foreach ($PathPattern in $OdbcSearchPaths) {
    $Match = Get-ChildItem -Path $PathPattern -File -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($Match) {
        $OdbcDll = $Match.FullName
        break
    }
}

if (-not $OdbcDll) {
    throw "Nie znaleziono msodbcsql*.dll. Sprawdź instalację sterownika ODBC."
}

# build
# --collect-data mysql.connector  # włącz pojedynczo, aby ustalić blokującą flagę
# --collect-submodules mysql.connector  # włącz pojedynczo po --collect-data
# --exclude-module pyodbc  # tymczasowo, jeśli build nadal się blokuje
pyinstaller --noconfirm --clean --log-level=DEBUG `
  --name PicOrgFTP-SQL `
  --debug=imports `
  --noconsole `
  --add-binary "$OdbcDll;." `
  --add-data "picorgftp_sql/Localization;picorgftp_sql/Localization" `
  PicOrgFTP-SQL.pyw


Write-Host "OK. Wynik: dist\PicOrgFTP-SQL\"


