#!/bin/bash
#
# bootstrap_utils.sh
#
# Purpose:
# - Bootstrap utilities for the Keycloak realm used by python-api-template.
# - Builds and runs the Docker-based bootstrap image.
#
# Usage:
#   Source this file and call run_keycloak_bootstrap.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SETUP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_ROOT="$(cd "${SETUP_DIR}/.." && pwd)"

BOOTSTRAP_ENV_FILE="${PROJECT_ROOT}/.env"
BOOTSTRAP_DIR="${PROJECT_ROOT}/keycloak/bootstrap"
BOOTSTRAP_IMAGE="python-api-template-keycloak-bootstrap"

# Retrieve environment values from .env or current shell.
#
# Args:
#   key: Environment variable name.
#   default_value: Fallback value when unset.
#
# Returns:
#   Resolved value from .env, environment, or default.
_bootstrap_get_env_value() {
    local key="$1"
    local default_value="${2:-}"
    local value=""

    if declare -F read_env_variable >/dev/null; then
        value=$(read_env_variable "$key" "$BOOTSTRAP_ENV_FILE" "")
    fi

    if [ -z "$value" ]; then
        value="${!key}"
    fi

    if [ -z "$value" ]; then
        value="$default_value"
    fi

    echo "$value"
}

# Determine whether Docker host networking is supported.
#
# Returns:
#   0 when host networking is supported, 1 otherwise.
_bootstrap_supports_host_network() {
    case "$(uname -s)" in
        Linux*) return 0 ;;
        *) return 1 ;;
    esac
}

# Resolve the Keycloak URL for bootstrap.
#
# Returns:
#   Keycloak URL used for connectivity checks.
_bootstrap_get_keycloak_url() {
    local url

    url="$(_bootstrap_get_env_value "KEYCLOAK_BOOTSTRAP_URL" "")"
    if [ -z "$url" ]; then
        url="$(_bootstrap_get_env_value "KEYCLOAK_SERVER_URL" "")"
    fi
    if [ -z "$url" ]; then
        url="$(_bootstrap_get_env_value "KEYCLOAK_INTERNAL_URL" "")"
    fi

    echo "${url:-http://localhost:9090}"
}

# Normalize a Keycloak URL for the bootstrap container.
#
# Args:
#   url: Base Keycloak URL.
#   use_host_network: Whether host networking is used.
#
# Returns:
#   Container-safe URL.
_bootstrap_normalize_url_for_container() {
    local url="$1"
    local use_host_network="$2"
    local normalized="$url"

    if [ "$use_host_network" = "true" ]; then
        echo "$normalized"
        return
    fi

    normalized="${normalized/localhost/host.docker.internal}"
    normalized="${normalized/127.0.0.1/host.docker.internal}"
    echo "$normalized"
}

# Test whether Keycloak is reachable at the provided URL.
#
# Args:
#   keycloak_url: Base Keycloak URL.
#
# Returns:
#   0 when reachable, 1 otherwise.
_test_keycloak_connection() {
    local keycloak_url="$1"

    echo "🔍 Checking Keycloak at $keycloak_url..."

    if curl -s --connect-timeout 10 "$keycloak_url/" > /dev/null 2>&1; then
        echo "✅ Keycloak is reachable"
        return 0
    elif curl -s --connect-timeout 10 "$keycloak_url/" 2>&1 | grep -q "405"; then
        echo "✅ Keycloak is reachable"
        return 0
    else
        echo "❌ Keycloak is not reachable at $keycloak_url"
        echo "   Please start Keycloak first."
        return 1
    fi
}

# Verify Docker and Keycloak prerequisites.
#
# Args:
#   keycloak_url: Base Keycloak URL.
#
# Returns:
#   0 when prerequisites are satisfied, 1 otherwise.
_bootstrap_validate_prereqs() {
    local keycloak_url="$1"

    if declare -F check_docker_installation >/dev/null; then
        if ! check_docker_installation; then
            return 1
        fi
    fi

    if ! _test_keycloak_connection "$keycloak_url"; then
        return 1
    fi

    if [ ! -d "$BOOTSTRAP_DIR" ]; then
        echo "❌ Bootstrap directory not found at $BOOTSTRAP_DIR"
        return 1
    fi

    return 0
}

# Build the bootstrap Docker image.
#
# Returns:
#   0 when build succeeds, 1 otherwise.
_bootstrap_build_image() {
    echo ""
    echo "🐳 Building bootstrap image..."
    if ! docker build -t "$BOOTSTRAP_IMAGE" "$BOOTSTRAP_DIR"; then
        echo "❌ Docker build failed"
        return 1
    fi

    return 0
}

