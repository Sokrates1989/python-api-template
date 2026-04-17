<#
.SYNOPSIS
Root-level wrapper for dependency management.

.DESCRIPTION
Uses the core-pdm-manager submodule directly.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [switch]$InitialRun,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RemainingArgs
)

$coreScript = ".\tools\core-pdm-manager\scripts\pdm-manager.ps1"

if (Test-Path $coreScript) {
    if ($InitialRun.IsPresent) {
        & $coreScript -ProjectRoot . -InitialRun -NonInteractive @RemainingArgs
        exit $LASTEXITCODE
    }

    & $coreScript -ProjectRoot . @RemainingArgs
    exit $LASTEXITCODE
}

Write-Host "[ERROR] Missing dependency manager entrypoint: $coreScript" -ForegroundColor Red
Write-Host "        Ensure submodule is initialized: git submodule update --init --recursive" -ForegroundColor Yellow
exit 1
