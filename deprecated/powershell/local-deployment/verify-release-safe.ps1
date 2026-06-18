param(
    [switch]$Strict
)

$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

$checks = @()

function Add-CheckResult {
    param(
        [string]$Name,
        [bool]$Passed,
        [string]$Details
    )
    $script:checks += [PSCustomObject]@{
        Check = $Name
        Passed = $Passed
        Details = $Details
    }
}

function Assert-FileExists {
    param(
        [string]$Path,
        [string]$Label
    )

    if (Test-Path $Path) {
        Add-CheckResult -Name $Label -Passed $true -Details $Path
    } else {
        Add-CheckResult -Name $Label -Passed $false -Details "Missing: $Path"
    }
}

Write-Host "Running safe release verification checks..." -ForegroundColor Cyan

# Required roadmap and operations docs.
Assert-FileExists -Path "docs/IMPROVEMENT_PLAN_PROGRESS.md" -Label "Roadmap progress document"
Assert-FileExists -Path "docs/STARTUP_PROBES.md" -Label "Startup probes document"
Assert-FileExists -Path "docs/RELEASE_CHECKLIST.md" -Label "Release checklist document"

# Required drill scripts.
Assert-FileExists -Path "local-deployment/run-phase5-drill.ps1" -Label "Phase 5 drill script"
Assert-FileExists -Path "local-deployment/verify-release-safe.ps1" -Label "Safe verification script"
Assert-FileExists -Path "local-deployment/run-release-gate.ps1" -Label "Release gate script"

# Required profile files.
Assert-FileExists -Path ".env.drill.postgres" -Label "Drill env (Postgres)"
Assert-FileExists -Path ".env.drill.neo4j" -Label "Drill env (Neo4j)"
Assert-FileExists -Path ".env.drill.mongodb" -Label "Drill env (MongoDB)"

# Python syntax sanity for key runtime modules.
try {
    python -m compileall `
        app/main.py `
        app/api/config/lifecycle.py `
        app/backend/database/init_db.py `
        app/backend/database/startup_probe.py `
        app/backend/observability.py `
        qa_pytest/unit/test_startup_probe.py | Out-Null
    Add-CheckResult -Name "Python syntax compile check" -Passed $true -Details "compileall passed"
} catch {
    Add-CheckResult -Name "Python syntax compile check" -Passed $false -Details $_.Exception.Message
}

$failed = @($checks | Where-Object { -not $_.Passed })

Write-Host ""
Write-Host "Safe verification results:" -ForegroundColor Green
$checks | Format-Table -AutoSize

if ($failed.Count -gt 0) {
    Write-Host ""
    Write-Host "Some checks failed." -ForegroundColor Yellow
    if ($Strict) {
        throw "Safe release verification failed in strict mode."
    }
} else {
    Write-Host ""
    Write-Host "All safe checks passed." -ForegroundColor Green
}

Write-Host ""
Write-Host "Next manual steps (requires Docker/runtime):" -ForegroundColor Cyan
Write-Host "  1) .\\local-deployment\\run-phase5-drill.ps1 -Profile all"
Write-Host "  2) Execute full pytest matrix in CI/local containers"
