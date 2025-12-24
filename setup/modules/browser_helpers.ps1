<#
.SYNOPSIS
    Browser helper functions for quick-start script.
    Provides URL polling and automatic browser opening when services are ready.
#>

<#
.SYNOPSIS
    Polls a URL until it returns a 2xx or 3xx HTTP status code.

.PARAMETER Url
    The URL to check.

.PARAMETER TimeoutSeconds
    Maximum time to wait in seconds (default: 120).

.RETURNS
    $true if URL became available, $false if timeout reached.
#>
function Wait-ForUrl {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,
        
        [Parameter(Mandatory = $false)]
        [int]$TimeoutSeconds = 120
    )
    
    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    
    while ($stopwatch.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
        try {
            $response = Invoke-WebRequest -Uri $Url -Method Head -TimeoutSec 5 -UseBasicParsing -ErrorAction SilentlyContinue
            $statusCode = [int]$response.StatusCode
            
            if ($statusCode -ge 200 -and $statusCode -lt 400) {
                $stopwatch.Stop()
                return $true
            }
        }
        catch {
            # Connection failed, continue polling
        }
        
        Start-Sleep -Seconds 2
    }
    
    $stopwatch.Stop()
    return $false
}

<#
.SYNOPSIS
    Opens a URL in the default browser, preferring incognito/private mode.

.PARAMETER Url
    The URL to open.
#>
function Open-Url {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url
    )
    
    # Try Chrome incognito first
    $chromePaths = @(
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "$env:ProgramFiles(x86)\Google\Chrome\Application\chrome.exe",
        "$env:LocalAppData\Google\Chrome\Application\chrome.exe"
    )
    
    foreach ($chromePath in $chromePaths) {
        if (Test-Path $chromePath) {
            Start-Process -FilePath $chromePath -ArgumentList "--incognito", $Url -ErrorAction SilentlyContinue
            return
        }
    }
    
    # Try Edge InPrivate
    $edgePaths = @(
        "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
        "$env:ProgramFiles(x86)\Microsoft\Edge\Application\msedge.exe"
    )
    
    foreach ($edgePath in $edgePaths) {
        if (Test-Path $edgePath) {
            Start-Process -FilePath $edgePath -ArgumentList "-inprivate", $Url -ErrorAction SilentlyContinue
            return
        }
    }
    
    # Fallback to default browser
    Start-Process $Url -ErrorAction SilentlyContinue
}

<#
.SYNOPSIS
    Displays service URLs and opens browsers automatically when services become available.
    Runs the polling and browser opening in a background job so docker compose can proceed.

.PARAMETER Port
    The port the API is running on.

.PARAMETER IncludeNeo4j
    Whether to also open Neo4j browser.

.PARAMETER TimeoutSeconds
    Maximum seconds to wait for services (default: 120).
#>
function Open-BrowsersDelayed {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port,
        
        [Parameter(Mandatory = $false)]
        [bool]$IncludeNeo4j = $false,
        
        [Parameter(Mandatory = $false)]
        [int]$TimeoutSeconds = 120
    )
    
    $apiUrl = "http://localhost:$Port/docs"
    $neo4jUrl = "http://localhost:7474"
    
    Write-Host ""
    Write-Host "========================================"
    Write-Host "  Services will be accessible at:"
    Write-Host "  * API Docs: $apiUrl"
    if ($IncludeNeo4j) {
        Write-Host "  * Neo4j Browser: $neo4jUrl"
    }
    Write-Host "========================================"
    Write-Host ""
    Write-Host "Browser will open automatically when services are ready..."
    Write-Host ""
    
    # Start background job to poll and open browsers
    $scriptBlock = {
        param($apiUrl, $neo4jUrl, $includeNeo4j, $timeout)
        
        # Wait-ForUrl inline function for background job
        function Wait-ForUrlInJob {
            param([string]$Url, [int]$TimeoutSeconds)
            
            $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
            
            while ($stopwatch.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
                try {
                    $response = Invoke-WebRequest -Uri $Url -Method Head -TimeoutSec 5 -UseBasicParsing -ErrorAction SilentlyContinue
                    $statusCode = [int]$response.StatusCode
                    
                    if ($statusCode -ge 200 -and $statusCode -lt 400) {
                        $stopwatch.Stop()
                        return $true
                    }
                }
                catch {
                    # Connection failed, continue polling
                }
                
                Start-Sleep -Seconds 2
            }
            
            $stopwatch.Stop()
            return $false
        }
        
        # Open-Url inline function for background job
        function Open-UrlInJob {
            param([string]$Url)
            
            $chromePaths = @(
                "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
                "$env:ProgramFiles(x86)\Google\Chrome\Application\chrome.exe",
                "$env:LocalAppData\Google\Chrome\Application\chrome.exe"
            )
            
            foreach ($chromePath in $chromePaths) {
                if (Test-Path $chromePath) {
                    Start-Process -FilePath $chromePath -ArgumentList "--incognito", $Url -ErrorAction SilentlyContinue
                    return
                }
            }
            
            $edgePaths = @(
                "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
                "$env:ProgramFiles(x86)\Microsoft\Edge\Application\msedge.exe"
            )
            
            foreach ($edgePath in $edgePaths) {
                if (Test-Path $edgePath) {
                    Start-Process -FilePath $edgePath -ArgumentList "-inprivate", $Url -ErrorAction SilentlyContinue
                    return
                }
            }
            
            Start-Process $Url -ErrorAction SilentlyContinue
        }
        
        # Wait for API
        if (Wait-ForUrlInJob -Url $apiUrl -TimeoutSeconds $timeout) {
            Open-UrlInJob -Url $apiUrl
        }
        
        # Wait for Neo4j if requested
        if ($includeNeo4j) {
            if (Wait-ForUrlInJob -Url $neo4jUrl -TimeoutSeconds $timeout) {
                Open-UrlInJob -Url $neo4jUrl
            }
        }
    }
    
    Start-Job -ScriptBlock $scriptBlock -ArgumentList $apiUrl, $neo4jUrl, $IncludeNeo4j, $TimeoutSeconds | Out-Null
}
