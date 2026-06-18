#!/bin/bash
#
# browser_helpers.sh
#
# Module for browser-related helper functions in quick-start script.
# Provides URL polling and automatic browser opening when services are ready.

# wait_for_url
# Polls a URL until it returns a reachable HTTP status code.
#
# Treats 2xx and 3xx as successful. Also treats 401 and 405 as reachable
# because FastAPI can return 405 on some startup states and services that
# require auth return 401 immediately once the process is listening.
# Both mean the server is up. Mirrors the legacy PowerShell Wait-ForUrl
# behaviour that accepted these codes as reachable.
#
# Args:
#   url: The URL to check
#   timeout_seconds: Maximum time to wait (default: 120)
#   log_file: Optional path to append per-attempt probe lines to
#   (polls every 2 seconds)
#
# Returns:
#   0 if URL became available, 1 if timeout reached
wait_for_url() {
    local url="$1"
    local timeout="${2:-120}"
    local log_file="${3:-}"
    local start_time
    start_time=$(date +%s)

    while true; do
        local current_time elapsed
        current_time=$(date +%s)
        elapsed=$((current_time - start_time))

        if [ "$elapsed" -ge "$timeout" ]; then
            [ -n "$log_file" ] && printf '[%s] TIMEOUT url=%s elapsed=%ss\n' \
                "$(date '+%Y-%m-%d %H:%M:%S')" "$url" "$elapsed" >> "$log_file" 2>/dev/null
            return 1
        fi

        local status
        status=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 --max-time 5 "$url" 2>/dev/null)
        status="${status:-000}"

        case "$status" in
            2*|3*)   return 0 ;;
            401|405) return 0 ;;
        esac

        [ -n "$log_file" ] && printf '[%s] PROBE url=%s status=%s elapsed=%ss\n' \
            "$(date '+%Y-%m-%d %H:%M:%S')" "$url" "$status" "$elapsed" >> "$log_file" 2>/dev/null
        sleep 2
    done
}

#
# Detects whether this Bash process runs inside WSL.
#
# Args:
#   None.
#
# Returns:
#   0 when running inside WSL, 1 otherwise.
#
is_wsl_environment() {
    if [ -f /proc/version ] && grep -qiE 'microsoft|wsl' /proc/version 2>/dev/null; then
        return 0
    fi
    return 1
}

#
# Opens a Windows browser from WSL in private/incognito mode with a dedicated
# user-data-dir profile so sessions are fully isolated from the user's normal
# browser profile.
#
# Mirrors the figma-website open_windows_private_browser implementation:
# writes a standalone PS1 launcher to a temp file, converts paths with wslpath,
# and invokes it with -File so argument quoting is unambiguous. The PS1 covers
# Edge → Chrome → Firefox → default URL handler as a fallback chain.
#
# When new_tab=true the PS1 receives -NewTab, which skips Stop-ProfileProcesses
# and passes --new-tab / -new-tab to the browser so the URL opens as a tab in
# the already-running window rather than killing it first.
#
# Launcher logs are written to ~/.browser-helper-logs/ and the path is printed
# to stderr so it is visible in the terminal output.
#
# Args:
#   $1: Fully qualified URL.
#   $2: new_tab — "true" to open as a tab in the existing window (default: false).
#
# Returns:
#   0 when the Windows launch command was started, 1 when PowerShell or wslpath
#   is unavailable.
#
open_windows_private_browser() {
    local url="$1"
    local new_tab="${2:-false}"
    local profile_slug="python_api_template"
    local log_dir="${HOME}/.browser-helper-logs"
    mkdir -p "$log_dir"
    local log_file
    log_file="${log_dir}/browser_open_$(date +%Y%m%d_%H%M%S)_$$.log"

    if ! command -v powershell.exe >/dev/null 2>&1; then
        return 1
    fi

    if ! command -v wslpath >/dev/null 2>&1; then
        return 1
    fi

    local log_file_abs
    log_file_abs="$(cd "$(dirname "$log_file")" && pwd)/$(basename "$log_file")"
    local launcher_script="${log_file_abs%.log}_open_$$.ps1"

    # Embedded PowerShell launcher — written to disk so argument quoting is
    # handled by -File rather than fragile -Command escaping.
    #
    # When -NewTab is $true the launcher skips Stop-ProfileProcesses and passes
    # --new-tab so the URL opens as a tab in the already-running browser window
    # instead of killing it and starting a fresh one. This lets open_browsers_delayed
    # kill the profile exactly once (before any subshell is spawned) and then open
    # every subsequent URL as a new tab in the same window.
    local ps_script='param(
    [string]$Url,
    [string]$ProfileSlug,
    [string]$LogFile,
    [switch]$NewTab
)
$ErrorActionPreference = "Stop"

