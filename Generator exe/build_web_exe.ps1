$ErrorActionPreference = "Stop"

$ScriptDir = $PSScriptRoot
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
$VenvDir = Join-Path $RepoRoot ".venv-build"
$Python = Join-Path $VenvDir "Scripts\python.exe"
$IconDir = Join-Path $ScriptDir ".icons"
$IconPath = Join-Path $IconDir "PIC_WEB.ico"
$WorkPath = Join-Path $RepoRoot "build\web-exe"

Set-Location $RepoRoot

if (-not (Test-Path $VenvDir)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        py -3.11 -m venv $VenvDir
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        python -m venv $VenvDir
    } else {
        throw "Nie znaleziono Pythona. Zainstaluj Python 3.11+ albo dodaj go do PATH."
    }
}

if (-not (Test-Path $Python)) {
    throw "Nie udalo sie utworzyc srodowiska build: $Python"
}

& $Python -m pip install --upgrade pip
& $Python -m pip install "pyinstaller>=6.6,<7"
& $Python -m pip install -r requirements-build.txt
& $Python -m pip install -r requirements-web.txt

New-Item -ItemType Directory -Path $IconDir -Force | Out-Null
& $Python -c "from PIL import Image; Image.open(r'pic\PIC_WEB.png').save(r'$IconPath', sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])"

$env:PICORGFTP_SQL_HEADLESS = "1"
$env:PYINSTALLER_BUILD = "1"

& $Python -m PyInstaller --noconfirm --clean --log-level=WARN `
    --name PicOrgFTP-SQL-WEB `
    --noconsole `
    --onefile `
    --distpath $ScriptDir `
    --workpath $WorkPath `
    --icon $IconPath `
    --collect-submodules picorgftp_sql `
    --collect-submodules mysql.connector `
    --collect-submodules uvicorn `
    --collect-submodules fastapi `
    --collect-submodules starlette `
    --collect-submodules multipart `
    --collect-submodules pystray `
    --collect-submodules PIL `
    --collect-data mysql.connector `
    --collect-data certifi `
    --add-data "picorgftp_sql\web\static;picorgftp_sql\web\static" `
    --add-data "picorgftp_sql\Localization;picorgftp_sql\Localization" `
    --add-data "picorgftp_sql\VERSION;picorgftp_sql" `
    --add-data "pic\PIC_WEB.png;pic" `
    PicOrgFTP-SQL-WEB.pyw

Write-Host "OK. Wynik: $ScriptDir\PicOrgFTP-SQL-WEB.exe"
