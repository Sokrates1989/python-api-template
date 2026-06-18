#!/usr/bin/env bash
#
# run-phase5-drill.sh
#
# Runs the Phase 5 provider drill matrix.  For each selected database profile
# the script:
#   1. Tears down any leftover containers from a previous run.
#   2. Starts the stack (with or without a build).
#   3. Waits for the API to become ready with the expected provider profile.
#   4. Validates /health, /database/provider-info, /database/lock, and
#      /database/unlock endpoints.
#   5. Tears down the stack (unless --keep-last is set).
#
# Usage:
#   ./local-deployment/run-phase5-drill.sh [options]
#
# Options:
#   --profile <all|postgres|neo4j|mongodb>
#             Which profile(s) to run (default: all).
#   --timeout <seconds>
#             API readiness timeout per profile (default: 300).
#   --no-build
#             Skip --build when starting containers.
#   --keep-last
#             Leave the last profile's containers running after the drill.
#
# Returns:
#   0 when all selected profiles pass, 1 otherwise.

set -o errexit
set -o nounset
set -o pipefail

# Change to the repository root so all relative paths resolve correctly.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

PROFILE="all"
TIMEOUT_SECONDS=300
NO_BUILD=false
KEEP_LAST=false

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

while [[ $# -gt 0 ]]; do
    case "$1" in
        --profile)
            PROFILE="${2:?--profile requires a value}"
            shift 2
            ;;
        --timeout)
            TIMEOUT_SECONDS="${2:?--timeout requires a value}"
            shift 2
            ;;
        --no-build)
            NO_BUILD=true
            shift
            ;;
        --keep-last)
            KEEP_LAST=true
            shift
            ;;
        *)
            echo "[ERROR] Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Profile definitions
# ---------------------------------------------------------------------------

# Each entry is a pipe-delimited string: name|env_file|compose_file|expected_profile
ALL_PROFILES=(
    "postgres|.env.drill.postgres|local-deployment/docker-compose.postgres.yml|sql"
    "neo4j|.env.drill.neo4j|local-deployment/docker-compose.neo4j.yml|neo4j"
    "mongodb|.env.drill.mongodb|local-deployment/docker-compose.mongodb.yml|mongodb"
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

#
# Read a single key from an env file, stripping comments and whitespace.
#
# Args:
#   env_file - path to the env file
#   key      - variable name to look up
#
# Returns:
#   Prints the value to stdout, or empty string if not found.
#
get_env_value() {
    local env_file="$1"
    local key="$2"
    grep -E "^${key}=" "$env_file" 2>/dev/null | head -n1 | cut -d'=' -f2- | tr -d '\r' | sed "s/^[[:space:]]*//;s/[[:space:]]*$//"
}

#
# Run docker compose for a project and abort on failure.
#
# Args:
#   project_name  - Docker Compose project name
#   env_file      - path to the --env-file
#   compose_file  - path to the -f compose file
#   args...       - additional arguments (e.g. "up -d --build")
#
run_compose() {
    local project_name="$1"
    local env_file="$2"
    local compose_file="$3"
    shift 3
    docker compose -p "$project_name" --env-file "$env_file" -f "$compose_file" "$@"
    local exit_code=$?
    if [ $exit_code -ne 0 ]; then
        echo "[ERROR] docker compose failed (exit $exit_code): project=$project_name env=$env_file compose=$compose_file args=$*" >&2
        return $exit_code
    fi
}

#
# Wait until the 'app' service is listed as running.
#
# Args:
#   project_name - Docker Compose project name
#   env_file     - path to the --env-file
#   compose_file - path to the compose file
#   timeout      - seconds to wait before giving up (default: 60)
#
assert_app_running() {
    local project_name="$1"
    local env_file="$2"
    local compose_file="$3"
    local timeout="${4:-60}"
    local deadline=$(( $(date +%s) + timeout ))

    while true; do
        local running_services
        running_services=$(docker compose -p "$project_name" --env-file "$env_file" -f "$compose_file" ps --status running --services 2>/dev/null || true)
        if printf '%s\n' "$running_services" | grep -qx "app"; then
            return 0
        fi

        if [ "$(date +%s)" -ge "$deadline" ]; then
            echo "  App service is not running; showing compose status and logs..." >&2
            docker compose -p "$project_name" --env-file "$env_file" -f "$compose_file" ps >&2 || true
            docker compose -p "$project_name" --env-file "$env_file" -f "$compose_file" logs --tail 150 >&2 || true
            echo "[ERROR] App service not running for project '$project_name'." >&2
            return 1
        fi

        sleep 2
    done
}

#
# Poll the health endpoint until the expected provider profile is reported.
#
# Args:
#   url              - full health endpoint URL
#   timeout          - seconds to wait before giving up
#   expected_profile - expected value of .provider_profile in the JSON response
#
wait_for_api() {
    local url="$1"
    local timeout="$2"
    local expected_profile="${3:-}"
    local deadline=$(( $(date +%s) + timeout ))
    local last_profile="<none>"
    local last_error="<none>"
    local last_progress_second=-1

    while true; do
        local remaining=$(( deadline - $(date +%s) ))
        if [ $remaining -le 0 ]; then
            echo "[ERROR] API not ready at $url within ${timeout}s." >&2
            echo "  Expected profile: '$expected_profile', last observed: '$last_profile', last error: '$last_error'" >&2
            return 1
        fi

        # Print progress every 10 seconds.
        local progress_slot=$(( remaining / 10 ))
        if [ "$progress_slot" != "$last_progress_second" ]; then
            echo "  waiting for API/profile readiness... remaining ${remaining}s (last profile: $last_profile, last error: $last_error)"
            last_progress_second="$progress_slot"
        fi

        local http_status
        http_status=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 --max-time 5 "$url" 2>/dev/null || echo "000")

        if [ "$http_status" = "200" ]; then
            if [ -z "$expected_profile" ]; then
                return 0
            fi

            local body
            body=$(curl -s --connect-timeout 3 --max-time 5 "$url" 2>/dev/null || echo "{}")
            last_profile=$(printf '%s' "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('provider_profile','<missing>'))" 2>/dev/null || echo "<parse-error>")

            if [ "$last_profile" = "$expected_profile" ]; then
                return 0
            fi
        else
            last_error="HTTP $http_status"
        fi

        sleep 2
    done
}

