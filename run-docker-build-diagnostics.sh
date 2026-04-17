#!/usr/bin/env bash
# Root-level wrapper for Docker/build diagnostics.
# Uses the core-pdm-manager submodule directly.

set -o errexit
set -o nounset
set -o pipefail

CORE_SCRIPT="./tools/core-pdm-manager/scripts/diagnostics.sh"

if [ -x "${CORE_SCRIPT}" ]; then
    exec "${CORE_SCRIPT}" --project-root . "$@"
fi

echo "[ERROR] Missing diagnostics entrypoint: ${CORE_SCRIPT}"
echo "        To fix: git submodule update --init --recursive"
exit 1