function Write-BrowserLog {
    param([string]$Message)
    if (-not $LogFile) { return }
    try {
        $parent = Split-Path -Parent $LogFile
        if ($parent) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
        Add-Content -Path $LogFile -Value ("[{0}] {1}" -f (Get-Date), $Message) -Encoding UTF8
    } catch {}
}

function Stop-ProfileProcesses {
    param(
        [string]$ProfileDir,
        [string[]]$ProcessNames
    )
    if (-not $ProfileDir -or -not $ProcessNames) { return }
    $normalizedProfile = $ProfileDir.Replace("\\", "/").ToLowerInvariant()
    try {
        $processes = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
            if (-not ($ProcessNames -contains $_.Name) -or -not $_.CommandLine) { $false }
            else { $_.CommandLine.Replace("\\", "/").ToLowerInvariant().Contains($normalizedProfile) }
        })
        Write-BrowserLog ("Matched {0} existing browser process(es) for profile {1}" -f $processes.Count, $ProfileDir)
        foreach ($process in $processes) {
            Write-BrowserLog ("Stopping process {0} pid={1}" -f $process.Name, $process.ProcessId)
            Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
        }
        if ($processes.Count -gt 0) { Start-Sleep -Milliseconds 700 }
        Get-ChildItem -Path $ProfileDir -Filter "Singleton*" -Force -ErrorAction SilentlyContinue |
            Remove-Item -Force -ErrorAction SilentlyContinue
    } catch {
        Write-BrowserLog ("ERROR while stopping profile processes: {0}" -f $_.Exception.Message)
    }
}

$safeSlug = if ($ProfileSlug) { $ProfileSlug -replace "[^a-zA-Z0-9_.-]", "_" } else { "python_api_template" }
Write-BrowserLog ("Launcher started. Url={0}; ProfileSlug={1}; NewTab={2}" -f $Url, $safeSlug, $NewTab)

$edgePaths = @(
    "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
    "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
)
foreach ($edgePath in $edgePaths) {
    if (Test-Path $edgePath) {
        $profileDir = Join-Path $env:TEMP "edge_incog_profile_$safeSlug"
        New-Item -ItemType Directory -Path $profileDir -Force | Out-Null
        if (-not $NewTab) { Stop-ProfileProcesses -ProfileDir $profileDir -ProcessNames @("msedge.exe") }
        $tabFlag = if ($NewTab) { "--new-tab" } else { $null }
        $edgeArgs = @("-inprivate", "--user-data-dir=$profileDir", "--no-first-run", "--no-default-browser-check")
        if ($tabFlag) { $edgeArgs += $tabFlag }
        $edgeArgs += $Url
        $edgeMode = if ($NewTab) { " (new-tab)" } else { "" }
        Write-BrowserLog ("Starting Edge{0}: {1}" -f $edgeMode, $edgePath)
        Start-Process -FilePath $edgePath -ArgumentList $edgeArgs
        Write-BrowserLog "Edge Start-Process returned successfully."
        exit 0
    }
}
Write-BrowserLog "Edge executable not found."

