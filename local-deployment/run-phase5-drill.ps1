param(
    [ValidateSet("all", "postgres", "neo4j", "mongodb")]
    [string]$Profile = "all",
    [int]$TimeoutSeconds = 300,
    [switch]$NoBuild,
    [switch]$KeepLastProfileRunning
)

$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

function Get-EnvValue {
    param(
        [string]$EnvFile,
        [string]$Key
    )

    foreach ($line in Get-Content $EnvFile) {
        if ([string]::IsNullOrWhiteSpace($line) -or $line.TrimStart().StartsWith("#")) {
            continue
        }

        $parts = $line -split "=", 2
        if ($parts.Count -ne 2) {
            continue
        }

        if ($parts[0].Trim() -eq $Key) {
            return $parts[1].Trim()
        }
    }

    return $null
}

function Wait-ForApi {
    param(
        [string]$Url,
        [int]$TimeoutSeconds,
        [string]$ExpectedProfile
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lastObservedProfile = "<none>"
    $lastProgressSecond = -1
    $lastError = "<none>"

    while ((Get-Date) -lt $deadline) {
        $remaining = [int][Math]::Max(0, ($deadline - (Get-Date)).TotalSeconds)
        if (($remaining % 10 -eq 0) -and ($remaining -ne $lastProgressSecond)) {
            Write-Host "  waiting for API/profile readiness... remaining ${remaining}s (last profile: $lastObservedProfile, last error: $lastError)" -ForegroundColor DarkGray
            $lastProgressSecond = $remaining
        }
        try {
            $invokeParams = @{
                Uri = $Url
                TimeoutSec = 3
            }
            if ((Get-Command Invoke-WebRequest).Parameters.ContainsKey("UseBasicParsing")) {
                $invokeParams["UseBasicParsing"] = $true
            }

            $response = Invoke-WebRequest @invokeParams
            if ($response.StatusCode -ne 200) {
                Start-Sleep -Seconds 2
                continue
            }

            $healthParams = @{
                Uri = $Url
                Method = "Get"
                TimeoutSec = 3
            }
            if ((Get-Command Invoke-RestMethod).Parameters.ContainsKey("UseBasicParsing")) {
                $healthParams["UseBasicParsing"] = $true
            }
            $health = Invoke-RestMethod @healthParams

            if (-not $ExpectedProfile) {
                return
            }

            $observedProfile = if ($null -ne $health.provider_profile) {
                [string]$health.provider_profile
            } else {
                "<missing>"
            }
            $lastObservedProfile = $observedProfile
            if ($observedProfile -eq $ExpectedProfile) {
                return
            }
        } catch {
            $lastError = $_.Exception.Message
        }
        Start-Sleep -Seconds 2
    }

    throw (
        "API not ready with expected provider profile at $Url within $TimeoutSeconds seconds. " +
        "Expected '$ExpectedProfile', last observed '$lastObservedProfile', last error '$lastError'."
    )
}

function Invoke-DockerCompose {
    param(
        [string]$ProjectName,
        [string]$EnvFile,
        [string]$ComposeFile,
        [string[]]$ComposeArgs
    )

    & docker compose -p $ProjectName --env-file $EnvFile -f $ComposeFile @ComposeArgs
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        $argsJoined = ($ComposeArgs -join " ")
        throw "docker compose failed (exit $exitCode): project=$ProjectName env=$EnvFile compose=$ComposeFile args=$argsJoined"
    }
}

function Assert-AppRunning {
    param(
        [string]$ProjectName,
        [string]$EnvFile,
        [string]$ComposeFile,
        [int]$TimeoutSeconds = 60
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $runningServicesRaw = & docker compose -p $ProjectName --env-file $EnvFile -f $ComposeFile ps --status running --services
        $exitCode = $LASTEXITCODE
        if ($exitCode -ne 0) {
            throw "docker compose ps failed for project=$ProjectName (exit $exitCode)"
        }

        $runningServices = @()
        if ($null -ne $runningServicesRaw) {
            $runningServices = @(
                (($runningServicesRaw | Out-String) -split "`r?`n") |
                    ForEach-Object { $_.Trim() } |
                    Where-Object { $_ }
            )
        }

        if ($runningServices -contains "app") {
            return
        }

        Start-Sleep -Seconds 2
    }

    Write-Host "  app service is not running, showing compose status and logs..." -ForegroundColor Yellow
    & docker compose -p $ProjectName --env-file $EnvFile -f $ComposeFile ps
    & docker compose -p $ProjectName --env-file $EnvFile -f $ComposeFile logs --tail 150
    throw "App service is not running for project '$ProjectName'."
}

