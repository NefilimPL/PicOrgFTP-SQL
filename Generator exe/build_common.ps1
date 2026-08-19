$ErrorActionPreference = "Stop"

function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Polecenie nie powiodlo sie (kod $LASTEXITCODE): $FilePath $($Arguments -join ' ')"
    }
}

function Remove-BuildVenv {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot,
        [Parameter(Mandatory = $true)]
        [string]$VenvDir
    )

    if (-not (Test-Path $VenvDir)) {
        return
    }

    $repoPath = [System.IO.Path]::GetFullPath($RepoRoot)
    $venvPath = [System.IO.Path]::GetFullPath($VenvDir)
    $repoPrefix = $repoPath.TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    ) + [System.IO.Path]::DirectorySeparatorChar

    if (-not $venvPath.StartsWith($repoPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Odmowa usuniecia srodowiska spoza repozytorium: $venvPath"
    }

    Remove-Item -LiteralPath $venvPath -Recurse -Force
}

function New-BuildVenv {
    param(
        [Parameter(Mandatory = $true)]
        [string]$VenvDir
    )

    if (Get-Command py -ErrorAction SilentlyContinue) {
        Invoke-Native "py" "-3.11" "-m" "venv" $VenvDir
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        Invoke-Native "python" "-m" "venv" $VenvDir
    } else {
        throw "Nie znaleziono Pythona. Zainstaluj Python 3.11+ albo dodaj go do PATH."
    }
}

function Install-BuildDependencies {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Python,
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot,
        [switch]$IncludeWebDependencies,
        [switch]$IncludeVisionDependencies
    )

    Invoke-Native $Python "-m" "pip" "install" "--disable-pip-version-check" "pyinstaller>=6.6,<7"
    Invoke-Native $Python "-m" "pip" "install" "--disable-pip-version-check" "-r" (Join-Path $RepoRoot "requirements-build.txt")
    if ($IncludeWebDependencies) {
        Invoke-Native $Python "-m" "pip" "install" "--disable-pip-version-check" "-r" (Join-Path $RepoRoot "requirements-web.txt")
    }
    if ($IncludeVisionDependencies) {
        Invoke-Native $Python "-m" "pip" "install" "--disable-pip-version-check" "-r" (Join-Path $RepoRoot "requirements-vision.txt")
    }
}

function Get-WebStaticDataArguments {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot
    )

    $staticDirectory = Join-Path $RepoRoot "picorgftp_sql\web\static"
    $staticAssets = @(
        "app.css",
        "app.js",
        "autocomplete.js",
        "index.html",
        "latest-request.js",
        "login.html",
        "login.js",
        "process-jobs.js",
        "runtime-status.js"
    )
    $arguments = @()
    foreach ($asset in $staticAssets) {
        $sourcePath = Join-Path $staticDirectory $asset
        if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
            throw "Brakuje wymaganego zasobu web: $sourcePath"
        }
        $arguments += "--add-data"
        $arguments += "$sourcePath;picorgftp_sql\web\static"
    }
    return $arguments
}

function Test-BuildEnvironment {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Python,
        [switch]$IncludeWebDependencies,
        [switch]$IncludeVisionDependencies
    )

    $imports = @(
        "import PyInstaller.__main__",
        "from PIL import Image",
        "import certifi",
        "import mysql.connector",
        "import openpyxl",
        "import pystray",
        "import tkinterdnd2"
    )
    if ($IncludeWebDependencies) {
        $imports += @(
            "import fastapi",
            "import multipart",
            "import starlette",
            "import uvicorn"
        )
    }
    if ($IncludeVisionDependencies) {
        $imports += @(
            "import cv2",
            "import paddle",
            "import paddlex",
            "import paddleocr"
        )
    }

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    try {
        & $Python "-c" ($imports -join "; ") > $null 2> $null
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    return $exitCode -eq 0
}

function Initialize-BuildEnvironment {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot,
        [Parameter(Mandatory = $true)]
        [string]$VenvDir,
        [Parameter(Mandatory = $true)]
        [string]$Python,
        [switch]$IncludeWebDependencies,
        [switch]$IncludeVisionDependencies
    )

    for ($attempt = 1; $attempt -le 2; $attempt++) {
        if (-not (Test-Path $Python)) {
            if (Test-Path $VenvDir) {
                Write-Warning "Srodowisko build jest niekompletne. Usuwam i tworze ponownie: $VenvDir"
                Remove-BuildVenv -RepoRoot $RepoRoot -VenvDir $VenvDir
            }
            New-BuildVenv -VenvDir $VenvDir
        }

        Install-BuildDependencies `
            -Python $Python `
            -RepoRoot $RepoRoot `
            -IncludeWebDependencies:$IncludeWebDependencies `
            -IncludeVisionDependencies:$IncludeVisionDependencies

        if (Test-BuildEnvironment `
            -Python $Python `
            -IncludeWebDependencies:$IncludeWebDependencies `
            -IncludeVisionDependencies:$IncludeVisionDependencies) {
            return
        }

        if ($attempt -lt 2) {
            Write-Warning "Srodowisko build jest uszkodzone. Usuwam i tworze ponownie: $VenvDir"
            Remove-BuildVenv -RepoRoot $RepoRoot -VenvDir $VenvDir
        }
    }

    throw "Nie udalo sie przygotowac poprawnego srodowiska build."
}
