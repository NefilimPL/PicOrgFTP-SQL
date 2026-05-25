$ErrorActionPreference = "Stop"

$ScriptDir = $PSScriptRoot
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
$VenvDir = Join-Path $RepoRoot ".venv-build"
$Python = Join-Path $VenvDir "Scripts\python.exe"
$IconDir = Join-Path $ScriptDir ".icons"
$IconPath = Join-Path $IconDir "PIC_LOCAL.ico"
$WorkPath = Join-Path $RepoRoot "build\local-exe"
$VersionInfoPath = Join-Path $WorkPath "PicOrgFTP-SQL.version.txt"

Set-Location $RepoRoot
. (Join-Path $ScriptDir "build_common.ps1")

Initialize-BuildEnvironment -RepoRoot $RepoRoot -VenvDir $VenvDir -Python $Python

New-Item -ItemType Directory -Path $IconDir -Force | Out-Null
New-Item -ItemType Directory -Path $WorkPath -Force | Out-Null
Invoke-Native $Python "-c" "from PIL import Image; Image.open(r'pic\PIC_LOCAL.png').save(r'$IconPath', sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])"
Invoke-Native $Python "tools\generate_windows_version_info.py" `
    --output $VersionInfoPath `
    --file-description "PicOrgFTP-SQL desktop application" `
    --internal-name "PicOrgFTP-SQL" `
    --original-filename "PicOrgFTP-SQL.exe"

$env:PICORGFTP_SQL_HEADLESS = "1"
$env:PYINSTALLER_BUILD = "1"

Invoke-Native $Python "-m" "PyInstaller" "--noconfirm" "--clean" "--log-level=WARN" `
    --name PicOrgFTP-SQL `
    --noconsole `
    --onefile `
    --distpath $ScriptDir `
    --workpath $WorkPath `
    --icon $IconPath `
    --version-file $VersionInfoPath `
    --collect-submodules mysql.connector `
    --collect-data mysql.connector `
    --collect-data certifi `
    --add-data "picorgftp_sql\Localization;picorgftp_sql\Localization" `
    --add-data "picorgftp_sql\VERSION;picorgftp_sql" `
    --add-data "pic\PIC_LOCAL.png;pic" `
    PicOrgFTP-SQL.pyw

Write-Host "OK. Wynik: $ScriptDir\PicOrgFTP-SQL.exe"
