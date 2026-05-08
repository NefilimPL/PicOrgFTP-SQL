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
$FirewallEnabled = $env:PICORG_WEB_FIREWALL -ne "0"
$FirewallRemoveOnStop = $env:PICORG_WEB_FIREWALL_CLOSE -ne "0"
$FirewallRuleName = if ($env:PICORG_WEB_FIREWALL_RULE) { $env:PICORG_WEB_FIREWALL_RULE } else { "PicOrgFTP-SQL Web $Port" }
$FirewallRemoteAddress = if ($env:PICORG_WEB_FIREWALL_REMOTE) { $env:PICORG_WEB_FIREWALL_REMOTE } else { "LocalSubnet" }
$FirewallProfiles = if ($env:PICORG_WEB_FIREWALL_PROFILE) {
    $env:PICORG_WEB_FIREWALL_PROFILE -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ }
} else {
    @("Private", "Domain", "Public")
}

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

function Test-Python($Candidate) {
    try {
        & $Candidate --version *> $null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

$Python = if ((Test-Path $VenvPython) -and (Test-Python $VenvPython)) { $VenvPython } else { "python" }

function Get-ProcessCommandLine($PidValue) {
    try {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $PidValue"
        return [string]$proc.CommandLine
    } catch {
        return ""
    }
}

function Test-WebProcess($PidValue) {
    $process = Get-Process -Id $PidValue -ErrorAction SilentlyContinue
    if (-not $process) {
        return $false
    }
    $cmd = Get-ProcessCommandLine $PidValue
    if ($cmd) {
        return $cmd -like "*uvicorn*" -and $cmd -like "*picorgftp_sql.web.app*"
    }
    return $process.ProcessName -in @("python", "pythonw")
}

function Get-PortListeners {
    $items = @()
    try {
        $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop
        foreach ($connection in $connections) {
            $pidValue = [int]$connection.OwningProcess
            $process = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
            $items += [pscustomobject]@{
                LocalAddress = [string]$connection.LocalAddress
                LocalPort = [int]$connection.LocalPort
                Pid = $pidValue
                ProcessName = if ($process) { $process.ProcessName } else { "" }
                CommandLine = Get-ProcessCommandLine $pidValue
                IsWebPanel = Test-WebProcess $pidValue
            }
        }
    } catch {
    }
    return $items
}

function Write-PortListeners($Listeners) {
    foreach ($listener in $Listeners) {
        $owner = if ($listener.ProcessName) { "$($listener.ProcessName), PID $($listener.Pid)" } else { "PID $($listener.Pid)" }
        Write-Info "Port $($listener.LocalPort) slucha na $($listener.LocalAddress) ($owner)."
    }
}

function Get-LanUrls {
    $items = @()
    try {
        $addresses = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
            Where-Object {
                $_.IPAddress -notlike "127.*" -and
                $_.IPAddress -notlike "169.254.*" -and
                $_.AddressState -eq "Preferred"
            }
        foreach ($address in $addresses) {
            $items += [pscustomobject]@{
                Url = "http://$($address.IPAddress):$Port"
                InterfaceAlias = [string]$address.InterfaceAlias
            }
        }
    } catch {
    }
    return $items
}

function Write-Urls {
    Write-Info "Adres lokalny: $LocalUrl"
    $lanUrls = Get-LanUrls
    foreach ($item in $lanUrls) {
        Write-Info "Adres w sieci: $($item.Url) ($($item.InterfaceAlias))"
    }
    if (-not $lanUrls -or $lanUrls.Count -eq 0) {
        Write-Info "Nie wykryto adresu IPv4 LAN. Sprawdz ipconfig."
    }
}

function Get-WebFirewallRule {
    if (-not (Get-Command Get-NetFirewallRule -ErrorAction SilentlyContinue)) {
        return $null
    }
    return Get-NetFirewallRule -DisplayName $FirewallRuleName -ErrorAction SilentlyContinue | Select-Object -First 1
}

function Ensure-FirewallRule {
    $result = [ordered]@{
        enabled = $FirewallEnabled
        created = $false
        exists = $false
        rule_name = $FirewallRuleName
        remove_on_stop = $FirewallRemoveOnStop
    }
    if (-not $FirewallEnabled) {
        Write-Info "Automatyczna regula firewall jest wylaczona (PICORG_WEB_FIREWALL=0)."
        return $result
    }
    if (-not (Get-Command New-NetFirewallRule -ErrorAction SilentlyContinue)) {
        Write-Info "Brak cmdletow Windows Firewall. Pominieto automatyczne odblokowanie portu."
        return $result
    }
    $existingRule = Get-WebFirewallRule
    if ($existingRule) {
        $result.exists = $true
        Write-Info "Regula firewall juz istnieje: $FirewallRuleName."
        return $result
    }
    if (-not (Test-Administrator)) {
        Write-Info "Brak uprawnien administratora, nie moge dodac reguly firewall."
        Write-Info "Uruchom START_WEB.bat jako administrator albo wykonaj:"
        Write-Info "New-NetFirewallRule -DisplayName `"$FirewallRuleName`" -Direction Inbound -Protocol TCP -LocalPort $Port -Action Allow -Profile $($FirewallProfiles -join ',') -RemoteAddress $FirewallRemoteAddress"
        return $result
    }
    try {
        New-NetFirewallRule `
            -DisplayName $FirewallRuleName `
            -Group "PicOrgFTP-SQL" `
            -Direction Inbound `
            -Protocol TCP `
            -LocalPort $Port `
            -Action Allow `
            -Profile $FirewallProfiles `
            -RemoteAddress $FirewallRemoteAddress `
            -Description "Created by PicOrgFTP-SQL web start script. RemoveOnStop=$FirewallRemoveOnStop" | Out-Null
        $result.created = $true
        $result.exists = $true
        Write-Info "Dodano regule firewall: $FirewallRuleName (RemoteAddress: $FirewallRemoteAddress)."
    } catch {
        Write-Info "Nie udalo sie dodac reguly firewall: $($_.Exception.Message)"
    }
    return $result
}

function Remove-FirewallRuleIfNeeded($FirewallState) {
    if (-not $FirewallState.created -or -not $FirewallState.remove_on_stop) {
        return
    }
    if (-not (Test-Administrator)) {
        return
    }
    try {
        Get-NetFirewallRule -DisplayName $FirewallState.rule_name -ErrorAction SilentlyContinue | Remove-NetFirewallRule
        Write-Info "Usunieto regule firewall po nieudanym starcie: $($FirewallState.rule_name)."
    } catch {
    }
}

function Write-RunMetadata($PidValue, $FirewallState) {
    $payload = [ordered]@{
        pid = [int]$PidValue
        port = [int]$Port
        host = $HostAddress
        firewall_rule_name = [string]$FirewallState.rule_name
        firewall_rule_created = [bool]$FirewallState.created
        firewall_remove_on_stop = [bool]$FirewallState.remove_on_stop
        started_at = (Get-Date).ToString("s")
    }
    $payload | ConvertTo-Json | Set-Content -Path $PidFile -Encoding ascii
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

$listeners = @(Get-PortListeners)
if ($listeners.Count -gt 0) {
    Write-Info "Port $Port jest juz uzywany."
    Write-PortListeners $listeners
    $webListener = $listeners | Where-Object { $_.IsWebPanel } | Select-Object -First 1
    if (-not $webListener) {
        Write-Info "Na tym porcie dziala inna usluga. Nie otwieram firewall dla obcego procesu."
        Write-Info "Zmien port, np.: `$env:PICORG_WEB_PORT=`"8080`"; .\START_WEB.bat"
        exit 1
    }
    $firewallState = Ensure-FirewallRule
    Write-RunMetadata $webListener.Pid $firewallState
    Write-Info "Panel webowy juz dziala."
    Write-Urls
    Write-Info "Z drugiego PC uzyj adresu z aktywnej karty Ethernet/Wi-Fi, nie VPN."
    if ($OpenBrowser) {
        Start-Process $LocalUrl
    }
    exit 0
}

if (-not (Test-WebDeps)) {
    Install-WebDeps
}

$firewallState = Ensure-FirewallRule

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
try {
    $process = Start-Process -FilePath $Python -ArgumentList $args -WorkingDirectory $Root -WindowStyle Hidden -RedirectStandardOutput $OutLog -RedirectStandardError $ErrLog -PassThru
} catch {
    Remove-FirewallRuleIfNeeded $firewallState
    Write-Info "Start nie powiodl sie: $($_.Exception.Message)"
    exit 1
}
Write-RunMetadata $process.Id $firewallState
Start-Sleep -Seconds 3

if ($process.HasExited) {
    Remove-Item -Path $PidFile -Force -ErrorAction SilentlyContinue
    Remove-FirewallRuleIfNeeded $firewallState
    Write-Info "Start nie powiodl sie. Log bledu:"
    if (Test-Path $ErrLog) {
        Get-Content -Path $ErrLog -Tail 40
    }
    exit 1
}

Write-Info "Panel dziala."
Write-Urls
Write-Info "Port: $Port, host: $HostAddress"
Write-Info "Logi: $OutLog oraz $ErrLog"
Write-Info "Z drugiego PC uzyj adresu z aktywnej karty Ethernet/Wi-Fi, nie VPN."
if ($OpenBrowser) {
    Start-Process $LocalUrl
}