$chromePaths = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
)
foreach ($chromePath in $chromePaths) {
    if (Test-Path $chromePath) {
        $profileDir = Join-Path $env:TEMP "chrome_incog_profile_$safeSlug"
        New-Item -ItemType Directory -Path $profileDir -Force | Out-Null
        if (-not $NewTab) { Stop-ProfileProcesses -ProfileDir $profileDir -ProcessNames @("chrome.exe") }
        $tabFlag = if ($NewTab) { "--new-tab" } else { $null }
        $chromeArgs = @("--incognito", "--user-data-dir=$profileDir", "--no-first-run", "--no-default-browser-check", "--disable-default-apps")
        if ($tabFlag) { $chromeArgs += $tabFlag }
        $chromeArgs += $Url
        $chromeMode = if ($NewTab) { " (new-tab)" } else { "" }
        Write-BrowserLog ("Starting Chrome{0}: {1}" -f $chromeMode, $chromePath)
        Start-Process -FilePath $chromePath -ArgumentList $chromeArgs
        Write-BrowserLog "Chrome Start-Process returned successfully."
        exit 0
    }
}
Write-BrowserLog "Chrome executable not found."

$firefoxPaths = @(
    "$env:ProgramFiles\Mozilla Firefox\firefox.exe",
    "${env:ProgramFiles(x86)}\Mozilla Firefox\firefox.exe"
)
foreach ($firefoxPath in $firefoxPaths) {
    if (Test-Path $firefoxPath) {
        $ffArgs = if ($NewTab) { @("-new-tab", $Url) } else { @("-private-window", $Url) }
        $ffMode = if ($NewTab) { " (new-tab)" } else { "" }
        Write-BrowserLog ("Starting Firefox{0}: {1}" -f $ffMode, $firefoxPath)
        Start-Process -FilePath $firefoxPath -ArgumentList $ffArgs
        Write-BrowserLog "Firefox Start-Process returned successfully."
        exit 0
    }
}
Write-BrowserLog "Firefox executable not found. Falling back to default URL handler."

Start-Process $Url | Out-Null
Write-BrowserLog "Default URL handler Start-Process returned successfully."
'

    printf '%s\n' "$ps_script" > "$launcher_script"

    local launcher_script_win
    local log_file_win
    launcher_script_win=$(wslpath -w "$launcher_script")
    log_file_win=$(wslpath -w "$log_file_abs")

    local new_tab_flag=""
    [ "$new_tab" = "true" ] && new_tab_flag="-NewTab"

    echo "[WEB] Browser launch log: $log_file_abs" >&2
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$launcher_script_win" \
        -Url "$url" -ProfileSlug "$profile_slug" -LogFile "$log_file_win" \
        $new_tab_flag \
        >>"$log_file_abs" 2>&1
    local exit_code=$?
    rm -f "$launcher_script"

    if [ "$exit_code" -ne 0 ]; then
        echo "[WEB] Browser launch failed; see log: $log_file_abs" >&2
        return "$exit_code"
    fi

    return 0
}

