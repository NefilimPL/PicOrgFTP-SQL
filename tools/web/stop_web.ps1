$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$Port = if ($env:PICORG_WEB_PORT) { [int]$env:PICORG_WEB_PORT } else { 8000 }
$PidFile = Join-Path $Root ".picorg_web.pid"

function Write-Info($Text) {
    Write-Host "[WEB] $Text"
}

function Test-WebProcess($PidValue) {
    $process = Get-Process -Id $PidValue -ErrorAction SilentlyContinue
    if (-not $process) {
        return $false
    }
    try {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $PidValue"
        $cmd = [string]$proc.CommandLine
        if ($cmd) {
            return $cmd -like "*uvicorn*" -and $cmd -like "*picorgftp_sql.web.app*"
        }
    } catch {
    }
    return $process.ProcessName -in @("python", "pythonw")
}

function Get-PortListenerPids {
    $pids = @()
    try {
        $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop
        foreach ($connection in $connections) {
            $pids += [int]$connection.OwningProcess
        }
    } catch {
    }
    if ($pids.Count -eq 0) {
        $lines = netstat -ano | Where-Object {
            $_ -match ":$Port\s" -and $_ -match "\sLISTENING\s+(\d+)\s*$"
        }
        foreach ($line in $lines) {
            if ($line -match "\sLISTENING\s+(\d+)\s*$") {
                $pids += [int]$Matches[1]
            }
        }
    }
    return $pids | Select-Object -Unique
}

function Stop-WebPid($PidValue) {
    if (-not (Test-WebProcess $PidValue)) {
        return $false
    }
    Stop-Process -Id $PidValue -Force
    return $true
}

$stopped = $false

if (Test-Path $PidFile) {
    $rawPid = (Get-Content -Path $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    $pidValue = 0
    if ([int]::TryParse([string]$rawPid, [ref]$pidValue)) {
        if (Stop-WebPid $pidValue) {
            Write-Info "Zatrzymano panel webowy, PID $pidValue."
            $stopped = $true
        }
    }
    Remove-Item -Path $PidFile -Force -ErrorAction SilentlyContinue
}

if (-not $stopped) {
    foreach ($pidValue in Get-PortListenerPids) {
        if (Stop-WebPid $pidValue) {
            Write-Info "Zatrzymano panel webowy na porcie $Port, PID $pidValue."
            $stopped = $true
        }
    }
}

if (-not $stopped) {
    Write-Info "Panel webowy nie byl uruchomiony albo na porcie $Port dziala inna usluga."
}