$profiles = @(
    @{
        Name = "postgres"
        EnvFile = ".env.drill.postgres"
        ComposeFile = "local-deployment/docker-compose.postgres.yml"
        ExpectedProfile = "sql"
    },
    @{
        Name = "neo4j"
        EnvFile = ".env.drill.neo4j"
        ComposeFile = "local-deployment/docker-compose.neo4j.yml"
        ExpectedProfile = "neo4j"
    },
    @{
        Name = "mongodb"
        EnvFile = ".env.drill.mongodb"
        ComposeFile = "local-deployment/docker-compose.mongodb.yml"
        ExpectedProfile = "mongodb"
    }
)

$selectedProfiles = @(
    if ($Profile -eq "all") {
        $profiles
    } else {
        $profiles | Where-Object { $_.Name -eq $Profile }
    }
)

if (-not $selectedProfiles) {
    throw "No profile selected for '$Profile'."
}

$results = @()

for ($i = 0; $i -lt $selectedProfiles.Count; $i++) {
    $cfg = $selectedProfiles[$i]
    $isLast = $i -eq ($selectedProfiles.Count - 1)
    $projectName = "python-api-template-drill-$($cfg.Name)"

    Write-Host "`n=== Phase 5 Drill: $($cfg.Name) ===" -ForegroundColor Cyan

    try {
        Write-Host "  tearing down old containers..." -ForegroundColor DarkGray
        Invoke-DockerCompose -ProjectName $projectName -EnvFile $cfg.EnvFile -ComposeFile $cfg.ComposeFile -ComposeArgs @("down", "--remove-orphans") | Out-Null

        $upArgs = @("up", "-d")
        if (-not $NoBuild) {
            $upArgs += "--build"
        }
        try {
            if ($NoBuild) {
                Write-Host "  starting services (no build)..." -ForegroundColor DarkGray
            } else {
                Write-Host "  starting services (with build)..." -ForegroundColor DarkGray
            }
            Invoke-DockerCompose -ProjectName $projectName -EnvFile $cfg.EnvFile -ComposeFile $cfg.ComposeFile -ComposeArgs $upArgs | Out-Null
        } catch {
            if ($NoBuild) {
                Write-Host "  no-build startup failed, retrying with build..." -ForegroundColor Yellow
                Invoke-DockerCompose -ProjectName $projectName -EnvFile $cfg.EnvFile -ComposeFile $cfg.ComposeFile -ComposeArgs @("up", "-d", "--build") | Out-Null
            } else {
                throw
            }
        }

        Assert-AppRunning -ProjectName $projectName -EnvFile $cfg.EnvFile -ComposeFile $cfg.ComposeFile -TimeoutSeconds 90

        Wait-ForApi -Url "http://localhost:8081/health" -TimeoutSeconds $TimeoutSeconds -ExpectedProfile $cfg.ExpectedProfile
        Write-Host "  API ready with expected profile '$($cfg.ExpectedProfile)'" -ForegroundColor DarkGray

        $adminKey = Get-EnvValue -EnvFile $cfg.EnvFile -Key "ADMIN_API_KEY"
        if (-not $adminKey) {
            throw "ADMIN_API_KEY not found in $($cfg.EnvFile)."
        }

        $headers = @{ "X-Admin-Key" = $adminKey }
        $provider = Invoke-RestMethod -Uri "http://localhost:8081/database/provider-info" -Headers $headers -Method Get
        if ($provider.provider_profile -ne $cfg.ExpectedProfile) {
            throw "Provider mismatch for $($cfg.Name): expected '$($cfg.ExpectedProfile)', got '$($provider.provider_profile)'."
        }
        Write-Host "  provider-info check passed" -ForegroundColor DarkGray

        $lockBody = @{ operation = "phase5_drill" } | ConvertTo-Json -Compress
        $lock = Invoke-RestMethod -Uri "http://localhost:8081/database/lock" -Headers $headers -Method Post -ContentType "application/json" -Body $lockBody
        if (-not $lock.success -or -not $lock.is_locked) {
            throw "Lock check failed for $($cfg.Name)."
        }
        Write-Host "  lock check passed" -ForegroundColor DarkGray

        $unlock = Invoke-RestMethod -Uri "http://localhost:8081/database/unlock" -Headers $headers -Method Post
        if (-not $unlock.success -or $unlock.is_locked) {
            throw "Unlock check failed for $($cfg.Name)."
        }
        Write-Host "  unlock check passed" -ForegroundColor DarkGray

        $results += [PSCustomObject]@{
            profile = $cfg.Name
            provider_profile = $provider.provider_profile
            database_type = $provider.database_type
            health = "ok"
            lock = "ok"
            unlock = "ok"
        }
    } finally {
        if (-not ($KeepLastProfileRunning -and $isLast)) {
            Write-Host "  stopping profile '$($cfg.Name)'" -ForegroundColor DarkGray
            Invoke-DockerCompose -ProjectName $projectName -EnvFile $cfg.EnvFile -ComposeFile $cfg.ComposeFile -ComposeArgs @("down", "--remove-orphans") | Out-Null
        }
    }
}

Write-Host "`nPhase 5 drill results:" -ForegroundColor Green
$results | Format-Table -AutoSize
