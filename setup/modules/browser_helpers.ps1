# browser_helpers.ps1
# PowerShell module for opening browsers
# Uses a detached helper process so auto-open works while docker compose runs.

$script:IncognitoProfileCleaned = $false

function Invoke-WebRequestCompat {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,
        [int]$TimeoutSec = 5
    )

    $params = @{
        Uri         = $Url
        Method      = "Get"
        TimeoutSec  = $TimeoutSec
        ErrorAction = "Stop"
    }

    $iwr = Get-Command Invoke-WebRequest -ErrorAction SilentlyContinue
    if ($iwr -and $iwr.Parameters.ContainsKey("UseBasicParsing")) {
        $params["UseBasicParsing"] = $true
    }

    return Invoke-WebRequest @params
}

function Wait-ForUrl {
    <#
    .SYNOPSIS
    Waits for a URL to become available by polling until it returns a valid HTTP status.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,
        [int]$TimeoutSeconds = 120,
        [int]$IntervalMs = 1000
    )

    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    while ($stopwatch.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
        try {
            $response = Invoke-WebRequestCompat -Url $Url -TimeoutSec 5
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
                return $true
            }
        } catch {
            # Treat 405 as reachable (some services reject method variants during startup).
            # Treat 401 as reachable (service is up but requires auth; browser will handle login).
            try {
                $ex = $_.Exception
                if ($ex -and $ex.Response -and $ex.Response.StatusCode) {
                    $status = [int]$ex.Response.StatusCode
                    if ($status -eq 405 -or $status -eq 401) {
                        return $true
                    }
                }
            } catch {
            }
        }

        Start-Sleep -Milliseconds $IntervalMs
    }

    return $false
}

function Test-CommandExists {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Command
    )

    return [bool](Get-Command $Command -ErrorAction SilentlyContinue)
}

function Stop-IncognitoProfileProcesses {
    <#
    .SYNOPSIS
    Stops running browser processes that use a specific --user-data-dir profile.
    #>
    param(
        [string]$ProfileDir,
        [string[]]$ProcessNames
    )

    if (-not $ProfileDir -or -not $ProcessNames) {
        return
    }

    try {
        $procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
            ($ProcessNames -contains $_.Name) -and ($_.CommandLine -like "*--user-data-dir=$ProfileDir*")
        }
        foreach ($proc in $procs) {
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
        }
    } catch {
        Write-Host "[WARN] Failed to stop existing browser processes for profile $ProfileDir" -ForegroundColor Yellow
    }
}

function Open-Url {
    <#
    .SYNOPSIS
    Opens a URL in an incognito/private browser window when possible.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url
    )

    try {
        $isWin = $false
        if ($null -ne $IsWindows) {
            $isWin = $IsWindows
        } elseif ($env:OS -match "Windows") {
            $isWin = $true
        }

        if ($isWin) {
            $edgePaths = @(
                "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
                "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
            )
            foreach ($edgePath in $edgePaths) {
                if (Test-Path $edgePath) {
                    $profileDir = Join-Path $env:TEMP "edge_incog_profile_python_api_template"
                    New-Item -ItemType Directory -Path $profileDir -Force | Out-Null
                    if (-not $script:IncognitoProfileCleaned) {
                        Stop-IncognitoProfileProcesses -ProfileDir $profileDir -ProcessNames @("msedge.exe")
                        $script:IncognitoProfileCleaned = $true
                    }
                    Start-Process -FilePath $edgePath -ArgumentList "-inprivate", "--user-data-dir=$profileDir", $Url
                    return
                }
            }

            $chromePaths = @(
                "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
                "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
                "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
            )
            foreach ($chromePath in $chromePaths) {
                if (Test-Path $chromePath) {
                    $profileDir = Join-Path $env:TEMP "chrome_incog_profile_python_api_template"
                    New-Item -ItemType Directory -Path $profileDir -Force | Out-Null
                    if (-not $script:IncognitoProfileCleaned) {
                        Stop-IncognitoProfileProcesses -ProfileDir $profileDir -ProcessNames @("chrome.exe")
                        $script:IncognitoProfileCleaned = $true
                    }
                    Start-Process -FilePath $chromePath -ArgumentList "--incognito", "--user-data-dir=$profileDir", $Url
                    return
                }
            }

            $firefoxPaths = @(
                "$env:ProgramFiles\Mozilla Firefox\firefox.exe",
                "${env:ProgramFiles(x86)}\Mozilla Firefox\firefox.exe"
            )
            foreach ($firefoxPath in $firefoxPaths) {
                if (Test-Path $firefoxPath) {
                    Start-Process -FilePath $firefoxPath -ArgumentList "-private-window", $Url
                    return
                }
            }

            Start-Process $Url | Out-Null
            return
        }

        if ($IsMacOS) {
            if (Test-Path "/Applications/Google Chrome.app") {
                & open -na "Google Chrome" --args --incognito $Url 2>&1 | Out-Null
                return
            }
            if (Test-Path "/Applications/Microsoft Edge.app") {
                & open -na "Microsoft Edge" --args -inprivate $Url 2>&1 | Out-Null
                return
            }
            if (Test-Path "/Applications/Firefox.app") {
                & open -na "Firefox" --args -private-window $Url 2>&1 | Out-Null
                return
            }
            & open $Url 2>&1 | Out-Null
            return
        }

        if ($IsLinux) {
            $linuxChrome = Get-Command google-chrome -ErrorAction SilentlyContinue
            if ($linuxChrome) { & $linuxChrome.Source --incognito $Url 2>&1 | Out-Null; return }
            $linuxChromium = Get-Command chromium-browser -ErrorAction SilentlyContinue
            if ($linuxChromium) { & $linuxChromium.Source --incognito $Url 2>&1 | Out-Null; return }
            $linuxFirefox = Get-Command firefox -ErrorAction SilentlyContinue
            if ($linuxFirefox) { & $linuxFirefox.Source -private-window $Url 2>&1 | Out-Null; return }
            & xdg-open $Url 2>&1 | Out-Null
            return
        }

        Start-Process $Url | Out-Null
    } catch {
        Write-Host "[WARN] Could not open browser automatically. Please open manually: $Url" -ForegroundColor Yellow
    }
}