#
# Opens a URL with the host operating system's browser in private/incognito mode.
#
# Dispatch order: WSL (Windows host via open_windows_private_browser) →
# macOS → native Linux Chromium/Edge → xdg-open fallback.
#
# Args:
#   $1: Fully qualified URL.
#   $2: new_tab — "true" to open as a tab in the existing window (default: false).
#
# Returns:
#   0 when an opener command was launched, 1 when no opener was found.
#
open_url() {
    local url="$1"
    local new_tab="${2:-false}"
    local edge_profile="/tmp/edge_incog_profile_python_api_template"
    local chrome_profile="/tmp/chrome_incog_profile_python_api_template"

    if is_wsl_environment && open_windows_private_browser "$url" "$new_tab"; then
        return 0
    fi

    if [[ "$OSTYPE" == "darwin"* ]]; then
        if [ -d "/Applications/Google Chrome.app" ]; then
            mkdir -p "$chrome_profile"
            if [ "$new_tab" = "true" ]; then
                open -na "Google Chrome" --args --incognito --user-data-dir="$chrome_profile" --new-tab "$url" >/dev/null 2>&1 || true
            else
                open -na "Google Chrome" --args --incognito --user-data-dir="$chrome_profile" "$url" >/dev/null 2>&1 || true
            fi
            return 0
        fi
        if [ -d "/Applications/Microsoft Edge.app" ]; then
            mkdir -p "$edge_profile"
            if [ "$new_tab" = "true" ]; then
                open -na "Microsoft Edge" --args -inprivate --user-data-dir="$edge_profile" --new-tab "$url" >/dev/null 2>&1 || true
            else
                open -na "Microsoft Edge" --args -inprivate --user-data-dir="$edge_profile" "$url" >/dev/null 2>&1 || true
            fi
            return 0
        fi
        open "$url" 2>/dev/null
        return 0
    fi

    local tab_flag=""
    [ "$new_tab" = "true" ] && tab_flag="--new-tab"

    if command -v microsoft-edge &>/dev/null; then
        mkdir -p "$edge_profile"
        microsoft-edge --inprivate --user-data-dir="$edge_profile" $tab_flag "$url" >/dev/null 2>&1 &
        return 0
    fi

    if command -v google-chrome &>/dev/null; then
        mkdir -p "$chrome_profile"
        google-chrome --incognito --user-data-dir="$chrome_profile" $tab_flag "$url" >/dev/null 2>&1 &
        return 0
    fi

    if command -v chromium-browser &>/dev/null; then
        mkdir -p "$chrome_profile"
        chromium-browser --incognito --user-data-dir="$chrome_profile" $tab_flag "$url" >/dev/null 2>&1 &
        return 0
    fi

    if command -v chromium &>/dev/null; then
        mkdir -p "$chrome_profile"
        chromium --incognito --user-data-dir="$chrome_profile" $tab_flag "$url" >/dev/null 2>&1 &
        return 0
    fi

    if command -v xdg-open &>/dev/null; then
        xdg-open "$url" 2>/dev/null &
        return 0
    fi

    echo "Could not detect browser command. Please open manually: $url"
    return 1
}

#
# kill_browser_profile
# Kills any existing browser processes running under the shared dev profile.
#
# Called once by open_browsers_delayed before spawning per-target subshells so
# the first real open_url starts a fresh window and every subsequent call can
# use --new-tab without a race against a stale singleton lock.
#
# Only effective on WSL/Windows via PowerShell. A no-op on macOS/Linux.
#
# Args:
#   $1: log_file — path to the shared helper log for this session.
#
# Returns:
#   void
#
kill_browser_profile() {
    local log_file="$1"

    if ! is_wsl_environment; then
        return 0
    fi
    if ! command -v powershell.exe >/dev/null 2>&1; then
        return 0
    fi
    if ! command -v wslpath >/dev/null 2>&1; then
        return 0
    fi

    local profile_slug="python_api_template"
    local kill_script_abs
    kill_script_abs="${log_file%.log}_kill_profile_$$.ps1"

    local ps_kill='param([string]$ProfileSlug, [string]$LogFile)
$ErrorActionPreference = "SilentlyContinue"
function Write-BrowserLog { param([string]$Msg)
    if (-not $LogFile) { return }
    try { Add-Content -Path $LogFile -Value ("[{0}] {1}" -f (Get-Date), $Msg) -Encoding UTF8 } catch {}
}
$safeSlug = if ($ProfileSlug) { $ProfileSlug -replace "[^a-zA-Z0-9_.-]", "_" } else { "python_api_template" }
Write-BrowserLog ("kill_browser_profile started for slug={0}" -f $safeSlug)
foreach ($spec in @(@{Exe="msedge.exe"; Dir="edge_incog_profile_$safeSlug"}, @{Exe="chrome.exe"; Dir="chrome_incog_profile_$safeSlug"})) {
    $profileDir = Join-Path $env:TEMP $spec.Dir
    if (-not (Test-Path $profileDir)) { continue }
    $norm = $profileDir.Replace("\\\\", "/").ToLowerInvariant()
    $procs = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -eq $spec.Exe -and $_.CommandLine -and $_.CommandLine.Replace("\\\\", "/").ToLowerInvariant().Contains($norm)
    })
    Write-BrowserLog ("Found {0} process(es) for {1}" -f $procs.Count, $spec.Exe)
    foreach ($p in $procs) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
    if ($procs.Count -gt 0) { Start-Sleep -Milliseconds 700 }
    Get-ChildItem -Path $profileDir -Filter "Singleton*" -Force -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
    Write-BrowserLog ("Profile cleaned: {0}" -f $profileDir)
}
'
    printf '%s
