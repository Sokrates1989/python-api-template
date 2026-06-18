<#
.SYNOPSIS
Root-level wrapper for Docker/build diagnostics.

.DESCRIPTION
Uses the core-pdm-manager submodule diagnostics script directly.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [switch]$SkipBuild,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RemainingArgs
)

$coreScript = ".\tools\core-pdm-manager\scripts\diagnostics.ps1"

if (Test-Path $coreScript) {
    & $coreScript -ProjectRoot . -SkipBuild:$SkipBuild @RemainingArgs
    if ($?) {
        exit 0
    }
    if ($null -ne $LASTEXITCODE) {
        exit $LASTEXITCODE
    }
    exit 1
}

Write-Host "[ERROR] Missing diagnostics entrypoint: $coreScript" -ForegroundColor Red
Write-Host "        To fix: git submodule update --init --recursive" -ForegroundColor Yellow
exit 1
