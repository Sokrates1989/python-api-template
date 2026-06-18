#!/usr/bin/env bash
#
# run-release-gate.sh
#
# Orchestrates the two-stage release gate:
#   Stage 1: Safe verification checks (no Docker/network required).
#   Stage 2: Provider drill matrix (requires Docker).
#
# Both stages must pass for the gate to succeed.  Individual stages can be
# skipped via flags for partial runs during development.
#
# Usage:
#   ./local-deployment/run-release-gate.sh [options]
#
# Options:
#   --skip-safe-checks   Skip stage 1 (safe verification).
#   --skip-drill         Skip stage 2 (provider drill matrix).
#   --no-build           Forward --no-build to the drill script.
#   --drill-timeout <s>  Seconds to wait per profile (default: 300).
#
# Returns:
#   0 when all enabled stages pass, 1 otherwise.

set -o errexit
set -o nounset
set -o pipefail

# Change to the repository root so all relative paths resolve correctly.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

SKIP_SAFE_CHECKS=false
SKIP_DRILL=false
NO_BUILD=false
DRILL_TIMEOUT=300

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-safe-checks) SKIP_SAFE_CHECKS=true; shift ;;
        --skip-drill)       SKIP_DRILL=true;        shift ;;
        --no-build)         NO_BUILD=true;           shift ;;
        --drill-timeout)
            DRILL_TIMEOUT="${2:?--drill-timeout requires a value}"
            shift 2
            ;;
        *)
            echo "[ERROR] Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Gate execution
# ---------------------------------------------------------------------------

echo "Release gate started..."

if [ "$SKIP_SAFE_CHECKS" = "false" ]; then
    echo ""
    echo "[Stage 1/2] Running safe verification checks"
    bash local-deployment/verify-release-safe.sh --strict
else
    echo ""
    echo "[Stage 1/2] Skipped safe verification checks"
fi

if [ "$SKIP_DRILL" = "false" ]; then
    echo ""
    echo "[Stage 2/2] Running provider drill matrix"

    DRILL_ARGS=("--profile" "all" "--timeout" "$DRILL_TIMEOUT")
    if [ "$NO_BUILD" = "true" ]; then
        DRILL_ARGS+=("--no-build")
    fi

    bash local-deployment/run-phase5-drill.sh "${DRILL_ARGS[@]}"
else
    echo ""
    echo "[Stage 2/2] Skipped provider drill matrix"
fi

echo ""
echo "Release gate completed successfully."
echo "Recommended next step: run CI matrix or merge if CI is already green."
