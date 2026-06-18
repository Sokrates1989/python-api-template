#!/usr/bin/env bash
#
# verify-release-safe.sh
#
# Runs a set of safe, non-destructive checks that must pass before a release
# gate or drill matrix is started.  Safe checks require no Docker or network
# access – they validate file existence and Python syntax only.
#
# Usage:
#   ./local-deployment/verify-release-safe.sh [--strict]
#
# Options:
#   --strict   Exit with a non-zero code when any check fails (default: report
#              failures but exit 0 so callers can decide whether to abort).
#
# Returns:
#   0 when all checks pass, or when not in strict mode and some checks fail.
#   1 when in strict mode and one or more checks failed.

set -o errexit
set -o nounset
set -o pipefail

# Change to the repository root so all relative paths resolve correctly.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

# ---------------------------------------------------------------------------
# Option parsing
# ---------------------------------------------------------------------------

STRICT=false
for arg in "$@"; do
    case "$arg" in
        --strict) STRICT=true ;;
    esac
done

# ---------------------------------------------------------------------------
# Result accumulation
# ---------------------------------------------------------------------------

declare -a CHECK_NAMES=()
declare -a CHECK_STATUSES=()
declare -a CHECK_DETAILS=()

#
# Record the result of a single check.
#
# Args:
#   name    - human-readable label for the check
#   passed  - "true" or "false"
#   details - supplementary text (path, error message, etc.)
#
add_check_result() {
    local name="$1"
    local passed="$2"
    local details="$3"
    CHECK_NAMES+=("$name")
    CHECK_STATUSES+=("$passed")
    CHECK_DETAILS+=("$details")
}

#
# Assert that a file exists and record the result.
#
# Args:
#   path  - file-system path to check
#   label - human-readable label
#
assert_file_exists() {
    local path="$1"
    local label="$2"
    if [ -f "$path" ]; then
        add_check_result "$label" "true" "$path"
    else
        add_check_result "$label" "false" "Missing: $path"
    fi
}

# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

echo "Running safe release verification checks..."

# Required roadmap and operations docs.
assert_file_exists "docs/IMPROVEMENT_PLAN_PROGRESS.md" "Roadmap progress document"
assert_file_exists "docs/STARTUP_PROBES.md"            "Startup probes document"
assert_file_exists "docs/RELEASE_CHECKLIST.md"         "Release checklist document"

# Required drill scripts (Bash variants are now the source of truth).
assert_file_exists "local-deployment/run-phase5-drill.sh"     "Phase 5 drill script"
assert_file_exists "local-deployment/verify-release-safe.sh"  "Safe verification script"
assert_file_exists "local-deployment/run-release-gate.sh"     "Release gate script"

# Required drill env files.
assert_file_exists ".env.drill.postgres" "Drill env (Postgres)"
assert_file_exists ".env.drill.neo4j"    "Drill env (Neo4j)"
assert_file_exists ".env.drill.mongodb"  "Drill env (MongoDB)"

# Python syntax sanity for key runtime modules.
if command -v python3 &>/dev/null || command -v python &>/dev/null; then
    PYTHON_CMD="$(command -v python3 || command -v python)"
    COMPILE_OUTPUT="$("$PYTHON_CMD" -m compileall \
        app/main.py \
        app/api/config/lifecycle.py \
        app/backend/database/init_db.py \
        app/backend/database/startup_probe.py \
        app/backend/observability.py \
        qa_pytest/unit/test_startup_probe.py 2>&1)"
    if [ $? -eq 0 ]; then
        add_check_result "Python syntax compile check" "true" "compileall passed"
    else
        add_check_result "Python syntax compile check" "false" "$COMPILE_OUTPUT"
    fi
else
    add_check_result "Python syntax compile check" "false" "python not found on PATH"
fi

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

echo ""
echo "Safe verification results:"
printf "%-45s  %-6s  %s\n" "Check" "Passed" "Details"
printf "%-45s  %-6s  %s\n" "-----" "------" "-------"

FAILED_COUNT=0
for i in "${!CHECK_NAMES[@]}"; do
    local_passed="${CHECK_STATUSES[$i]}"
    if [ "$local_passed" = "true" ]; then
        status_label="OK"
    else
        status_label="FAIL"
        FAILED_COUNT=$((FAILED_COUNT + 1))
    fi
    printf "%-45s  %-6s  %s\n" "${CHECK_NAMES[$i]}" "$status_label" "${CHECK_DETAILS[$i]}"
done

echo ""

if [ "$FAILED_COUNT" -gt 0 ]; then
    echo "Some checks failed ($FAILED_COUNT failure(s))."
    if [ "$STRICT" = "true" ]; then
        echo "Strict mode: aborting." >&2
        exit 1
    fi
else
    echo "All safe checks passed."
fi

echo ""
echo "Next manual steps (requires Docker/runtime):"
echo "  1) ./local-deployment/run-phase5-drill.sh --profile all"
echo "  2) Execute full pytest matrix in CI/local containers"
