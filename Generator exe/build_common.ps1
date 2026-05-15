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
        [switch]$IncludeWebDependencies
    )

    Invoke-Native $Python "-m" "pip" "install" "--disable-pip-version-check" "pyinstaller>=6.6,<7"
    Invoke-Native $Python "-m" "pip" "install" "--disable-pip-version-check" "-r" (Join-Path $RepoRoot "requirements-build.txt")
    if ($IncludeWebDependencies) {
        Invoke-Native $Python "-m" "pip" "install" "--disable-pip-version-check" "-r" (Join-Path $RepoRoot "requirements-web.txt")
    }
}

function Test-BuildEnvironment {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Python,
        [switch]$IncludeWebDependencies
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
        [switch]$IncludeWebDependencies
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
            -IncludeWebDependencies:$IncludeWebDependencies

        if (Test-BuildEnvironment -Python $Python -IncludeWebDependencies:$IncludeWebDependencies) {
            return
        }

        if ($attempt -lt 2) {
            Write-Warning "Srodowisko build jest uszkodzone. Usuwam i tworze ponownie: $VenvDir"
            Remove-BuildVenv -RepoRoot $RepoRoot -VenvDir $VenvDir
        }
    }

    throw "Nie udalo sie przygotowac poprawnego srodowiska build."
}
