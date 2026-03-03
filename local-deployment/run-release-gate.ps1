param(
    [switch]$SkipSafeChecks,
    [switch]$SkipDrill,
    [switch]$NoBuild,
    [int]$DrillTimeoutSeconds = 300
)

$ErrorActionPreference = "Stop"

$root = Join-Path $PSScriptRoot ".."
Set-Location $root

Write-Host "Release gate started..." -ForegroundColor Cyan

if (-not $SkipSafeChecks) {
    Write-Host ""
    Write-Host "[Stage 1/2] Running safe verification checks" -ForegroundColor Cyan
    & ".\local-deployment\verify-release-safe.ps1" -Strict
    if ($LASTEXITCODE -ne 0) {
        throw "Safe verification checks failed."
    }
} else {
    Write-Host ""
    Write-Host "[Stage 1/2] Skipped safe verification checks" -ForegroundColor Yellow
}

if (-not $SkipDrill) {
    Write-Host ""
    Write-Host "[Stage 2/2] Running provider drill matrix" -ForegroundColor Cyan

    $drillParams = @{
        Profile = "all"
        TimeoutSeconds = $DrillTimeoutSeconds
    }
    if ($NoBuild) {
        $drillParams["NoBuild"] = $true
    }

    & ".\local-deployment\run-phase5-drill.ps1" @drillParams
    if ($LASTEXITCODE -ne 0) {
        throw "Provider drill matrix failed."
    }
} else {
    Write-Host ""
    Write-Host "[Stage 2/2] Skipped provider drill matrix" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Release gate completed successfully." -ForegroundColor Green
Write-Host "Recommended next step: run CI matrix or merge if CI is already green." -ForegroundColor Green