function Get-ConfiguredBrowserTargets {
    <#
    .SYNOPSIS
    Reads additional browser targets from the active backend browser target list.
    #>
    $targets = @()
    if ([string]::IsNullOrWhiteSpace($env:ACTIVE_BACKEND_BROWSER_TARGETS)) {
        return $targets
    }

    foreach ($line in ($env:ACTIVE_BACKEND_BROWSER_TARGETS -split "`r?`n")) {
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }

        $parts = $line -split "\|", 2
        if ($parts.Count -lt 2) {
            continue
        }

        $targets += [PSCustomObject]@{
            Label = $parts[0]
            Url = $parts[1]
        }
    }

    return $targets
}

function Open-BrowsersDelayed {
    <#
    .SYNOPSIS
    Displays service URLs and opens browser windows when services become available.
    Runs in a detached helper process so it works during long-running compose sessions.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port,
        [bool]$IncludeNeo4j = $false,
        [int]$TimeoutSeconds = 120,
        [array]$AdditionalTargets = @()
    )

    $apiUrl = "http://localhost:$Port/docs"
    $neo4jUrl = "http://localhost:7474"
    $additionalTargets = if ($AdditionalTargets.Count -gt 0) { $AdditionalTargets } else { Get-ConfiguredBrowserTargets }

    Write-Host ""
    Write-Host "========================================"
    Write-Host "  Services will be accessible at:"
    Write-Host "  * API Docs: $apiUrl"
    if ($IncludeNeo4j) {
        Write-Host "  * Neo4j Browser: $neo4jUrl"
    }
    foreach ($target in $additionalTargets) {
        Write-Host ("  * {0}: {1}" -f $target.Label, $target.Url)
    }
    Write-Host "========================================"
    Write-Host ""
    if ($additionalTargets.Count -gt 0) {
        Write-Host "Monitoring UI credentials:"
        foreach ($target in $additionalTargets) {
            if ($target.Label -eq "pgAdmin") {
                Write-Host "  * pgAdmin: $env:PGADMIN_EMAIL / $env:PGADMIN_PASSWORD"
            } elseif ($target.Label -eq "Mongo Express") {
                Write-Host "  * Mongo Express: $env:MONGO_EXPRESS_USERNAME / $env:MONGO_EXPRESS_PASSWORD"
            }
        }
        Write-Host ""
    }
    Write-Host "Browser will open automatically when services are ready..."
    Write-Host ""

    $scriptPath = $PSScriptRoot
    if (-not $scriptPath) {
        $scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Definition
    }
    $browserHelpersFile = Join-Path $scriptPath "browser_helpers.ps1"

    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $tempScript = Join-Path $env:TEMP "python_api_template_browser_open_$([guid]::NewGuid().ToString('N').Substring(0,8)).ps1"
    $logFile = Join-Path $env:TEMP "python_api_template_browser_open_$timestamp.log"

    $scriptContent = @"
