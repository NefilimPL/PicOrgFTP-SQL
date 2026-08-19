param(
    [switch]$IncludeVision,
    [switch]$IncludeVisionModels
)

$ErrorActionPreference = "Stop"

if ($IncludeVisionModels -and -not $IncludeVision) {
    throw "IncludeVisionModels wymaga parametru -IncludeVision."
}

$ScriptDir = $PSScriptRoot
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
$VenvDir = Join-Path $RepoRoot ".venv-build"
$Python = Join-Path $VenvDir "Scripts\python.exe"
$IconDir = Join-Path $ScriptDir ".icons"
$IconPath = Join-Path $IconDir "PIC_WEB.ico"
$WorkPath = Join-Path $RepoRoot "build\web-exe"
$VersionInfoPath = Join-Path $WorkPath "PicOrgFTP-SQL-WEB.version.txt"

Set-Location $RepoRoot
. (Join-Path $ScriptDir "build_common.ps1")

Initialize-BuildEnvironment `
    -RepoRoot $RepoRoot `
    -VenvDir $VenvDir `
    -Python $Python `
    -IncludeWebDependencies `
    -IncludeVisionDependencies:$IncludeVision

New-Item -ItemType Directory -Path $IconDir -Force | Out-Null
New-Item -ItemType Directory -Path $WorkPath -Force | Out-Null
Invoke-Native $Python "-c" "from PIL import Image; Image.open(r'pic\PIC_WEB.png').save(r'$IconPath', sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])"
Invoke-Native $Python "tools\generate_windows_version_info.py" `
    --output $VersionInfoPath `
    --file-description "PicOrgFTP-SQL web manager" `
    --internal-name "PicOrgFTP-SQL-WEB" `
    --original-filename "PicOrgFTP-SQL-WEB.exe"

$env:PICORGFTP_SQL_HEADLESS = "1"
$env:PYINSTALLER_BUILD = "1"
$WebStaticDataArguments = Get-WebStaticDataArguments -RepoRoot $RepoRoot
$VisionPyInstallerArguments = @()
if ($IncludeVision) {
    foreach ($package in @("paddleocr", "paddlex", "paddle", "cv2", "bidi", "imagesize", "pyclipper", "pypdfium2", "shapely")) {
        $VisionPyInstallerArguments += "--collect-all"
        $VisionPyInstallerArguments += $package
    }
}
if ($IncludeVisionModels) {
    $VisionModelCache = Join-Path $WorkPath "ocr-model-cache"
    New-Item -ItemType Directory -Path $VisionModelCache -Force | Out-Null
    $env:PADDLE_PDX_CACHE_HOME = $VisionModelCache
    Invoke-Native $Python "-c" "from paddleocr import PaddleOCR; PaddleOCR(lang='en')"
    if (-not (Test-Path -LiteralPath $VisionModelCache -PathType Container)) {
        throw "Nie znaleziono lokalnego cache modeli OCR po przygotowaniu builda."
    }
    $VisionPyInstallerArguments += "--add-data"
    $VisionPyInstallerArguments += "$VisionModelCache;ocr_models"
}

Invoke-Native $Python "-m" "PyInstaller" "--noconfirm" "--clean" "--log-level=WARN" `
    --name PicOrgFTP-SQL-WEB `
    --noconsole `
    --onefile `
    --distpath $ScriptDir `
    --workpath $WorkPath `
    --icon $IconPath `
    --version-file $VersionInfoPath `
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
    @VisionPyInstallerArguments `
    @WebStaticDataArguments `
    --add-data "picorgftp_sql\browser_extension;picorgftp_sql\browser_extension" `
    --add-data "picorgftp_sql\Localization;picorgftp_sql\Localization" `
    --add-data "picorgftp_sql\VERSION;picorgftp_sql" `
    --add-data "pic\PIC_WEB.png;pic" `
    PicOrgFTP-SQL-WEB.pyw

Write-Host "OK. Wynik: $ScriptDir\PicOrgFTP-SQL-WEB.exe"