' "$ps_kill" > "$kill_script_abs"

    local kill_script_win log_file_win
    kill_script_win=$(wslpath -w "$kill_script_abs")
    log_file_win=$(wslpath -w "$log_file")

    printf '[%s] kill_browser_profile: killing existing profile processes\n' \
        "$(date '+%Y-%m-%d %H:%M:%S')" >> "$log_file" 2>/dev/null

    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$kill_script_win" \
        -ProfileSlug "$profile_slug" -LogFile "$log_file_win" \
        >>"$log_file" 2>&1

    rm -f "$kill_script_abs"
}

# get_configured_browser_targets
# Reads additional browser targets from ACTIVE_BACKEND_BROWSER_TARGETS.
#
# Returns:
#   Writes newline-delimited entries in the format label|url to stdout.
get_configured_browser_targets() {
    if [ -n "${ACTIVE_BACKEND_BROWSER_TARGETS:-}" ]; then
        printf '%s\n' "${ACTIVE_BACKEND_BROWSER_TARGETS}"
    fi
}

#
# _open_one_target
# Wait for one URL to become reachable, then open it in the browser.
#
# Designed to run inside a background subshell so each target races
# independently — no service waits for another to succeed or time out first.
# All progress is written to the shared helper log file.
#
# Args:
#   $1: label    — human-readable name shown in log and timeout messages.
#   $2: url      — fully qualified URL to wait for and open.
#   $3: timeout  — max seconds to wait before giving up.
#   $4: log_file — path to the shared helper log for this session.
#   $5: new_tab  — "true" to open as a tab in the already-running window
#                  (default: false). The profile was already killed by the
#                  caller so no Stop-ProfileProcesses step is needed.
#
# Returns:
#   void
#
_open_one_target() {
    local label="$1"
    local url="$2"
    local timeout="$3"
    local log_file="$4"
    local new_tab="${5:-false}"

    printf '[%s] START label=%s url=%s timeout=%ss new_tab=%s\n' \
        "$(date '+%Y-%m-%d %H:%M:%S')" "$label" "$url" "$timeout" "$new_tab" >> "$log_file" 2>/dev/null

    if wait_for_url "$url" "$timeout" "$log_file"; then
        printf '[%s] READY label=%s url=%s — opening browser (new_tab=%s)\n' \
            "$(date '+%Y-%m-%d %H:%M:%S')" "$label" "$url" "$new_tab" >> "$log_file" 2>/dev/null
        open_url "$url" "$new_tab"
        printf '[%s] OPEN_RETURNED label=%s\n' \
            "$(date '+%Y-%m-%d %H:%M:%S')" "$label" >> "$log_file" 2>/dev/null
    else
        printf '[%s] TIMEOUT label=%s url=%s\n' \
            "$(date '+%Y-%m-%d %H:%M:%S')" "$label" "$url" >> "$log_file" 2>/dev/null
        echo "⚠️  Timeout waiting for ${label} at ${url}"
    fi
}