`$ErrorActionPreference = 'Continue'
. '$browserHelpersFile'

`$logFile = '$logFile'
try { Add-Content -Path `$logFile -Value ("[{0}] Browser helper started. API={1} Neo4j={2}" -f (Get-Date), '$apiUrl', '$IncludeNeo4j') -Encoding UTF8 } catch {}

try {
    `$apiReady = Wait-ForUrl -Url '$apiUrl' -TimeoutSeconds $TimeoutSeconds -IntervalMs 1000
    Add-Content -Path `$logFile -Value ("[{0}] API ready={1}" -f (Get-Date), `$apiReady) -Encoding UTF8
    if (`$apiReady) { Open-Url '$apiUrl' }
} catch {
    try { Add-Content -Path `$logFile -Value ("[{0}] ERROR waiting/opening API: {1}" -f (Get-Date), `$_.Exception.Message) -Encoding UTF8 } catch {}
}

`$includeNeo4j = '$IncludeNeo4j'
if (`$includeNeo4j -match '^(?i:true)$') {
    try {
        `$neo4jReady = Wait-ForUrl -Url '$neo4jUrl' -TimeoutSeconds $TimeoutSeconds -IntervalMs 1000
        Add-Content -Path `$logFile -Value ("[{0}] Neo4j ready={1}" -f (Get-Date), `$neo4jReady) -Encoding UTF8
        if (`$neo4jReady) { Open-Url '$neo4jUrl' }
    } catch {
        try { Add-Content -Path `$logFile -Value ("[{0}] ERROR waiting/opening Neo4j: {1}" -f (Get-Date), `$_.Exception.Message) -Encoding UTF8 } catch {}
    }
}

try { Add-Content -Path `$logFile -Value ("[{0}] DEBUG: Processing additional targets..." -f (Get-Date)) -Encoding UTF8 } catch {}
`$targetsJsonBase64 = '$([Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes(($additionalTargets | ConvertTo-Json -Compress -ErrorAction SilentlyContinue))))'
try { Add-Content -Path `$logFile -Value ("[{0}] DEBUG: Base64 length={1}" -f (Get-Date), `$targetsJsonBase64.Length) -Encoding UTF8 } catch {}
`$targetsJson = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String(`$targetsJsonBase64))
try { Add-Content -Path `$logFile -Value ("[{0}] DEBUG: Decoded JSON={1}" -f (Get-Date), `$targetsJson) -Encoding UTF8 } catch {}
if ([string]::IsNullOrWhiteSpace(`$targetsJson) -or `$targetsJson -eq 'null') { `$targetsJson = '[]' }
`$parsedTargets = `$targetsJson | ConvertFrom-Json
# Ensure we always have an array to iterate over (handles single object vs array)
if (`$parsedTargets -isnot [array]) { `$parsedTargets = @(`$parsedTargets) }
if (-not `$parsedTargets) { `$parsedTargets = @() }
try { Add-Content -Path `$logFile -Value ("[{0}] DEBUG: Target count={1}" -f (Get-Date), `$parsedTargets.Count) -Encoding UTF8 } catch {}
foreach (`$target in `$parsedTargets) {
    try {
        try { Add-Content -Path `$logFile -Value ("[{0}] DEBUG: Checking {1} at {2}" -f (Get-Date), `$target.Label, `$target.Url) -Encoding UTF8 } catch {}
        `$targetReady = Wait-ForUrl -Url `$target.Url -TimeoutSeconds $TimeoutSeconds -IntervalMs 1000
        Add-Content -Path `$logFile -Value ("[{0}] {1} ready={2}" -f (Get-Date), `$target.Label, `$targetReady) -Encoding UTF8
        if (`$targetReady) { Open-Url `$target.Url }
    } catch {
        try { Add-Content -Path `$logFile -Value ("[{0}] ERROR waiting/opening {1}: {2}" -f (Get-Date), `$target.Label, `$_.Exception.Message) -Encoding UTF8 } catch {}
    }
}

Remove-Item -Path '$tempScript' -Force -ErrorAction SilentlyContinue
"@

    Set-Content -Path $tempScript -Value $scriptContent -Encoding UTF8

    $psExe = $null
    try {
        $psExe = (Get-Command powershell -ErrorAction SilentlyContinue).Source
        if (-not $psExe) {
            $psExe = (Get-Command pwsh -ErrorAction SilentlyContinue).Source
        }
    } catch {
        $psExe = $null
    }
    if (-not $psExe) {
        $psExe = "powershell"
    }

    Write-Host "[WEB] Browser helper log: $logFile" -ForegroundColor Gray
    Write-Host "[WEB] Browser helper started in background" -ForegroundColor Gray

    Start-Process -FilePath $psExe -ArgumentList @(
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-WindowStyle",
        "Hidden",
        "-File",
        $tempScript
    ) -WindowStyle Hidden
}
