<#
.SYNOPSIS
Windows entry point for quick-start – delegates all runtime logic to Bash via WSL.

.DESCRIPTION
This script is a thin wrapper. It performs Windows-to-WSL handoff only:
  1. Verifies WSL is available and detects a usable distro.
  2. Passes the Windows repo path via WSLENV /p so WSL translates it
     automatically to /mnt/<drive>/... without wslpath backslash issues.
  3. Verifies Docker is accessible inside the detected WSL distro.
  4. Forwards all arguments unchanged to quick-start.sh inside WSL.
  5. Propagates the Bash exit code as this script's exit code.

All runtime logic lives in quick-start.sh and the setup/modules/*.sh modules.
Do not add runtime logic here.

.PARAMETER Args
All arguments are forwarded verbatim to quick-start.sh.
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
    Write-Host "[quick-start] $Message" -ForegroundColor $Color
}

#
# Step 1 – Verify WSL is available.
#
Write-Status "Checking WSL availability..."

$wslExe = Get-Command wsl -ErrorAction SilentlyContinue
if (-not $wslExe) {
    Write-Host ""
    Write-Host "[ERROR] WSL (Windows Subsystem for Linux) is not installed or not on PATH." -ForegroundColor Red
    Write-Host ""
    Write-Host "Setup instructions:" -ForegroundColor Yellow
    Write-Host "  1. Open PowerShell as Administrator and run:  wsl --install" -ForegroundColor Gray
    Write-Host "  2. Restart your machine when prompted." -ForegroundColor Gray
    Write-Host "  3. Launch a WSL distro at least once to finish setup." -ForegroundColor Gray
    Write-Host "  4. Enable Docker Desktop WSL integration for your distro:" -ForegroundColor Gray
    Write-Host "     Docker Desktop -> Settings -> Resources -> WSL Integration" -ForegroundColor Gray
    Write-Host ""
    exit 1
}

#
# Step 2 – Detect a running WSL distro.
#
Write-Status "Detecting WSL distro..."

$wslDistro = $null

# Prefer the value from WSL_DISTRO_NAME set in the environment (honoured when
# the user has already entered a WSL session and launched PowerShell from it).
if ($env:WSL_DISTRO_NAME -and $env:WSL_DISTRO_NAME.Trim() -ne "") {
    $wslDistro = $env:WSL_DISTRO_NAME.Trim()
    Write-Status "Using distro from WSL_DISTRO_NAME env var: $wslDistro" "Gray"
}

if (-not $wslDistro) {
    # List running distributions and pick the first one.
    $runningDistros = wsl --list --running --quiet 2>$null
    if ($LASTEXITCODE -eq 0 -and $runningDistros) {
        $lines = ($runningDistros | Out-String) -split "`r?`n" |
            ForEach-Object { $_.Trim() -replace '\x00', '' } |
            Where-Object { $_ -and $_ -notmatch '^\s*$' }
        if ($lines.Count -gt 0) {
            $wslDistro = $lines[0]
            Write-Status "Using running distro: $wslDistro" "Gray"
        }
    }
}

if (-not $wslDistro) {
    # Fall back to the default distro.
    $defaultDistroRaw = wsl --list --quiet 2>$null
    if ($LASTEXITCODE -eq 0 -and $defaultDistroRaw) {
        $lines = ($defaultDistroRaw | Out-String) -split "`r?`n" |
            ForEach-Object { $_.Trim() -replace '\x00', '' } |
            Where-Object { $_ -and $_ -notmatch '^\s*$' }
        if ($lines.Count -gt 0) {
            $wslDistro = $lines[0]
            Write-Status "Using default distro: $wslDistro" "Gray"
        }
    }
}

if (-not $wslDistro) {
    Write-Host ""
    Write-Host "[ERROR] No WSL distro found." -ForegroundColor Red
    Write-Host ""
    Write-Host "Setup instructions:" -ForegroundColor Yellow
    Write-Host "  1. Install a WSL distro:  wsl --install -d Ubuntu" -ForegroundColor Gray
    Write-Host "  2. Launch it once to complete setup." -ForegroundColor Gray
    Write-Host "  3. Enable Docker Desktop WSL integration:" -ForegroundColor Gray
    Write-Host "     Docker Desktop -> Settings -> Resources -> WSL Integration" -ForegroundColor Gray
    Write-Host ""
    exit 1
}

#
# Step 3 – Expose the Windows repo path to WSL via WSLENV.
#
# The /p flag tells WSL to translate the value from a Windows path to
# a POSIX path (/mnt/<drive>/...).  This avoids backslash mangling that
# occurs when passing a Windows path as a CLI argument through the WSL
# process boundary.
#
Write-Status "Setting up WSL path translation via WSLENV..." "Gray"

$winRepoPath = (Get-Location).Path
$env:WIN_REPO_PATH = $winRepoPath

# Append WIN_REPO_PATH/p to WSLENV, preserving any existing value.
$existingWslEnv = if ($env:WSLENV) { $env:WSLENV } else { "" }
if ($existingWslEnv -notmatch "WIN_REPO_PATH") {
    $env:WSLENV = ($existingWslEnv.TrimEnd(":") + ":WIN_REPO_PATH/p").TrimStart(":")
}

Write-Status "Windows repo path: $winRepoPath" "Gray"

#
# Step 4 – Verify Docker is accessible inside WSL.
#
Write-Status "Checking Docker inside WSL ($wslDistro)..."

$dockerCheck = wsl -d $wslDistro -- bash -c 'docker info > /dev/null 2>&1 && echo ok || echo fail' 2>$null
if ($dockerCheck -notmatch "ok") {
    Write-Host ""
    Write-Host "[ERROR] Docker is not accessible inside WSL distro '$wslDistro'." -ForegroundColor Red
    Write-Host ""
    Write-Host "Setup instructions:" -ForegroundColor Yellow
    Write-Host "  1. Ensure Docker Desktop is running." -ForegroundColor Gray
    Write-Host "  2. Enable WSL integration in Docker Desktop:" -ForegroundColor Gray
    Write-Host "     Docker Desktop -> Settings -> Resources -> WSL Integration" -ForegroundColor Gray
    Write-Host "  3. Check the box for '$wslDistro' and click Apply & Restart." -ForegroundColor Gray
    Write-Host "  4. Re-run this script." -ForegroundColor Gray
    Write-Host ""
    exit 1
}

Write-Status "Docker OK inside $wslDistro." "Green"

#
# Step 5 – Forward to quick-start.sh inside WSL.
#
# WIN_REPO_PATH is translated to a POSIX path by WSLENV /p and is available
# as $WIN_REPO_PATH inside the WSL bash session.
#
Write-Status "Launching quick-start.sh in WSL ($wslDistro)..."
Write-Host ""

# Build the argument list for the Bash script.
# Each argument is single-quoted and inner single-quotes are escaped for Bash.
$bashArgs = $ScriptArgs | ForEach-Object {
    "'" + ($_ -replace "'", "'\\''") + "'"
}
$bashArgString = $bashArgs -join " "

$bashCmd = 'cd "$WIN_REPO_PATH" && bash quick-start.sh ' + $bashArgString

wsl -d $wslDistro -- bash -c $bashCmd
$wslExitCode = $LASTEXITCODE

exit $wslExitCode