#
# open_browsers_delayed
# Displays service URLs and opens browsers when each service becomes available.
#
# Creates a helper log file immediately before any waits begin so failures
# always leave a readable artifact. Spawns one independent background subshell
# per target so API, Neo4j, and extra targets such as pgAdmin race concurrently
# — a slow API startup no longer prevents pgAdmin from opening.
#
# Args:
#   port:          The port the API is running on.
#   include_neo4j: "true" or "false" — whether to also open Neo4j browser.
#   timeout:       Maximum seconds to wait per service (default: 120).
#
# Returns:
#   void
#
open_browsers_delayed() {
    local port="$1"
    local include_neo4j="$2"
    local timeout="${3:-120}"

    local api_url="http://localhost:$port/docs"
    local neo4j_url="http://localhost:7474"
    local target_line target_label target_url

    #
    # Create the helper log file upfront so it exists even if every target
    # times out before open_url is called.
    #
    local log_dir="${HOME}/.browser-helper-logs"
    mkdir -p "$log_dir"
    local log_file_abs
    log_file_abs="${log_dir}/browser_open_$(date +%Y%m%d_%H%M%S)_$$.log"

    printf '[%s] Browser auto-open helper started. AppId=%s Api=%s Timeout=%ss\n' \
        "$(date '+%Y-%m-%d %H:%M:%S')" "${ACTIVE_BACKEND_APP_ID:-unknown}" "$api_url" "$timeout" \
        >> "$log_file_abs" 2>/dev/null

    echo ""
    echo "========================================"
    echo "  Services will be accessible at:"
    echo "  • API Docs: $api_url"
    if [ "$include_neo4j" = "true" ]; then
        echo "  • Neo4j Browser: $neo4j_url"
    fi
    while IFS= read -r target_line || [ -n "$target_line" ]; do
        target_line="${target_line%$'\r'}"
        [ -z "$target_line" ] && continue
        target_label="${target_line%%|*}"
        target_url="${target_line#*|}"
        [ -z "$target_url" ] && continue
        echo "  • ${target_label}: ${target_url}"
    done < <(get_configured_browser_targets)
    echo "========================================"
    echo ""
    if [ -n "${PGADMIN_EMAIL:-}" ] || [ -n "${MONGO_EXPRESS_USERNAME:-}" ]; then
        echo "Monitoring UI credentials:"
        if [ -n "${PGADMIN_EMAIL:-}" ]; then
            echo "  • pgAdmin: ${PGADMIN_EMAIL} / ${PGADMIN_PASSWORD:-admin}"
        fi
        if [ -n "${MONGO_EXPRESS_USERNAME:-}" ]; then
            echo "  • Mongo Express: ${MONGO_EXPRESS_USERNAME} / ${MONGO_EXPRESS_PASSWORD:-admin}"
        fi
        echo ""
    fi
    echo "🌐 Browser will open automatically when services are ready..."
    echo "[WEB] Browser auto-open log: $log_file_abs"
    echo ""

    #
    # Kill the shared browser profile exactly once so the first opener starts a
    # fresh incognito window and every subsequent opener uses --new-tab to add a
    # tab to that window instead of killing it again.
    #
    kill_browser_profile "$log_file_abs"

    #
    # Spawn one independent background subshell per target so each races
    # concurrently. A slow API startup no longer delays pgAdmin from opening.
    # The first target opens a new window (new_tab=false); all remaining targets
    # open as tabs (new_tab=true).
    #
    _open_one_target "API Docs" "$api_url" "$timeout" "$log_file_abs" "false" &

    if [ "$include_neo4j" = "true" ]; then
        _open_one_target "Neo4j" "$neo4j_url" "$timeout" "$log_file_abs" "true" &
    fi

    while IFS= read -r target_line || [ -n "$target_line" ]; do
        target_line="${target_line%$'\r'}"
        [ -z "$target_line" ] && continue
        target_label="${target_line%%|*}"
        target_url="${target_line#*|}"
        [ -z "$target_url" ] && continue
        _open_one_target "$target_label" "$target_url" "$timeout" "$log_file_abs" "true" &
    done < <(get_configured_browser_targets)
}
