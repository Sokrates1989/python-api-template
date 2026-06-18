<#
.SYNOPSIS
Windows entry point for dependency management – delegates to Bash via WSL.

.DESCRIPTION
This script is a thin wrapper. It performs Windows-to-WSL handoff only:
  1. Verifies WSL is available and detects a usable distro.
  2. Converts the Windows repository path to a WSL path via wslpath.
  3. Forwards all arguments unchanged to manage-python-project-dependencies.sh
     inside WSL.
  4. Propagates the Bash exit code as this script's exit code.

All runtime logic lives in manage-python-project-dependencies.sh and the
tools/core-pdm-manager submodule Bash scripts.
Do not add runtime logic here.

.PARAMETER ScriptArgs
All arguments are forwarded verbatim to manage-python-project-dependencies.sh.
#>

[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ScriptArgs
)

$ErrorActionPreference = "Stop"

#
# Helper: write a status message with a consistent prefix.
#
function Write-Status {
    param([string]$Message, [string]$Color = "Cyan")
    Write-Host "[manage-deps] $Message" -ForegroundColor $Color
}

#
# Step 1 – Verify WSL is available.
#
Write-Status "Checking WSL availability..."

$wslExe = Get-Command wsl -ErrorAction SilentlyContinue
if (-not $wslExe) {
    Write-Host ""
    Write-Host "[ERROR] WSL is not installed or not on PATH." -ForegroundColor Red
    Write-Host "  Install WSL: wsl --install" -ForegroundColor Yellow
    Write-Host "  Then enable Docker Desktop WSL integration." -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

#
# Step 2 – Detect a usable WSL distro.
#
$wslDistro = $null

if ($env:WSL_DISTRO_NAME -and $env:WSL_DISTRO_NAME.Trim() -ne "") {
    $wslDistro = $env:WSL_DISTRO_NAME.Trim()
}

if (-not $wslDistro) {
    $runningDistros = wsl --list --running --quiet 2>$null
    if ($LASTEXITCODE -eq 0 -and $runningDistros) {
        $lines = ($runningDistros | Out-String) -split "`r?`n" |
            ForEach-Object { $_.Trim() -replace '\x00', '' } |
            Where-Object { $_ -and $_ -notmatch '^\s*$' }
        if ($lines.Count -gt 0) { $wslDistro = $lines[0] }
    }
}

if (-not $wslDistro) {
    $defaultRaw = wsl --list --quiet 2>$null
    if ($LASTEXITCODE -eq 0 -and $defaultRaw) {
        $lines = ($defaultRaw | Out-String) -split "`r?`n" |
            ForEach-Object { $_.Trim() -replace '\x00', '' } |
            Where-Object { $_ -and $_ -notmatch '^\s*$' }
        if ($lines.Count -gt 0) { $wslDistro = $lines[0] }
    }
}

if (-not $wslDistro) {
    Write-Host "[ERROR] No WSL distro found. Run: wsl --install -d Ubuntu" -ForegroundColor Red
    exit 1
}

Write-Status "Using WSL distro: $wslDistro" "Gray"

#
# Step 3 – Expose the Windows repo path to WSL via WSLENV.
#
# The /p flag tells WSL to translate the value from a Windows path to a POSIX
# path (/mnt/<drive>/...), avoiding backslash mangling at the process boundary.
#
$winRepoPath = (Get-Location).Path
$env:WIN_REPO_PATH = $winRepoPath
$existingWslEnv = if ($env:WSLENV) { $env:WSLENV } else { "" }
if ($existingWslEnv -notmatch "WIN_REPO_PATH") {
    $env:WSLENV = ($existingWslEnv.TrimEnd(":") + ":WIN_REPO_PATH/p").TrimStart(":")
}

#
# Step 4 – Forward to manage-python-project-dependencies.sh inside WSL.
#
Write-Status "Launching manage-python-project-dependencies.sh in WSL..." "Cyan"
Write-Host ""

$bashArgs = $ScriptArgs | ForEach-Object {
    "'" + ($_ -replace "'", "'\\''") + "'"
}
$bashArgString = $bashArgs -join " "

$bashCmd = 'cd "$WIN_REPO_PATH" && bash manage-python-project-dependencies.sh ' + $bashArgString

wsl -d $wslDistro -- bash -c $bashCmd
exit $LASTEXITCODE
