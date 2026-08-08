#!/usr/bin/env bash
# =============================================================================
# Module: test_semver_menu.sh
#
# Description:
#     Verifies the canonical API semantic-version menu aliases and default.
# =============================================================================

set -euo pipefail

TEST_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SEMVER_MENU_USE_STDIN=1
source "${TEST_ROOT}/setup/modules/version_manager.sh"

# Assert one selector response without requiring a controlling terminal.
#
# Args:
#   $1: Simulated operator input.
#   $2: Expected selected version.
#
# Returns:
#   0 when the selector matches; otherwise exits the test with an error.
assert_selection() {
    local input="$1"
    local expected="$2"
    local actual=""

    actual="$(select_semver_version "1.2.3" "Test" false <<< "$input")"
    if [ "$actual" != "$expected" ]; then
        printf 'Expected %s for %q, received %s.\n' "$expected" "$input" "$actual" >&2
        exit 1
    fi
}

assert_selection "" "1.2.3"
assert_selection "k" "1.2.3"
assert_selection "p" "1.2.4"
assert_selection "f" "1.3.0"
assert_selection "m" "2.0.0"
assert_selection $'e\n1.4.2' "1.4.2"

printf '%s\n' "Canonical API semantic-version menu passed."
