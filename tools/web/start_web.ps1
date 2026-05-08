$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$Port = if ($env:PICORG_WEB_PORT) { [int]$env:PICORG_WEB_PORT } else { 8010 }
$HostAddress = if ($env:PICORG_WEB_HOST) { $env:PICORG_WEB_HOST } else { "0.0.0.0" }
$LocalUrl = "http://127.0.0.1:$Port"
$OpenBrowser = $env:PICORG_WEB_NO_BROWSER -ne "1"
$StarterMenu = $env:PICORG_WEB_STARTER_MENU -ne "0"
$PidFile = Join-Path $Root ".picorg_web.pid"
$OutLog = Join-Path $Root "picorg_web_out.log"
$ErrLog = Join-Path $Root "picorg_web_err.log"
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$FirewallEnabled = $env:PICORG_WEB_FIREWALL -ne "0"
$FirewallRemoveOnStop = $env:PICORG_WEB_FIREWALL_CLOSE -ne "0"
$CustomFirewallRuleName = [bool]$env:PICORG_WEB_FIREWALL_RULE
$CustomFirewallBlockRuleName = [bool]$env:PICORG_WEB_FIREWALL_BLOCK_RULE
$FirewallRuleName = if ($env:PICORG_WEB_FIREWALL_RULE) { $env:PICORG_WEB_FIREWALL_RULE } else { "Allow TCP $Port" }
$FirewallBlockRuleName = if ($env:PICORG_WEB_FIREWALL_BLOCK_RULE) { $env:PICORG_WEB_FIREWALL_BLOCK_RULE } else { "Block TCP $Port" }
$FirewallRemoteAddress = if ($env:PICORG_WEB_FIREWALL_REMOTE) { $env:PICORG_WEB_FIREWALL_REMOTE } else { "Any" }
$FirewallInterfaceAlias = if ($env:PICORG_WEB_FIREWALL_INTERFACE) { $env:PICORG_WEB_FIREWALL_INTERFACE } else { "" }
$FirewallProfiles = if ($env:PICORG_WEB_FIREWALL_PROFILE) {
    $env:PICORG_WEB_FIREWALL_PROFILE -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ }
} else {
    @("Any")
}

function Write-Info($Text) {
    Write-Host "[WEB] $Text"
}

