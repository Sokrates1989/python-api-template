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
        if ($?) {
            exit 0
        }
        if ($null -ne $LASTEXITCODE) {
            exit $LASTEXITCODE
        }
        exit 1
    }

    & $coreScript -ProjectRoot . @RemainingArgs
    if ($?) {
        exit 0
    }
    if ($null -ne $LASTEXITCODE) {
        exit $LASTEXITCODE
    }
    exit 1
}

Write-Host "[ERROR] Missing dependency manager entrypoint: $coreScript" -ForegroundColor Red
Write-Host "        Ensure submodule is initialized: git submodule update --init --recursive" -ForegroundColor Yellow
exit 1
