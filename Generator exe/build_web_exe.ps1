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
$BuildName = if ($IncludeVisionModels) { "PicOrgFTP-SQL-WEB-OCR" } elseif ($IncludeVision) { "PicOrgFTP-SQL-WEB-OCR-ONLINE" } else { "PicOrgFTP-SQL-WEB" }
$WorkPath = Join-Path $RepoRoot ("build\\web-exe-" + $BuildName)
$VersionInfoPath = Join-Path $WorkPath ($BuildName + ".version.txt")

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
    --internal-name $BuildName `
    --original-filename ($BuildName + ".exe")
$ModuleBuildVariant = if ($IncludeVisionModels) { "web-ocr" } else { "web" }
$ModuleBuildManifestArguments = New-ModuleBuildManifestArguments `
    -Python $Python `
    -RepoRoot $RepoRoot `
    -WorkPath $WorkPath `
    -BuildVariant $ModuleBuildVariant

$env:PICORGFTP_SQL_HEADLESS = "1"
$env:PYINSTALLER_BUILD = "1"
$WebStaticDataArguments = Get-WebStaticDataArguments -RepoRoot $RepoRoot
$VisionPyInstallerArguments = @()
if (-not $IncludeVision) {
    $VisionPyInstallerArguments += "--runtime-hook"
    $VisionPyInstallerArguments += (Join-Path $ScriptDir "disable_ocr_runtime.py")
}
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
    $PrepareVisionModels = @"
import os
from picorgftp_sql.services.image_dimensions import _model_cache_has_profile
from picorgftp_sql.services.ocr_profiles import available_ocr_profiles

cache = os.environ['PADDLE_PDX_CACHE_HOME']
profiles = available_ocr_profiles()
missing = [profile for profile in profiles if not _model_cache_has_profile(cache, profile)]
if missing:
    from paddleocr import PaddleOCR
    for profile in missing:
        PaddleOCR(
            text_detection_model_name=profile.detector_model,
            text_recognition_model_name=profile.recognizer_model,
            enable_mkldnn=False,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
missing = [profile.id for profile in profiles if not _model_cache_has_profile(cache, profile)]
if missing:
    raise RuntimeError('Brakuje modeli OCR po przygotowaniu builda: ' + ', '.join(missing))
"@
    Invoke-Native $Python "-c" $PrepareVisionModels
    if (-not (Test-Path -LiteralPath $VisionModelCache -PathType Container)) {
        throw "Nie znaleziono lokalnego cache modeli OCR po przygotowaniu builda."
    }
    $VisionPyInstallerArguments += "--add-data"
    $VisionPyInstallerArguments += "$VisionModelCache;ocr_models"
}

Invoke-Native $Python "-m" "PyInstaller" "--noconfirm" "--clean" "--log-level=WARN" `
    --name $BuildName `
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
    @ModuleBuildManifestArguments `
    --add-data "picorgftp_sql\browser_extension;picorgftp_sql\browser_extension" `
    --add-data "picorgftp_sql\Localization;picorgftp_sql\Localization" `
    --add-data "picorgftp_sql\VERSION;picorgftp_sql" `
    --add-data "pic\PIC_WEB.png;pic" `
    PicOrgFTP-SQL-WEB.pyw

Write-Host "OK. Wynik: $ScriptDir\$BuildName.exe"