function Set-WebPort($NewPort) {
    $script:Port = [int]$NewPort
    $script:LocalUrl = "http://127.0.0.1:$script:Port"
    if (-not $script:CustomFirewallRuleName) {
        $script:FirewallRuleName = "Allow TCP $script:Port"
    }
    if (-not $script:CustomFirewallBlockRuleName) {
        $script:FirewallBlockRuleName = "Block TCP $script:Port"
    }
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

function Stop-WebProcessIfSafe($PidValue) {
    if (-not (Test-WebProcess $PidValue)) {
        return $false
    }
    Stop-Process -Id $PidValue -Force
    return $true
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
    if ($items.Count -eq 0) {
        try {
            $lines = netstat -ano | Where-Object {
                $_ -match ":$Port\s" -and $_ -match "\sLISTENING\s+(\d+)\s*$"
            }
            foreach ($line in $lines) {
                if ($line -match "^\s*TCP\s+(\S+):$Port\s+\S+\s+LISTENING\s+(\d+)\s*$") {
                    $pidValue = [int]$Matches[2]
                    $process = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
                    $items += [pscustomobject]@{
                        LocalAddress = [string]$Matches[1]
                        LocalPort = [int]$Port
                        Pid = $pidValue
                        ProcessName = if ($process) { $process.ProcessName } else { "" }
                        CommandLine = Get-ProcessCommandLine $pidValue
                        IsWebPanel = Test-WebProcess $pidValue
                    }
                }
            }
        } catch {
        }
    }
    return $items
}

function Write-PortListeners($Listeners) {
    foreach ($listener in $Listeners) {
        $owner = if ($listener.ProcessName) { "$($listener.ProcessName), PID $($listener.Pid)" } else { "PID $($listener.Pid)" }
        Write-Info "Port $($listener.LocalPort) slucha na $($listener.LocalAddress) ($owner)."
    }
}

function Read-AlternatePort {
    while ($true) {
        $value = Read-Host "Podaj inny port, np. 8011, albo Enter aby przerwac"
        if (-not $value) {
            return $null
        }
        $newPort = 0
        if ([int]::TryParse($value, [ref]$newPort) -and $newPort -ge 1 -and $newPort -le 65535) {
            return $newPort
        }
        Write-Info "Niepoprawny port. Dozwolony zakres: 1-65535."
    }
}

function Resolve-PortConflict {
    while ($true) {
        $listeners = @(Get-PortListeners)
        if ($listeners.Count -eq 0) {
            return
        }

        Write-Info "Port $Port jest juz uzywany."
        Write-PortListeners $listeners
        $webListeners = @($listeners | Where-Object { $_.IsWebPanel })

        if ($webListeners.Count -gt 0) {
            Write-Info "Wykryto juz uruchomiony panel PicOrg Web na porcie $Port."
            Write-Info "K = uzyj dzialajacego panelu, R = restartuj panel, P = wybierz inny port, Q = przerwij"
            $choice = (Read-Host "Decyzja [K/R/P/Q]").Trim().ToUpperInvariant()
            if (-not $choice) {
                $choice = "K"
            }
            switch ($choice) {
                "K" {
                    $firewallState = Ensure-FirewallRule
                    Write-RunMetadata $webListeners[0].Pid $firewallState
                    Write-Info "Panel webowy juz dziala."
                    Write-Urls
                    Write-StartupDiagnostics
                    Write-Info "Z drugiego PC uzyj adresu z aktywnej karty Ethernet/Wi-Fi, nie VPN."
                    if ($OpenBrowser) {
                        Start-Process $LocalUrl
                    }
                    Show-StarterMenu
                    exit 0
                }
                "R" {
                    foreach ($listener in $webListeners) {
                        if (Stop-WebProcessIfSafe $listener.Pid) {
                            Write-Info "Zatrzymano panel webowy, PID $($listener.Pid)."
                        }
                    }
                    Start-Sleep -Seconds 1
                    continue
                }
                "P" {
                    $newPort = Read-AlternatePort
                    if (-not $newPort) {
                        exit 1
                    }
                    Set-WebPort $newPort
                    Write-Info "Wybrano port $Port."
                    continue
                }
                "Q" {
                    exit 1
                }
                default {
                    Write-Info "Nieznana decyzja."
                    continue
                }
            }
        }

        Write-Info "Na porcie $Port dziala inna usluga. Nie zatrzymuje jej i nie otwieram firewall dla obcego procesu."
        Write-Info "P = wybierz inny port, Q = przerwij"
        $choice = (Read-Host "Decyzja [P/Q]").Trim().ToUpperInvariant()
        if ($choice -eq "P") {
            $newPort = Read-AlternatePort
            if (-not $newPort) {
                exit 1
            }
            Set-WebPort $newPort
            Write-Info "Wybrano port $Port."
            continue
        }
        exit 1
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

function Test-LocalTcpPort {
    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $async = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        $success = $async.AsyncWaitHandle.WaitOne(1500)
        if ($success -and $client.Connected) {
            $client.EndConnect($async)
            $client.Close()
            return $true
        }
        $client.Close()
    } catch {
    }
    return $false
}

function Write-NetstatForPort {
    Write-Info "netstat dla portu ${Port}:"
    try {
        $lines = netstat -ano | Select-String ":$Port"
        if ($lines) {
            $lines | ForEach-Object { Write-Host $_.Line }
        } else {
            Write-Info "Brak wpisow netstat dla portu $Port."
        }
    } catch {
        Write-Info "Nie udalo sie wykonac netstat: $($_.Exception.Message)"
    }
}

function Wait-WebPortReady($PidValue) {
    $deadline = (Get-Date).AddSeconds(20)
    while ((Get-Date) -lt $deadline) {
        $process = Get-Process -Id $PidValue -ErrorAction SilentlyContinue
        if (-not $process -or $process.HasExited) {
            return $false
        }
        if (Test-LocalTcpPort) {
            return $true
        }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Write-StartupDiagnostics {
    Write-NetstatForPort
    $listeners = @(Get-PortListeners)
    if ($listeners.Count -gt 0) {
        Write-PortListeners $listeners
    } else {
        Write-Info "Nie wykryto procesu LISTENING na porcie $Port."
    }
    $localTcp = Test-LocalTcpPort
    Write-Info "Test TCP 127.0.0.1:$Port = $localTcp"
    $rule = Get-WebFirewallRule
    if ($rule) {
        Write-FirewallRuleSummary $rule
    } else {
        Write-Info "Nie znaleziono reguly firewall: $FirewallRuleName."
    }
}

function Get-WebEstablishedConnections {
    $items = @()
    try {
        $connections = Get-NetTCPConnection -LocalPort $Port -State Established -ErrorAction Stop
        foreach ($connection in $connections) {
            $items += [pscustomobject]@{
                LocalAddress = [string]$connection.LocalAddress
                LocalPort = [int]$connection.LocalPort
                RemoteAddress = [string]$connection.RemoteAddress
                RemotePort = [int]$connection.RemotePort
                State = [string]$connection.State
                Pid = [int]$connection.OwningProcess
            }
        }
    } catch {
    }
    if ($items.Count -eq 0) {
        try {
            $lines = netstat -ano | Where-Object {
                $_ -match ":$Port\s" -and $_ -match "\sESTABLISHED\s+(\d+)\s*$"
            }
            foreach ($line in $lines) {
                if ($line -match "^\s*TCP\s+(\S+):$Port\s+(\S+):(\d+)\s+ESTABLISHED\s+(\d+)\s*$") {
                    $items += [pscustomobject]@{
                        LocalAddress = [string]$Matches[1]
                        LocalPort = [int]$Port
                        RemoteAddress = [string]$Matches[2]
                        RemotePort = [int]$Matches[3]
                        State = "Established"
                        Pid = [int]$Matches[4]
                    }
                }
            }
        } catch {
        }
    }
    return $items
}

function Test-WebAccessLogLine($Line) {
    if (-not $Line) {
        return $false
    }
    return $Line -match 'HTTP/\d(\.\d)?"' -or $Line -match ' - "[A-Z]+ '
}

function Watch-WebConnections {
    Write-Info "Monitor polaczen TCP na porcie $Port."
    Write-Info "Otworz panel z innego PC. Pokaze aktywne TCP oraz nowe wpisy HTTP z logu."
    Write-Info "Nacisnij Q, Enter albo Esc, zeby zakonczyc monitoring."
    $seen = @{}
    $seenLogLines = @{}
    if (Test-Path $OutLog) {
        try {
            Get-Content -Path $OutLog -Tail 80 -ErrorAction SilentlyContinue |
                Where-Object { Test-WebAccessLogLine $_ } |
                ForEach-Object { $seenLogLines[[string]$_] = $true }
        } catch {
        }
    }
    $lastIdleMessage = Get-Date
    while ($true) {
        try {
            if ([Console]::KeyAvailable) {
                $key = [Console]::ReadKey($true)
                if ($key.Key -in @("Q", "Enter", "Escape")) {
                    Write-Info "Monitoring zakonczony. Panel webowy nadal dziala w tle."
                    return
                }
            }
        } catch {
        }

        $connections = @(Get-WebEstablishedConnections)
        foreach ($connection in $connections) {
            $key = "$($connection.LocalAddress):$($connection.LocalPort)<-$($connection.RemoteAddress):$($connection.RemotePort)"
            if (-not $seen.ContainsKey($key)) {
                $seen[$key] = $true
                $stamp = (Get-Date).ToString("HH:mm:ss")
                Write-Info "$stamp polaczenie: $($connection.RemoteAddress):$($connection.RemotePort) -> $($connection.LocalAddress):$($connection.LocalPort), PID $($connection.Pid)"
            }
        }

        if (Test-Path $OutLog) {
            try {
                $logLines = Get-Content -Path $OutLog -Tail 80 -ErrorAction SilentlyContinue |
                    Where-Object { Test-WebAccessLogLine $_ }
                foreach ($line in $logLines) {
                    $logKey = [string]$line
                    if (-not $seenLogLines.ContainsKey($logKey)) {
                        $seenLogLines[$logKey] = $true
                        Write-Info "HTTP: $line"
                    }
                }
            } catch {
            }
        }

        if ($connections.Count -eq 0 -and ((Get-Date) - $lastIdleMessage).TotalSeconds -ge 15) {
            Write-Info "Czekam na polaczenie z innego PC..."
            $lastIdleMessage = Get-Date
        }
        Start-Sleep -Milliseconds 700
    }
}

function Show-StarterMenu {
    if (-not $StarterMenu) {
        return
    }
    Write-Host ""
    Write-Info "M = monitoruj polaczenia z innych PC, Enter = zamknij starter (panel dziala w tle)"
    $choice = (Read-Host "Decyzja [M/Enter]").Trim().ToUpperInvariant()
    if ($choice -eq "M") {
        Watch-WebConnections
    }
}

function Get-WebFirewallRule {
    if (-not (Get-Command Get-NetFirewallRule -ErrorAction SilentlyContinue)) {
        return $null
    }
    return Get-NetFirewallRule -DisplayName $FirewallRuleName -ErrorAction SilentlyContinue | Select-Object -First 1
}

function Remove-WebBlockFirewallRule {
    if (-not $FirewallEnabled) {
        return
    }
    if (-not (Get-Command Remove-NetFirewallRule -ErrorAction SilentlyContinue)) {
        return
    }
    $blockRule = Get-NetFirewallRule -DisplayName $FirewallBlockRuleName -ErrorAction SilentlyContinue
    if (-not $blockRule) {
        return
    }
    if (-not (Test-Administrator)) {
        Write-Info "Istnieje regula blokujaca '$FirewallBlockRuleName', ale bez administratora nie moge jej usunac."
        Write-Info "Uruchom START_WEB.bat jako administrator albo wykonaj:"
        Write-Info "Remove-NetFirewallRule -DisplayName `"$FirewallBlockRuleName`""
        return
    }
    try {
        $blockRule | Remove-NetFirewallRule
        Write-Info "Usunieto regule blokujaca firewall: $FirewallBlockRuleName."
    } catch {
        Write-Info "Nie udalo sie usunac reguly blokujacej firewall: $($_.Exception.Message)"
    }
}

function Write-FirewallRuleSummary($Rule) {
    try {
        $portFilter = $Rule | Get-NetFirewallPortFilter
        $addressFilter = $Rule | Get-NetFirewallAddressFilter
        $interfaceFilter = $Rule | Get-NetFirewallInterfaceFilter
        Write-Info "Firewall: Enabled=$($Rule.Enabled), Profile=$($Rule.Profile), LocalPort=$($portFilter.LocalPort), RemoteAddress=$($addressFilter.RemoteAddress), InterfaceAlias=$($interfaceFilter.InterfaceAlias)."
    } catch {
        Write-Info "Nie udalo sie odczytac szczegolow reguly firewall: $($_.Exception.Message)"
    }
}

function Update-ExistingFirewallRule($Rule) {
    if (-not (Test-Administrator)) {
        Write-Info "Regula firewall juz istnieje, ale bez administratora nie moge jej poprawic."
        Write-FirewallRuleSummary $Rule
        Write-Info "Uruchom START_WEB.bat jako administrator, zeby wymusic port/profil/adres reguly."
        return
    }
    try {
        $Rule | Set-NetFirewallRule `
            -Enabled True `
            -Direction Inbound `
            -Action Allow `
            -Profile $FirewallProfiles
        $Rule | Get-NetFirewallPortFilter | Set-NetFirewallPortFilter `
            -Protocol TCP `
            -LocalPort $Port
        $Rule | Get-NetFirewallAddressFilter | Set-NetFirewallAddressFilter `
            -RemoteAddress $FirewallRemoteAddress
        if ($FirewallInterfaceAlias) {
            $Rule | Get-NetFirewallInterfaceFilter | Set-NetFirewallInterfaceFilter `
                -InterfaceAlias $FirewallInterfaceAlias
        }
        Write-Info "Zaktualizowano regule firewall: $FirewallRuleName."
        Write-FirewallRuleSummary (Get-WebFirewallRule)
    } catch {
        Write-Info "Nie udalo sie zaktualizowac reguly firewall: $($_.Exception.Message)"
    }
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
    Remove-WebBlockFirewallRule
    $existingRule = Get-WebFirewallRule
    if ($existingRule) {
        $result.exists = $true
        Write-Info "Regula firewall juz istnieje: $FirewallRuleName."
        Update-ExistingFirewallRule $existingRule
        return $result
    }
    if (-not (Test-Administrator)) {
        Write-Info "Brak uprawnien administratora, nie moge dodac reguly firewall."
        Write-Info "Uruchom START_WEB.bat jako administrator albo wykonaj:"
        $manualCommand = "New-NetFirewallRule -DisplayName `"$FirewallRuleName`" -Direction Inbound -Protocol TCP -LocalPort $Port -Action Allow -Profile $($FirewallProfiles -join ',') -RemoteAddress $FirewallRemoteAddress"
        if ($FirewallInterfaceAlias) {
            $manualCommand = "$manualCommand -InterfaceAlias `"$FirewallInterfaceAlias`""
        }
        Write-Info $manualCommand
        return $result
    }
    try {
        $ruleArgs = @{
            DisplayName = $FirewallRuleName
            Group = "PicOrgFTP-SQL"
            Direction = "Inbound"
            Protocol = "TCP"
            LocalPort = $Port
            Action = "Allow"
            Profile = $FirewallProfiles
            RemoteAddress = $FirewallRemoteAddress
            Description = "Created by PicOrgFTP-SQL web start script. RemoveOnStop=$FirewallRemoveOnStop"
        }
        if ($FirewallInterfaceAlias) {
            $ruleArgs.InterfaceAlias = $FirewallInterfaceAlias
        }
        New-NetFirewallRule @ruleArgs | Out-Null
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

Resolve-PortConflict

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
Start-Sleep -Seconds 1

if ($process.HasExited) {
    Remove-Item -Path $PidFile -Force -ErrorAction SilentlyContinue
    Remove-FirewallRuleIfNeeded $firewallState
    Write-Info "Start nie powiodl sie. Log bledu:"
    if (Test-Path $ErrLog) {
        Get-Content -Path $ErrLog -Tail 40
    }
    exit 1
}

if (-not (Wait-WebPortReady $process.Id)) {
    Write-Info "Proces wystartowal, ale port $Port nie przeszedl lokalnego testu TCP."
    Write-StartupDiagnostics
    if (Test-Path $ErrLog) {
        Write-Info "Ostatnie wpisy z logu bledu:"
        Get-Content -Path $ErrLog -Tail 40
    }
    exit 1
}

Write-Info "Panel dziala."
Write-Urls
Write-StartupDiagnostics
Write-Info "Port: $Port, host: $HostAddress"
Write-Info "Logi: $OutLog oraz $ErrLog"
Write-Info "Z drugiego PC uzyj adresu z aktywnej karty Ethernet/Wi-Fi, nie VPN."
if ($OpenBrowser) {
    Start-Process $LocalUrl
}
Show-StarterMenu
