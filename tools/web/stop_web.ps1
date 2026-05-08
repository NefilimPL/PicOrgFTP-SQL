$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$Port = if ($env:PICORG_WEB_PORT) { [int]$env:PICORG_WEB_PORT } else { 8000 }
$PidFile = Join-Path $Root ".picorg_web.pid"

function Write-Info($Text) {
    Write-Host "[WEB] $Text"
}

function Test-Administrator {
    try {
        $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
        $principal = [Security.Principal.WindowsPrincipal]::new($identity)
        return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    } catch {
        return $false
    }
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

function Read-RunMetadata {
    if (-not (Test-Path $PidFile)) {
        return $null
    }
    $content = Get-Content -Path $PidFile -Raw -ErrorAction SilentlyContinue
    if (-not $content) {
        return $null
    }
    try {
        return $content | ConvertFrom-Json
    } catch {
        $pidValue = 0
        $firstLine = ($content -split "`r?`n" | Select-Object -First 1)
        if ([int]::TryParse([string]$firstLine, [ref]$pidValue)) {
            return [pscustomobject]@{
                pid = $pidValue
                port = $Port
                firewall_rule_created = $false
                firewall_remove_on_stop = $false
                firewall_rule_name = ""
            }
        }
    }
    return $null
}

function Remove-FirewallRuleFromMetadata($Metadata) {
    if (-not $Metadata) {
        return
    }
    if (-not $Metadata.firewall_rule_created -or -not $Metadata.firewall_remove_on_stop) {
        return
    }
    $ruleName = [string]$Metadata.firewall_rule_name
    if (-not $ruleName) {
        return
    }
    if (-not (Get-Command Remove-NetFirewallRule -ErrorAction SilentlyContinue)) {
        Write-Info "Brak cmdletow Windows Firewall. Regula pozostaje: $ruleName."
        return
    }
    if (-not (Test-Administrator)) {
        Write-Info "Brak uprawnien administratora, nie moge usunac reguly firewall."
        Write-Info "Uruchom STOP_WEB.bat jako administrator albo wykonaj:"
        Write-Info "Remove-NetFirewallRule -DisplayName `"$ruleName`""
        return
    }
    try {
        Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
        Write-Info "Usunieto regule firewall: $ruleName."
    } catch {
        Write-Info "Nie udalo sie usunac reguly firewall: $($_.Exception.Message)"
    }
}

$stopped = $false
$metadata = Read-RunMetadata
if ($metadata -and $metadata.port) {
    $Port = [int]$metadata.port
}

if ($metadata -and $metadata.pid) {
    $pidValue = [int]$metadata.pid
    if (Stop-WebPid $pidValue) {
        Write-Info "Zatrzymano panel webowy, PID $pidValue."
        $stopped = $true
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

Remove-FirewallRuleFromMetadata $metadata