# ---------------------------------------------------------------------------
# Main drill loop
# ---------------------------------------------------------------------------

# Filter profiles.
SELECTED_PROFILES=()
for entry in "${ALL_PROFILES[@]}"; do
    name="${entry%%|*}"
    if [ "$PROFILE" = "all" ] || [ "$name" = "$PROFILE" ]; then
        SELECTED_PROFILES+=("$entry")
    fi
done

if [ ${#SELECTED_PROFILES[@]} -eq 0 ]; then
    echo "[ERROR] No profile selected for '$PROFILE'. Valid values: all, postgres, neo4j, mongodb." >&2
    exit 1
fi

declare -a RESULTS=()
OVERALL_OK=true

for i in "${!SELECTED_PROFILES[@]}"; do
    entry="${SELECTED_PROFILES[$i]}"
    IFS='|' read -r name env_file compose_file expected_profile <<< "$entry"
    is_last=false
    [ $i -eq $(( ${#SELECTED_PROFILES[@]} - 1 )) ] && is_last=true

    project_name="python-api-template-drill-${name}"

    echo ""
    echo "=== Phase 5 Drill: ${name} ==="

    profile_ok=true

    (
        set -e
        echo "  tearing down old containers..."
        run_compose "$project_name" "$env_file" "$compose_file" down --remove-orphans >/dev/null 2>&1 || true

        if [ "$NO_BUILD" = "true" ]; then
            echo "  starting services (no build)..."
            run_compose "$project_name" "$env_file" "$compose_file" up -d || \
                { echo "  no-build startup failed, retrying with build..."; run_compose "$project_name" "$env_file" "$compose_file" up -d --build; }
        else
            echo "  starting services (with build)..."
            run_compose "$project_name" "$env_file" "$compose_file" up -d --build
        fi

        assert_app_running "$project_name" "$env_file" "$compose_file" 90

        wait_for_api "http://localhost:8081/health" "$TIMEOUT_SECONDS" "$expected_profile"
        echo "  API ready with expected profile '$expected_profile'"

        admin_key="$(get_env_value "$env_file" "ADMIN_API_KEY")"
        if [ -z "$admin_key" ]; then
            echo "[ERROR] ADMIN_API_KEY not found in $env_file." >&2
            exit 1
        fi

        provider_json=$(curl -s --connect-timeout 5 --max-time 10 \
            -H "X-Admin-Key: $admin_key" \
            "http://localhost:8081/database/provider-info" 2>/dev/null || echo "{}")
        observed_profile=$(printf '%s' "$provider_json" | python3 -c \
            "import sys,json; d=json.load(sys.stdin); print(d.get('provider_profile','<missing>'))" 2>/dev/null || echo "<parse-error>")
        if [ "$observed_profile" != "$expected_profile" ]; then
            echo "[ERROR] Provider mismatch for $name: expected '$expected_profile', got '$observed_profile'." >&2
            exit 1
        fi
        echo "  provider-info check passed"

        lock_json=$(curl -s --connect-timeout 5 --max-time 10 \
            -X POST \
            -H "X-Admin-Key: $admin_key" \
            -H "Content-Type: application/json" \
            -d '{"operation":"phase5_drill"}' \
            "http://localhost:8081/database/lock" 2>/dev/null || echo "{}")
        lock_success=$(printf '%s' "$lock_json" | python3 -c \
            "import sys,json; d=json.load(sys.stdin); print(str(d.get('success',False)).lower())" 2>/dev/null || echo "false")
        lock_locked=$(printf '%s' "$lock_json" | python3 -c \
            "import sys,json; d=json.load(sys.stdin); print(str(d.get('is_locked',False)).lower())" 2>/dev/null || echo "false")
        if [ "$lock_success" != "true" ] || [ "$lock_locked" != "true" ]; then
            echo "[ERROR] Lock check failed for $name." >&2
            exit 1
        fi
        echo "  lock check passed"

        unlock_json=$(curl -s --connect-timeout 5 --max-time 10 \
            -X POST \
            -H "X-Admin-Key: $admin_key" \
            "http://localhost:8081/database/unlock" 2>/dev/null || echo "{}")
        unlock_success=$(printf '%s' "$unlock_json" | python3 -c \
            "import sys,json; d=json.load(sys.stdin); print(str(d.get('success',False)).lower())" 2>/dev/null || echo "false")
        unlock_locked=$(printf '%s' "$unlock_json" | python3 -c \
            "import sys,json; d=json.load(sys.stdin); print(str(d.get('is_locked',True)).lower())" 2>/dev/null || echo "true")
        if [ "$unlock_success" != "true" ] || [ "$unlock_locked" = "true" ]; then
            echo "[ERROR] Unlock check failed for $name." >&2
            exit 1
        fi
        echo "  unlock check passed"

        RESULTS+=("${name}|${expected_profile}|ok")
    ) || profile_ok=false

    if ! "$is_last" || [ "$KEEP_LAST" = "false" ]; then
        echo "  stopping profile '$name'"
        docker compose -p "$project_name" --env-file "$env_file" -f "$compose_file" down --remove-orphans >/dev/null 2>&1 || true
    fi

    if [ "$profile_ok" = "false" ]; then
        OVERALL_OK=false
        RESULTS+=("${name}|${expected_profile}|FAILED")
    else
        RESULTS+=("${name}|${expected_profile}|ok")
    fi
done

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo ""
echo "Phase 5 drill results:"
printf "%-12s  %-15s  %s\n" "Profile" "Provider" "Result"
printf "%-12s  %-15s  %s\n" "-------" "--------" "------"
for result in "${RESULTS[@]}"; do
    IFS='|' read -r rname rprovider rstatus <<< "$result"
    printf "%-12s  %-15s  %s\n" "$rname" "$rprovider" "$rstatus"
done

echo ""
if [ "$OVERALL_OK" = "true" ]; then
    echo "All profiles passed."
    exit 0
else
    echo "One or more profiles failed." >&2
    exit 1
fi
