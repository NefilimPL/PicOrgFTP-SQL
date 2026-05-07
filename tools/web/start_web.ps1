$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$Port = if ($env:PICORG_WEB_PORT) { [int]$env:PICORG_WEB_PORT } else { 8000 }
$HostAddress = if ($env:PICORG_WEB_HOST) { $env:PICORG_WEB_HOST } else { "0.0.0.0" }
$LocalUrl = "http://127.0.0.1:$Port"
$OpenBrowser = $env:PICORG_WEB_NO_BROWSER -ne "1"
$PidFile = Join-Path $Root ".picorg_web.pid"
$OutLog = Join-Path $Root "picorg_web_out.log"
$ErrLog = Join-Path $Root "picorg_web_err.log"
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"

function Test-Python($Candidate) {
    try {
        & $Candidate --version *> $null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

$Python = if ((Test-Path $VenvPython) -and (Test-Python $VenvPython)) { $VenvPython } else { "python" }

function Write-Info($Text) {
    Write-Host "[WEB] $Text"
}

function Get-LanUrl {
    try {
        $ip = Get-NetIPAddress -AddressFamily IPv4 |
            Where-Object {
                $_.IPAddress -notlike "127.*" -and
                $_.IPAddress -notlike "169.254.*" -and
                $_.PrefixOrigin -ne "WellKnown"
            } |
            Select-Object -First 1 -ExpandProperty IPAddress
        if ($ip) {
            return "http://$ip`:$Port"
        }
    } catch {
    }
    return ""
}

function Test-WebDeps {
    $check = "__import__('fastapi'); __import__('uvicorn'); __import__('multipart')"
    Push-Location $Root
    try {
        & $Python -c $check *> $null
        return $LASTEXITCODE -eq 0
    } finally {
        Pop-Location
    }
}

function Install-WebDeps {
    Write-Info "Instaluje zaleznosci webowe z requirements-web.txt..."
    $process = Start-Process -FilePath $Python -ArgumentList @("-m", "pip", "install", "-r", "requirements-web.txt") -WorkingDirectory $Root -NoNewWindow -Wait -PassThru
    if ($process.ExitCode -ne 0) {
        throw "Nie udalo sie zainstalowac zaleznosci webowych."
    }
}

$existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($existing) {
    Write-Info "Panel albo inna usluga juz slucha na porcie $Port."
    Write-Info "Adres lokalny: $LocalUrl"
    $lanUrl = Get-LanUrl
    if ($lanUrl) {
        Write-Info "Adres w LAN: $lanUrl"
    }
    if ($OpenBrowser) {
        Start-Process $LocalUrl
    }
    exit 0
}

if (-not (Test-WebDeps)) {
    Install-WebDeps
}

$args = @(
    "-m",
    "uvicorn",
    "picorgftp_sql.web.app:app",
    "--host",
    $HostAddress,
    "--port",
    [string]$Port
)

Write-Info "Uruchamiam panel webowy..."
$process = Start-Process -FilePath $Python -ArgumentList $args -WorkingDirectory $Root -WindowStyle Hidden -RedirectStandardOutput $OutLog -RedirectStandardError $ErrLog -PassThru
Set-Content -Path $PidFile -Value $process.Id -Encoding ascii
Start-Sleep -Seconds 3

if ($process.HasExited) {
    Remove-Item -Path $PidFile -Force -ErrorAction SilentlyContinue
    Write-Info "Start nie powiodl sie. Log bledu:"
    if (Test-Path $ErrLog) {
        Get-Content -Path $ErrLog -Tail 40
    }
    exit 1
}

Write-Info "Panel dziala."
Write-Info "Adres lokalny: $LocalUrl"
$lanUrl = Get-LanUrl
if ($lanUrl) {
    Write-Info "Adres w LAN: $lanUrl"
}
Write-Info "Logi: $OutLog oraz $ErrLog"
if ($OpenBrowser) {
    Start-Process $LocalUrl
}
