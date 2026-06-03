#!/usr/bin/env bash
# Root-level wrapper for dependency management.
# Uses the core-pdm-manager submodule directly.

set -o errexit
set -o nounset
set -o pipefail

CORE_SCRIPT="./tools/core-pdm-manager/scripts/pdm-manager.sh"
PROJECT_ROOT="${PDM_MANAGER_PROJECT_ROOT:-.}"

if [ -x "$CORE_SCRIPT" ]; then
    if [ "${1:-}" = "initial-run" ]; then
        exec "$CORE_SCRIPT" --project-root "$PROJECT_ROOT" --initial-run --non-interactive "${@:2}"
    fi
    exec "$CORE_SCRIPT" --project-root "$PROJECT_ROOT" "$@"
fi

echo "[ERROR] Missing dependency manager entrypoint: $CORE_SCRIPT"
echo "        Ensure submodule is initialized: git submodule update --init --recursive"
exit 1