# Prepare bootstrap configuration values for container execution.
#
# Args:
#   keycloak_url: Base Keycloak URL.
#   use_host_network: Whether host networking is enabled.
#
# Returns:
#   None. Populates BOOTSTRAP_* variables for the bootstrap run.
_bootstrap_prepare_config() {
    local keycloak_url="$1"
    local use_host_network="$2"

    BOOTSTRAP_CONTAINER_URL="$(_bootstrap_normalize_url_for_container "$keycloak_url" "$use_host_network")"
    BOOTSTRAP_ADMIN_USER="$(_bootstrap_get_env_value "KEYCLOAK_ADMIN" "admin")"
    BOOTSTRAP_ADMIN_PASSWORD="$(_bootstrap_get_env_value "KEYCLOAK_ADMIN_PASSWORD" "admin")"
    BOOTSTRAP_REALM="$(_bootstrap_get_env_value "KEYCLOAK_REALM" "python-api-template")"
    BOOTSTRAP_BACKEND_CLIENT_ID="$(_bootstrap_get_env_value "KEYCLOAK_BACKEND_CLIENT_ID" "")"
    if [ -z "$BOOTSTRAP_BACKEND_CLIENT_ID" ]; then
        BOOTSTRAP_BACKEND_CLIENT_ID="$(_bootstrap_get_env_value "KEYCLOAK_CLIENT_ID" "python-api-template-backend")"
    fi
    BOOTSTRAP_FRONTEND_CLIENT_ID="$(_bootstrap_get_env_value "KEYCLOAK_FRONTEND_CLIENT_ID" "python-api-template-frontend")"
    BOOTSTRAP_FRONTEND_ROOT_URL="$(_bootstrap_get_env_value "KEYCLOAK_FRONTEND_ROOT_URL" "http://localhost:3000")"
    BOOTSTRAP_API_ROOT_URL="$(_bootstrap_get_env_value "KEYCLOAK_API_ROOT_URL" "http://localhost:8000")"
    BOOTSTRAP_ROLES="$(_bootstrap_get_env_value "KEYCLOAK_ROLES" "")"
    BOOTSTRAP_USERS="$(_bootstrap_get_env_value "KEYCLOAK_USERS" "")"
    BOOTSTRAP_SERVICE_ACCOUNT_ROLE="$(_bootstrap_get_env_value "KEYCLOAK_SERVICE_ACCOUNT_ROLE" "")"
}

# Run the bootstrap container with prepared configuration values.
#
# Args:
#   use_host_network: Whether host networking is enabled.
#
# Returns:
#   0 when the container succeeds, 1 otherwise.
_bootstrap_run_container() {
    local use_host_network="$1"
    local -a run_args

    run_args=(--rm)

    if [ "$use_host_network" = "true" ]; then
        run_args+=(--network host)
    fi

    run_args+=(-e "KEYCLOAK_URL=$BOOTSTRAP_CONTAINER_URL")
    run_args+=(-e "KEYCLOAK_ADMIN=$BOOTSTRAP_ADMIN_USER")
    run_args+=(-e "KEYCLOAK_ADMIN_PASSWORD=$BOOTSTRAP_ADMIN_PASSWORD")
    run_args+=(-e "KEYCLOAK_REALM=$BOOTSTRAP_REALM")
    run_args+=(-e "KEYCLOAK_FRONTEND_CLIENT_ID=$BOOTSTRAP_FRONTEND_CLIENT_ID")
    run_args+=(-e "KEYCLOAK_BACKEND_CLIENT_ID=$BOOTSTRAP_BACKEND_CLIENT_ID")
    run_args+=(-e "KEYCLOAK_FRONTEND_ROOT_URL=$BOOTSTRAP_FRONTEND_ROOT_URL")
    run_args+=(-e "KEYCLOAK_API_ROOT_URL=$BOOTSTRAP_API_ROOT_URL")

    if [ -n "$BOOTSTRAP_ROLES" ]; then
        run_args+=(-e "KEYCLOAK_ROLES=$BOOTSTRAP_ROLES")
    fi

    if [ -n "$BOOTSTRAP_USERS" ]; then
        run_args+=(-e "KEYCLOAK_USERS=$BOOTSTRAP_USERS")
    fi

    if [ -n "$BOOTSTRAP_SERVICE_ACCOUNT_ROLE" ]; then
        run_args+=(-e "KEYCLOAK_SERVICE_ACCOUNT_ROLE=$BOOTSTRAP_SERVICE_ACCOUNT_ROLE")
    fi

    echo ""
    echo "🚀 Running bootstrap container..."
    if docker run "${run_args[@]}" "$BOOTSTRAP_IMAGE"; then
        return 0
    fi

    return 1
}

# Build and run the Docker-based Keycloak bootstrap script.
#
# Returns:
#   0 when bootstrap completes successfully, 1 otherwise.
run_keycloak_bootstrap() {
    echo ""
    echo "🧩 Keycloak realm bootstrap"
    echo "---------------------------"

    local keycloak_url
    keycloak_url="$(_bootstrap_get_keycloak_url)"
    if ! _bootstrap_validate_prereqs "$keycloak_url"; then
        return 1
    fi

    if ! _bootstrap_build_image; then
        return 1
    fi

    local use_host_network="false"
    if _bootstrap_supports_host_network; then
        use_host_network="true"
    fi

    _bootstrap_prepare_config "$keycloak_url" "$use_host_network"

    if _bootstrap_run_container "$use_host_network"; then
        echo ""
        echo "🎉 Keycloak realm bootstrap complete!"
        return 0
    fi

    echo "❌ Bootstrap failed"
    return 1
}
