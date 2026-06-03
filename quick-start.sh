#!/bin/bash
#
# quick-start.sh
#
# Vollständiges Onboarding-Tool für frisch geclonte Projekte:
# 1. Überprüft Docker-Installation
# 2. Erstellt .env aus .env.template
# 3. Startet Backend mit docker compose up
# 4. Bietet Dependency Management Optionen

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SETUP_DIR="${PROJECT_ROOT}/setup"
ACTIVE_BACKEND_APP_STATE_FILE=".active_backend_app"
ACTIVE_BACKEND_APP_ID="demo_app"
ACTIVE_BACKEND_ENV_FILE=".env.flutter.demo.mongodb"

# Source modules
source "${SETUP_DIR}/modules/docker_helpers.sh"
source "${SETUP_DIR}/modules/version_manager.sh"
source "${SETUP_DIR}/modules/menu_handlers.sh"

# Source Cognito setup script if available
if [ -f "${SETUP_DIR}/modules/cognito_setup.sh" ]; then
    # shellcheck disable=SC1091
    source "${SETUP_DIR}/modules/cognito_setup.sh"
fi

resolve_backend_env_file() {
    local app_id="$1"

    # First check for app-specific env file in app/apps/<app>/env/
    local app_specific_env="app/apps/${app_id}/env/.env.${app_id}"
    if [[ -f "${PROJECT_ROOT}/${app_specific_env}" ]]; then
        printf '%s\n' "${app_specific_env}"
        return
    fi

    # Fallback to root preset files for backward compatibility
    case "$app_id" in
        demo_app) echo ".env.flutter.demo.mongodb" ;;
        mongodb_template) echo ".env.flutter.mongodb_template.mongodb" ;;
        postgres_template) echo ".env.flutter.postgres_template.postgresql" ;;
        template_app) echo ".env.flutter.template.postgresql" ;;
        *) echo ".env" ;;
    esac
}

resolve_backend_dependency_project_root() {
    local app_id="$1"
    local app_root="${PROJECT_ROOT}/app/apps/${app_id}"

    if [ -f "${app_root}/pyproject.toml" ]; then
        printf '%s' "$app_root"
        return 0
    fi

    printf '%s' "${PROJECT_ROOT}"
}

# Resolve the deployment folder that owns the active app's local stack files.
resolve_backend_deployment_root() {
    local app_id="$1"
    local app_deployment_root="${PROJECT_ROOT}/app/apps/${app_id}/deployment"

    if [ -d "$app_deployment_root" ]; then
        printf '%s' "$app_deployment_root"
        return 0
    fi

    printf '%s' "${PROJECT_ROOT}/local-deployment"
}

# Resolve the optional compose manifest that lists a full stack of compose files.
resolve_backend_compose_manifest() {
    local app_id="$1"
    local db_mode="${2:-}"
    local mode_manifest_path=""
    local default_manifest_path="${PROJECT_ROOT}/app/apps/${app_id}/deployment/compose-files.txt"

    if [ -n "$db_mode" ]; then
        mode_manifest_path="${PROJECT_ROOT}/app/apps/${app_id}/deployment/compose-files.${db_mode}.txt"
        if [ -f "$mode_manifest_path" ]; then
            printf '%s' "$mode_manifest_path"
            return 0
        fi
    fi

    if [ "$db_mode" = "local" ] && [ -f "$default_manifest_path" ]; then
        printf '%s' "$default_manifest_path"
        return 0
    fi

    if [ -z "$db_mode" ] && [ -f "$default_manifest_path" ]; then
        printf '%s' "$default_manifest_path"
        return 0
    fi

    printf '%s' ""
}

get_compose_project_name() {
    local app_id="$1"
    local repo_name
    repo_name="$(basename "$PROJECT_ROOT")"
    repo_name="$(printf '%s' "$repo_name" | tr '[:upper:]' '[:lower:]' | tr '_' '-')"
    app_id="$(printf '%s' "$app_id" | tr '[:upper:]' '[:lower:]' | tr '_' '-')"
    printf '%s' "${repo_name}-${app_id}"
}

resolve_compose_file_path() {
    local compose_file="$1"
    case "$compose_file" in
        /*) printf '%s' "$compose_file" ;;
        *) printf '%s' "${PROJECT_ROOT}/${compose_file}" ;;
    esac
}

refresh_docker_compose_context() {
    local app_id="$1"
    local env_file="$2"
    local deployment_root
    local compose_manifest

    export ACTIVE_BACKEND_APP_ID="$app_id"
    export ACTIVE_BACKEND_ENV_FILE="$env_file"
    export DOCKER_COMPOSE_ENV_FILE
    export ACTIVE_BACKEND_APP_STATE_FILE
    export COMPOSE_PROJECT_NAME
    export APP_ENV_FILE
    export PDM_MANAGER_PROJECT_ROOT
    export ACTIVE_BACKEND_DEPLOYMENT_ROOT
    export ACTIVE_BACKEND_COMPOSE_MANIFEST
    export ACTIVE_BACKEND_COMPOSE_FILES
    export ACTIVE_BACKEND_PRIMARY_COMPOSE_FILE
    export ACTIVE_BACKEND_BROWSER_TARGETS

    DOCKER_COMPOSE_ENV_FILE="${PROJECT_ROOT}/${env_file}"
    COMPOSE_PROJECT_NAME="$(get_compose_project_name "$app_id")"
    APP_ENV_FILE="${PROJECT_ROOT}/${env_file}"
    PDM_MANAGER_PROJECT_ROOT="$(resolve_backend_dependency_project_root "$app_id")"
    deployment_root="$(resolve_backend_deployment_root "$app_id")"
    compose_manifest="$(resolve_backend_compose_manifest "$app_id")"
    ACTIVE_BACKEND_DEPLOYMENT_ROOT="$deployment_root"
    ACTIVE_BACKEND_COMPOSE_MANIFEST="$compose_manifest"
    ACTIVE_BACKEND_COMPOSE_FILES=""
    ACTIVE_BACKEND_PRIMARY_COMPOSE_FILE=""
    ACTIVE_BACKEND_BROWSER_TARGETS=""
}

# Return additional browser targets for the active local backend stack.
get_backend_browser_targets() {
    local env_file="$1"
    local db_type="$2"
    local db_mode="$3"

    if [ "$db_mode" != "local" ]; then
        return 0
    fi

    case "$db_type" in
        postgresql|postgres)
            local pgadmin_port
            pgadmin_port="$(read_env_variable "PGADMIN_PORT" "$env_file" "5050")"
            PGADMIN_EMAIL="$(read_env_variable "PGADMIN_EMAIL" "$env_file" "admin@local.dev")"
            PGADMIN_PASSWORD="$(read_env_variable "PGADMIN_PASSWORD" "$env_file" "admin")"
            export PGADMIN_EMAIL PGADMIN_PASSWORD
            printf '%s\n' "pgAdmin|http://localhost:${pgadmin_port}"
            ;;
        mongodb|mongo)
            local mongo_express_port
            mongo_express_port="$(read_env_variable "MONGO_EXPRESS_PORT" "$env_file" "8081")"
            MONGO_EXPRESS_USERNAME="$(read_env_variable "MONGO_EXPRESS_USERNAME" "$env_file" "admin")"
            MONGO_EXPRESS_PASSWORD="$(read_env_variable "MONGO_EXPRESS_PASSWORD" "$env_file" "admin")"
            export MONGO_EXPRESS_USERNAME MONGO_EXPRESS_PASSWORD
            printf '%s\n' "Mongo Express|http://localhost:${mongo_express_port}"
            ;;
    esac
}

# Resolve the compose stack for the active backend app.
resolve_backend_compose_files() {
    local app_id="$1"
    local db_type="$2"
    local db_mode="$3"
    local compose_manifest
    local resolved_files=""

    compose_manifest="$(resolve_backend_compose_manifest "$app_id" "$db_mode")"
    if [ -n "$compose_manifest" ] && [ -f "$compose_manifest" ]; then
        while IFS= read -r manifest_line || [ -n "$manifest_line" ]; do
            manifest_line="${manifest_line%$'\r'}"
            if [ -z "$manifest_line" ]; then
                continue
            fi

            case "$manifest_line" in
                \#*)
                    continue
                    ;;
            esac

            if [ -n "$resolved_files" ]; then
                resolved_files+=$'\n'
            fi
            resolved_files+="$(resolve_compose_file_path "$manifest_line")"
        done < "$compose_manifest"

        if [ -n "$resolved_files" ]; then
            printf '%s' "$resolved_files"
            return 0
        fi
    fi

    printf '%s' "$(resolve_compose_file_path "$(determine_compose_file "$db_type" "$db_mode")")"
}

# Return the first compose file in a possibly multi-file compose stack.
resolve_primary_compose_file() {
    local compose_files="$1"

    printf '%s\n' "$compose_files" | head -n 1
}

# Print a user-friendly list of compose files that belong to the active stack.
print_compose_file_stack() {
    local compose_files="$1"
    local compose_file

    while IFS= read -r compose_file || [ -n "$compose_file" ]; do
        compose_file="${compose_file%$'\r'}"
        [ -z "$compose_file" ] && continue
        echo "   Using: $compose_file"
    done <<< "$compose_files"
}

# Run docker compose with the full active compose stack.
run_backend_compose_stack() {
    local env_file="$1"
    local compose_files="$2"
    shift 2
    local compose_args=(docker compose --env-file "$env_file")
    local compose_file

    while IFS= read -r compose_file || [ -n "$compose_file" ]; do
        compose_file="${compose_file%$'\r'}"
        [ -z "$compose_file" ] && continue
        compose_args+=(-f "$compose_file")
    done <<< "$compose_files"

    compose_args+=("$@")
    "${compose_args[@]}"
}

get_backend_app_relative_path() {
    local app_id="$1"
    echo "app/apps/${app_id}"
}

set_active_backend_app() {
    local app_id="$1"
    ACTIVE_BACKEND_APP_ID="$app_id"
    ACTIVE_BACKEND_ENV_FILE="$(resolve_backend_env_file "$app_id")"
    printf '%s\n' "$app_id" > "$ACTIVE_BACKEND_APP_STATE_FILE"
    refresh_docker_compose_context "$ACTIVE_BACKEND_APP_ID" "$ACTIVE_BACKEND_ENV_FILE"
}

select_active_backend_app() {
    local current_app="$1"
    local default_choice="1"
    local builtin_apps=("demo_app" "template_app" "mongodb_template" "postgres_template")
    local app_ids=("${builtin_apps[@]}")
    local excluded_names=("__pycache__" ".git" ".vscode" "node_modules")
    local app_path
    local app_name
    local builtin_app
    local excluded_name
    local is_known_name

    for app_path in "${PROJECT_ROOT}"/app/apps/*; do
        [ -d "$app_path" ] || continue
        app_name="$(basename "$app_path")"
        is_known_name="false"

        for builtin_app in "${builtin_apps[@]}"; do
            if [ "$app_name" = "$builtin_app" ]; then
                is_known_name="true"
                break
            fi
        done

        for excluded_name in "${excluded_names[@]}"; do
            if [ "$app_name" = "$excluded_name" ]; then
                is_known_name="true"
                break
            fi
        done

        if [ "$is_known_name" = "false" ]; then
            app_ids+=("$app_name")
        fi
    done

    for i in "${!app_ids[@]}"; do
        if [ "${app_ids[$i]}" = "$current_app" ]; then
            default_choice="$((i + 1))"
            break
        fi
    done

    echo ""
    echo "========================================"
    echo "  Select Active Backend App"
    echo "========================================"
    echo ""
    for i in "${!app_ids[@]}"; do
        app_name="${app_ids[$i]}"
        if [ "$current_app" = "$app_name" ]; then
            echo "  $((i + 1))) $(get_backend_app_relative_path "$app_name") (current)"
        else
            echo "  $((i + 1))) $(get_backend_app_relative_path "$app_name")"
        fi
    done
    echo ""
    echo "  n/c) Create New Backend App"
    echo "  r/d) Remove a Backend App"
    echo ""

    local choice
    while true; do
        read -r -p "Select backend app (1-${#app_ids[@]}, n/c, r/d) [default: $(get_backend_app_relative_path "$current_app")] [$default_choice]: " choice
        choice="${choice:-$default_choice}"

        case "$choice" in
            n|c|r|d|"") break ;;
            *[!0-9]*) echo "Invalid option '$choice'. Please try again." ;;
            *)
                if [ "$choice" -ge 1 ] && [ "$choice" -le "${#app_ids[@]}" ]; then
                    break
                fi
                echo "Invalid option '$choice'. Please try again."
                ;;
        esac
    done

    case "$choice" in
        n|c)
            local new_app_id
            new_app_id=$(new_backend_app)
            if [[ -n "$new_app_id" ]]; then
                set_active_backend_app "$new_app_id"
            else
                select_active_backend_app "$current_app"
            fi
            ;;
        r|d)
            remove_backend_app
            select_active_backend_app "$current_app"
            ;;
        "")
            set_active_backend_app "$current_app"
            ;;
        *)
            set_active_backend_app "${app_ids[$((choice - 1))]}"
            ;;
    esac
}

new_backend_app() {
    echo ""
    echo "========================================"
    echo "  Create New Backend App"
    echo "========================================"
    echo ""

    read -r -p "Enter app display name (e.g., 'My New API'): " app_display_name
    if [[ -z "$app_display_name" ]]; then
        echo "App name is required. Cancelled." >&2
        return 1
    fi

    # Sanitize app name for folder (lowercase, replace spaces/whitespace with underscores)
    app_id=$(printf '%s' "$app_display_name" | tr '[:upper:]' '[:lower:]' | tr -s ' \t' '_' | tr -c 'a-z0-9_-' '_')
    # Trim leading/trailing underscores
    app_id=$(printf '%s' "$app_id" | sed 's/^_//;s/_$//')

    read -r -p "Enter app description: " app_description
    if [[ -z "$app_description" ]]; then
        app_description="Auto-generated backend app."
    fi

    echo ""
    echo "Select database type:"
    echo "  1) PostgreSQL"
    echo "  2) MongoDB"
    read -r -p "Database type (1-2) [default: 1]: " db_choice
    db_choice="${db_choice:-1}"

    case "$db_choice" in
        2) db_type="mongodb"; source_app="mongodb_template" ;;
        *) db_type="postgresql"; source_app="postgres_template" ;;
    esac
    compose_db_type="$db_type"
    if [[ "$db_type" == "postgresql" ]]; then
        compose_db_type="postgres"
    fi

    echo ""
    echo "Creating app: $app_id ($db_type)..."

    local app_dir="${PROJECT_ROOT}/app/apps/${app_id}"
    if [[ -d "$app_dir" ]]; then
        echo "App directory already exists: $app_dir" >&2
        return 1
    fi

    # Create directory structure
    mkdir -p "${app_dir}/routes" "${app_dir}/schemas" "${app_dir}/services" \
             "${app_dir}/config" "${app_dir}/env" "${app_dir}/deployment" \
             "${PROJECT_ROOT}/.docker/apps/${app_id}"

    # Copy pyproject.toml and pdm.lock from source template
    local source_dir="${PROJECT_ROOT}/app/apps/${source_app}"
    cp "${source_dir}/pyproject.toml" "${app_dir}/pyproject.toml"
    cp "${source_dir}/pdm.lock" "${app_dir}/pdm.lock"
    sed -i.bak -E \
        -e "s/^name[[:space:]]*=.*/name = \"${app_id}\"/" \
        -e 's/^version[[:space:]]*=.*/version = "0.1.0"/' \
        "${app_dir}/pyproject.toml"
    rm -f "${app_dir}/pyproject.toml.bak"

    # Create definition.py
    cat > "${app_dir}/definition.py" << EOF
"""
${app_display_name} backend definition.

This dynamically created app currently exposes only the shared core API
routers. App-specific routers can be added later by creating route modules and
registering them in route_registrations.
"""
from __future__ import annotations

from apps.contracts import BackendAppDefinition

BACKEND_APP_DEFINITION = BackendAppDefinition(
    app_id="${app_id}",
    display_name="${app_display_name}",
    backend_data_profile="${db_type}",
    route_registrations=(),
    exposes_sync_routes=False,
)
EOF

    # Create __init__.py
    echo '"""Backend app package created by quick-start."""' > "${app_dir}/__init__.py"

    # Create routes/__init__.py
    echo '"""Route modules for the generated backend app."""' > "${app_dir}/routes/__init__.py"

    # Create compose-files.txt
    cat > "${app_dir}/deployment/compose-files.txt" << EOF
local-deployment/base/api.compose.yml
local-deployment/base/redis.compose.yml
local-deployment/base/${compose_db_type}.compose.yml
EOF

    # Create compose.override.yml
    if [[ "$db_type" == "postgresql" ]]; then
        cat > "${app_dir}/deployment/compose.override.yml" << EOF
services:
  api:
    environment:
      APP_PROFILE: ${app_id}
      BACKEND_APP_ID: ${app_id}
    volumes:
      - ../../app/apps/${app_id}:/app/apps/${app_id}:ro
  postgres:
    volumes:
      - ../../.docker/apps/${app_id}/postgres-data:/var/lib/postgresql/data
EOF
    else
        cat > "${app_dir}/deployment/compose.override.yml" << EOF
services:
  api:
    environment:
      APP_PROFILE: ${app_id}
      BACKEND_APP_ID: ${app_id}
    volumes:
      - ../../app/apps/${app_id}:/app/apps/${app_id}:ro
  mongodb:
    volumes:
      - ../../.docker/apps/${app_id}/mongodb-data:/data/db
EOF
    fi

    # Create env file
    if [[ "$db_type" == "postgresql" ]]; then
        cat > "${app_dir}/env/.env.${app_id}" << EOF
# ${app_display_name} Local Environment
# =============================================================================
# This file contains local runtime settings for the ${app_id} backend app. It is
# ignored by git because it may contain credentials, local ports, and
# developer-specific service URLs.
#
# Release image metadata is stored in:
#   app/apps/${app_id}/pyproject.toml
# Do not add IMAGE_NAME or IMAGE_VERSION here.
# =============================================================================

# =============================================================================
# Python Runtime
# =============================================================================
PYTHON_VERSION=3.13

# =============================================================================
# Backend App Selection
# =============================================================================
APP_ENV_FILE=../app/apps/${app_id}/env/.env.${app_id}
APP_PROFILE=${app_id}
BACKEND_APP_ID=${app_id}
APP_NAME=${app_display_name}
APP_DESCRIPTION=${app_description}

# =============================================================================
# Database Configuration
# =============================================================================
# DB_MODE=local starts a Docker database; DB_MODE=external uses your own host.
DB_TYPE=${db_type}
DB_MODE=local

# Local Docker PostgreSQL connection.
# Use the Docker service name "postgres" from containers, not localhost.
DATABASE_URL=postgresql://postgres:postgres@postgres:5435/apidb
DB_HOST=postgres
DB_NAME=apidb
DB_USER=postgres
DB_PASSWORD=postgres
DB_PORT=5435

# =============================================================================
# API and Redis Ports
# =============================================================================
PORT=8086
REDIS_URL=redis://redis:6379
REDIS_PORT=6385

# =============================================================================
# PostgreSQL Admin UI
# =============================================================================
PGADMIN_PORT=5055
PGADMIN_EMAIL=admin@local.dev
PGADMIN_PASSWORD=admin

# =============================================================================
# Debug and Request Logging
# =============================================================================
# Keep body/header logging disabled unless you are actively debugging because
# request data can contain credentials or personal information.
DEBUG=true
ENABLE_HTTP_DEBUG_LOGGING=false
LOG_REQUEST_HEADERS=false
LOG_REQUEST_BODY=false
LOG_RESPONSE_HEADERS=false
LOG_RESPONSE_BODY=false
DB_LOCK_FAIL_CLOSED=true
EOF
    else
        cat > "${app_dir}/env/.env.${app_id}" << EOF
# ${app_display_name} Local Environment
# =============================================================================
# This file contains local runtime settings for the ${app_id} backend app. It is
# ignored by git because it may contain credentials, local ports, and
# developer-specific service URLs.
#
# Release image metadata is stored in:
#   app/apps/${app_id}/pyproject.toml
# Do not add IMAGE_NAME or IMAGE_VERSION here.
# =============================================================================

# =============================================================================
# Python Runtime
# =============================================================================
PYTHON_VERSION=3.13

# =============================================================================
# Backend App Selection
# =============================================================================
APP_ENV_FILE=../app/apps/${app_id}/env/.env.${app_id}
APP_PROFILE=${app_id}
BACKEND_APP_ID=${app_id}
APP_NAME=${app_display_name}
APP_DESCRIPTION=${app_description}

# =============================================================================
# Database Configuration
# =============================================================================
# DB_MODE=local starts a Docker database; DB_MODE=external uses your own host.
DB_TYPE=${db_type}
DB_MODE=local

# Local Docker MongoDB connection.
# Use the Docker service name "mongodb" from containers, not localhost.
MONGODB_URL=mongodb://mongo:mongo@mongodb:27017/?authSource=admin
MONGODB_DB_NAME=apidb
MONGODB_ROOT_USER=mongo
MONGODB_ROOT_PASSWORD=mongo
MONGODB_PORT=27021

# =============================================================================
# API and Redis Ports
# =============================================================================
PORT=8087
REDIS_URL=redis://redis:6379
REDIS_PORT=6386

# =============================================================================
# Mongo Express Admin UI
# =============================================================================
MONGO_EXPRESS_PORT=8088
MONGO_EXPRESS_USERNAME=admin
MONGO_EXPRESS_PASSWORD=admin

# =============================================================================
# Debug and Request Logging
# =============================================================================
# Keep body/header logging disabled unless you are actively debugging because
# request data can contain credentials or personal information.
DEBUG=true
ENABLE_HTTP_DEBUG_LOGGING=false
LOG_REQUEST_HEADERS=false
LOG_REQUEST_BODY=false
LOG_RESPONSE_HEADERS=false
LOG_RESPONSE_BODY=false
DB_LOCK_FAIL_CLOSED=true
EOF
    fi

    echo "Created: ${app_dir}"
    echo "App '${app_id}' created successfully!"
    echo ""

    printf '%s' "${app_id}"
}

remove_backend_app() {
    echo ""
    echo "========================================"
    echo "  Remove Backend App"
    echo "========================================"
    echo ""
    echo "WARNING: This will permanently delete the app and all its data."
    echo ""

    # Get list of custom apps (exclude built-in templates)
    local apps=()
    local app_dirs="${PROJECT_ROOT}/app/apps/*"
    for app_path in ${app_dirs}; do
        if [[ -d "$app_path" ]]; then
            local app_name=$(basename "$app_path")
            # Skip built-in templates
            if [[ "$app_name" != "demo_app" && "$app_name" != "template_app" && \
                  "$app_name" != "mongodb_template" && "$app_name" != "postgres_template" ]]; then
                apps+=("$app_name")
            fi
        fi
    done

    if [[ ${#apps[@]} -eq 0 ]]; then
        echo "No custom apps found to remove."
        return 1
    fi

    echo "Select app to remove:"
    local i=1
    for app in "${apps[@]}"; do
        echo "  ${i}) ${app}"
        ((i++))
    done
    echo "  c) Cancel"
    echo ""

    read -r -p "Select app to remove (1-${#apps[@]}, c): " choice
    if [[ "$choice" == "c" || -z "$choice" ]]; then
        echo "Cancelled."
        return 1
    fi

    local idx=$((choice - 1))
    if [[ $idx -lt 0 || $idx -ge ${#apps[@]} ]]; then
        echo "Invalid selection. Cancelled." >&2
        return 1
    fi

    local target_app="${apps[$idx]}"

    # Get display name from definition.py if possible
    local display_name="$target_app"
    if [[ -f "${PROJECT_ROOT}/app/apps/${target_app}/definition.py" ]]; then
        display_name=$(grep -E '(display_name|name)=' "${PROJECT_ROOT}/app/apps/${target_app}/definition.py" | head -1 | sed 's/.*="\([^"]*\)".*/\1/')
    fi

    echo ""
    echo "You are about to DELETE: ${display_name} (${target_app})"
    echo ""
    echo "To confirm, type: DELETE ${display_name}"
    echo ""
    read -r -p "Confirmation: " confirmation

    if [[ "$confirmation" != "DELETE ${display_name}" ]]; then
        echo "Confirmation failed. Deletion cancelled."
        return 1
    fi

    echo ""
    echo "Removing ${target_app}..."

    # Stop any running containers for this app
    local compose_file="${PROJECT_ROOT}/.docker/apps/${target_app}/compose.yml"
    if [[ -f "$compose_file" ]]; then
        docker compose -f "$compose_file" down --volumes 2>/dev/null || true
    fi

    # Remove app directory
    rm -rf "${PROJECT_ROOT}/app/apps/${target_app}"

    # Remove docker data directory
    rm -rf "${PROJECT_ROOT}/.docker/apps/${target_app}"

    echo "App '${target_app}' has been removed."
}

initialize_active_backend_app_selection() {
    local saved_app="demo_app"
    if [ -f "$ACTIVE_BACKEND_APP_STATE_FILE" ]; then
        saved_app="$(tr -d '\r\n' < "$ACTIVE_BACKEND_APP_STATE_FILE")"
    fi

    select_active_backend_app "$saved_app"
}

prompt_api_port() {
    local env_file="$1"
    prompt_env_port_value "$env_file" "PORT" "API port" "8000"
}

resolve_monitoring_ui_port_variable_name() {
    local db_type="$1"
    case "$db_type" in
        postgresql|postgres)
            printf '%s' "PGADMIN_PORT"
            ;;
        mongodb|mongo)
            printf '%s' "MONGO_EXPRESS_PORT"
            ;;
        *)
            printf '%s' ""
            ;;
    esac
}

resolve_monitoring_ui_port_prompt_label() {
    local db_type="$1"
    case "$db_type" in
        postgresql|postgres)
            printf '%s' "pgAdmin port"
            ;;
        mongodb|mongo)
            printf '%s' "Mongo Express port"
            ;;
        *)
            printf '%s' "Monitoring UI port"
            ;;
    esac
}

resolve_monitoring_ui_port_default_value() {
    local db_type="$1"
    case "$db_type" in
        postgresql|postgres)
            printf '%s' "5050"
            ;;
        mongodb|mongo)
            printf '%s' "8081"
            ;;
        *)
            printf '%s' ""
            ;;
    esac
}

resolve_database_port_variable_name() {
    local db_type="$1"
    case "$db_type" in
        neo4j|postgresql|postgres|mysql|sqlite)
            printf '%s' "DB_PORT"
            ;;
        mongodb|mongo)
            printf '%s' "MONGODB_PORT"
            ;;
        *)
            printf '%s' ""
            ;;
    esac
}

resolve_database_port_prompt_label() {
    local db_type="$1"
    case "$db_type" in
        neo4j)
            printf '%s' "Neo4j Bolt port"
            ;;
        postgresql|postgres)
            printf '%s' "PostgreSQL port"
            ;;
        mysql|sqlite)
            printf '%s' "Database port"
            ;;
        mongodb|mongo)
            printf '%s' "MongoDB port"
            ;;
        *)
            printf '%s' "Database port"
            ;;
    esac
}

resolve_database_port_default_value() {
    local db_type="$1"
    case "$db_type" in
        neo4j)
            printf '%s' "7687"
            ;;
        postgresql|postgres|mysql|sqlite)
            printf '%s' "5433"
            ;;
        mongodb|mongo)
            printf '%s' "27017"
            ;;
        *)
            printf '%s' "5433"
            ;;
    esac
}

prompt_env_port_value() {
    local env_file="$1"
    local variable_name="$2"
    local prompt_label="$3"
    local fallback_default="$4"
    local default_port
    default_port="$(read_env_variable "$variable_name" "$env_file" "$fallback_default")"

    while true; do
        local selected_port
        read -r -p "$prompt_label [$default_port]: " selected_port
        selected_port="${selected_port:-$default_port}"

        if [[ "$selected_port" =~ ^[0-9]+$ ]] && [ "$selected_port" -ge 1 ] && [ "$selected_port" -le 65535 ]; then
            update_env_variable "$variable_name" "$selected_port" "$env_file"
            printf '%s\n' "$selected_port"
            return 0
        fi

        echo "❌ Invalid port '$selected_port'. Please enter a number between 1 and 65535."
    done
}

sync_local_database_connection_settings() {
    local env_file="$1"
    local db_type="$2"
    local db_mode="$3"
    local selected_port="$4"
    local normalized_db_type
    normalized_db_type=$(printf '%s' "$db_type" | tr '[:upper:]' '[:lower:]')

    if [ "$db_mode" != "local" ] || [ -z "$selected_port" ]; then
        return 0
    fi

    case "$normalized_db_type" in
        postgresql|postgres)
            local db_host
            local db_name
            local db_user
            local db_password
            db_host="$(read_env_variable "DB_HOST" "$env_file" "postgres")"
            db_name="$(read_env_variable "DB_NAME" "$env_file" "apidb")"
            db_user="$(read_env_variable "DB_USER" "$env_file" "postgres")"
            db_password="$(read_env_variable "DB_PASSWORD" "$env_file" "postgres")"
            update_env_variable "DATABASE_URL" "postgresql://${db_user}:${db_password}@${db_host}:${selected_port}/${db_name}" "$env_file"
            ;;
        neo4j)
            local db_host
            db_host="$(read_env_variable "DB_HOST" "$env_file" "neo4j")"
            update_env_variable "NEO4J_URL" "bolt://${db_host}:${selected_port}" "$env_file"
            ;;
    esac
}

configure_service_ports() {
    local env_file="$1"
    local db_type="$2"
    local db_mode="$3"

    SELECTED_DATABASE_PORT_VARIABLE=""
    SELECTED_DATABASE_PORT=""

    if [ "$db_mode" = "local" ]; then
        local database_port_variable
        local database_port_label
        local database_port_default
        database_port_variable="$(resolve_database_port_variable_name "$db_type")"
        if [ -n "$database_port_variable" ]; then
            database_port_label="$(resolve_database_port_prompt_label "$db_type")"
            database_port_default="$(resolve_database_port_default_value "$db_type")"
            SELECTED_DATABASE_PORT_VARIABLE="$database_port_variable"
            SELECTED_DATABASE_PORT="$(prompt_env_port_value "$env_file" "$database_port_variable" "$database_port_label" "$database_port_default")"
            sync_local_database_connection_settings "$env_file" "$db_type" "$db_mode" "$SELECTED_DATABASE_PORT"
        fi
    fi

    SELECTED_REDIS_PORT="$(prompt_env_port_value "$env_file" "REDIS_PORT" "Redis port" "6379")"

    # Prompt for monitoring UI port (pgAdmin for PostgreSQL, Mongo Express for MongoDB)
    SELECTED_MONITORING_UI_PORT_VARIABLE=""
    SELECTED_MONITORING_UI_PORT=""
    if [ "$db_mode" = "local" ]; then
        local monitoring_port_variable
        local monitoring_port_label
        local monitoring_port_default
        monitoring_port_variable="$(resolve_monitoring_ui_port_variable_name "$db_type")"
        if [ -n "$monitoring_port_variable" ]; then
            monitoring_port_label="$(resolve_monitoring_ui_port_prompt_label "$db_type")"
            monitoring_port_default="$(resolve_monitoring_ui_port_default_value "$db_type")"
            SELECTED_MONITORING_UI_PORT_VARIABLE="$monitoring_port_variable"
            SELECTED_MONITORING_UI_PORT="$(prompt_env_port_value "$env_file" "$monitoring_port_variable" "$monitoring_port_label" "$monitoring_port_default")"
        fi
    fi
}

echo "🚀 FastAPI Redis API Test - Quick Start"
echo "======================================"

# Docker-Verfügbarkeit prüfen
# Docker-Verfügbarkeit prüfen
if ! check_docker_installation; then
    exit 1
fi
echo ""

# Check if initial setup is needed
if [ ! -f .setup-complete ]; then
    EXISTING_ENV_BEFORE_PROMPT=false
    if [ -f .env ]; then
        EXISTING_ENV_BEFORE_PROMPT=true
    fi
    echo "🚀 Erstmalige Einrichtung erkannt!"
    echo ""
    echo "Dies scheint das erste Mal zu sein, dass du dieses Projekt ausführst."
    echo "Möchtest du den interaktiven Setup-Assistenten ausführen?"
    echo ""
    echo "Der Setup-Assistent hilft dir bei der Konfiguration von:"
    echo "  • Docker Image-Name und Version"
    echo "  • Python-Version"
    echo "  • Datenbanktyp (PostgreSQL, Neo4j oder MongoDB)"
    echo "  • Datenbankmodus (lokal oder extern)"
    echo "  • API-Konfiguration"
    echo ""
    
    read -p "Setup-Assistenten jetzt ausführen? (Y/n): " runSetup
    if [[ ! "$runSetup" =~ ^[Nn]$ ]]; then
        echo ""
        echo "Starte Setup-Assistenten..."
        docker compose -f setup/docker-compose.setup.yml run --rm setup
        echo ""
        if declare -F run_cognito_setup >/dev/null; then
            run_cognito_setup
            echo ""
        fi
    else
        echo ""
        if [ "$EXISTING_ENV_BEFORE_PROMPT" = true ]; then
            echo "Setup-Assistent übersprungen. Bestehende .env gefunden, verwende aktuelle Werte."
        else
            echo "Setup-Assistent übersprungen. Erstelle einfache .env aus Vorlage..."
            if [ -f setup/.env.template ]; then
                cp setup/.env.template .env
                echo "✅ .env wurde aus Vorlage erstellt."
                echo "⚠️  Bitte bearbeite .env, um deine Umgebung zu konfigurieren, bevor du fortfährst."

                EDITOR_CMD="${EDITOR:-nano}"
                if ! command -v "$EDITOR_CMD" >/dev/null 2>&1; then
                    EDITOR_CMD="vi"
                fi
                read -p "Soll die .env jetzt in $EDITOR_CMD geöffnet werden? (Y/n): " open_env
                if [[ ! "$open_env" =~ ^[Nn]$ ]]; then
                    "$EDITOR_CMD" .env
                fi
            else
                echo "❌ setup/.env.template nicht gefunden!"
                exit 1
            fi
        fi

        if [ "$EXISTING_ENV_BEFORE_PROMPT" = true ]; then
            read -p "Es wurde bereits vor dem Prompt eine .env gefunden. .setup-complete jetzt neu erstellen und den Wizard überspringen? (y/N): " recreate_setup
            if [[ "$recreate_setup" =~ ^[Yy]$ ]]; then
                touch .setup-complete
                echo ".setup-complete aus bestehender .env neu erstellt."
            fi
        fi

        if declare -F run_cognito_setup >/dev/null; then
            run_cognito_setup
            echo ""
        fi
    fi
    echo ""
elif [ ! -f .env ]; then
    # Setup complete but .env missing - recreate from template
    echo "⚠️  .env Datei fehlt. Erstelle aus Vorlage..."
    if [ -f setup/.env.template ]; then
        cp setup/.env.template .env
        echo "✅ .env wurde aus Vorlage erstellt."
        echo "Bitte prüfe die Werte in .env bei Bedarf."
        if declare -F run_cognito_setup >/dev/null; then
            run_cognito_setup
            echo ""
        fi
    else
        echo "❌ setup/.env.template nicht gefunden!"
        exit 1
    fi
    echo ""
fi

initialize_active_backend_app_selection

echo "Active backend app: $(get_backend_app_relative_path "$ACTIVE_BACKEND_APP_ID")"
echo "Using env file: $ACTIVE_BACKEND_ENV_FILE"
echo "Using Docker Compose project: $COMPOSE_PROJECT_NAME"
echo ""

# Read API port from .env (default: 8000)
PORT=$(prompt_api_port "$ACTIVE_BACKEND_ENV_FILE")
echo "API will use port: $PORT"
echo ""

# Database configuration aus .env lesen
DB_TYPE=$(read_env_variable "DB_TYPE" "$ACTIVE_BACKEND_ENV_FILE" "neo4j")
DB_MODE=$(read_env_variable "DB_MODE" "$ACTIVE_BACKEND_ENV_FILE" "local")
DB_TYPE=$(printf '%s' "$DB_TYPE" | tr '[:upper:]' '[:lower:]')
DB_MODE=$(printf '%s' "$DB_MODE" | tr '[:upper:]' '[:lower:]')

configure_service_ports "$ACTIVE_BACKEND_ENV_FILE" "$DB_TYPE" "$DB_MODE"
if [ -n "$SELECTED_DATABASE_PORT" ]; then
    echo "$(resolve_database_port_prompt_label "$DB_TYPE") will use port: $SELECTED_DATABASE_PORT"
fi
echo "Redis will use port: $SELECTED_REDIS_PORT"
if [ -n "$SELECTED_MONITORING_UI_PORT" ]; then
    echo "$(resolve_monitoring_ui_port_prompt_label "$DB_TYPE") will use port: $SELECTED_MONITORING_UI_PORT"
fi
echo ""

# Docker Compose Datei basierend auf DB_TYPE und DB_MODE bestimmen
COMPOSE_FILES="$(resolve_backend_compose_files "$ACTIVE_BACKEND_APP_ID" "$DB_TYPE" "$DB_MODE")"
COMPOSE_FILE="$(resolve_primary_compose_file "$COMPOSE_FILES")"
export ACTIVE_BACKEND_COMPOSE_MANIFEST="$(resolve_backend_compose_manifest "$ACTIVE_BACKEND_APP_ID" "$DB_MODE")"
export ACTIVE_BACKEND_COMPOSE_FILES="$COMPOSE_FILES"
export ACTIVE_BACKEND_PRIMARY_COMPOSE_FILE="$COMPOSE_FILE"
export ACTIVE_BACKEND_BROWSER_TARGETS="$(get_backend_browser_targets "$ACTIVE_BACKEND_ENV_FILE" "$DB_TYPE" "$DB_MODE")"

if [ "$DB_MODE" = "external" ]; then
    echo "🔌 Detected external database mode"
    echo "   Database Type: $DB_TYPE"
    echo "   Will connect to external database (no local DB container)"
elif [ "$DB_TYPE" = "neo4j" ]; then
    echo "🗄️  Detected local Neo4j database"
    echo "   Will start Neo4j container"
elif [ "$DB_TYPE" = "postgresql" ] || [ "$DB_TYPE" = "postgres" ]; then
    echo "🗄️  Detected local $DB_TYPE database"
    echo "   Will start PostgreSQL container"
elif [ "$DB_TYPE" = "mysql" ] || [ "$DB_TYPE" = "sqlite" ]; then
    echo "⚠️  Detected DB_TYPE=$DB_TYPE (legacy compatibility mode)"
    echo "   Official stability matrix is: postgresql, neo4j, mongodb"
    echo "   Compose will use PostgreSQL profile for local development"
elif [ "$DB_TYPE" = "mongodb" ] || [ "$DB_TYPE" = "mongo" ]; then
    echo "🗄️  Detected local MongoDB database"
    echo "   Will start MongoDB container"
else
    echo "⚠️  Unknown DB_TYPE: $DB_TYPE, using default compose file"
fi

print_compose_file_stack "$COMPOSE_FILES"
echo ""

# Prüfen, ob dies der erste Setup-Lauf ist
if [ ! -f ".setup-complete" ]; then
    echo "🎯 First setup detected!"
    echo ""
    echo "Would you like to run optional diagnostics and dependency checks?"
    echo "  This can take 1-2 minutes but helps validate your configuration."
    echo "  You can skip this and dependencies will be installed during Docker build."
    echo ""
    read -p "Run diagnostics and dependency checks? (y/N): " run_diagnostics
    
    if [[ "$run_diagnostics" =~ ^[Yy]$ ]]; then
        echo ""
        echo "Running diagnostics and dependency configuration..."
        echo ""
        
        # Run diagnostics to validate Docker/build configuration first
        echo "🔍 Running Docker/Build diagnostics..."
        DIAGNOSTICS_SCRIPT="run-docker-build-diagnostics.sh"
        if [ -f "$DIAGNOSTICS_SCRIPT" ]; then
            echo "Collecting diagnostic information..."
            if bash "$DIAGNOSTICS_SCRIPT"; then
                echo "✅ Diagnostics completed successfully"
            else
                echo ""
                echo "❌ Diagnostics reported issues with your Docker or build configuration!"
                echo "Please address the reported problems before continuing."
                echo ""
                echo "🔧 Troubleshooting steps:"
                echo "1. Ensure Docker Desktop/daemon is running"
                echo "2. Verify .env values (especially PYTHON_VERSION and DB settings)"
                echo "3. Review missing files noted in the diagnostics output"
                echo "4. Re-run manually via: ./$DIAGNOSTICS_SCRIPT"
                echo ""
                echo "Subsequent steps may fail until the diagnostics succeed."
                read -p "Continue anyway? (y/N): " continue_anyway
                if [[ ! "$continue_anyway" =~ ^[Yy]$ ]]; then
                    echo "Setup aborted. Please fix the reported diagnostics issues first."
                    exit 1
                fi
                echo "⚠️  Continuing with potentially broken configuration..."
            fi
        else
            echo "⚠️  $DIAGNOSTICS_SCRIPT not found - skipping diagnostics"
        fi
        echo ""
        echo "📦 Starte Dependency Management für initiales Setup..."
        
        # Run dependency management in initial-run mode
        ./manage-python-project-dependencies.sh initial-run
    else
        echo ""
        echo "Skipping diagnostics and dependency checks."
        echo "Dependencies will be installed during Docker container build."
    fi
    
    # Markiere Setup als abgeschlossen
    touch .setup-complete
    
    echo ""
    echo "🎉 Erstes Setup abgeschlossen!"
    echo "🐳 Starte nun das Backend..."
    echo ""
    echo "========================================"
    echo "  API will be accessible at:"
    echo "  http://localhost:$PORT/docs"
    echo "========================================"
    echo ""
    echo "Press ENTER to open the API documentation in your browser..."
    echo "(The API may take a few seconds to start. Please refresh the page if needed.)"
    read -r
    
    # Open browser in incognito/private mode
    echo "Opening browser..."
    if command -v xdg-open &> /dev/null; then
        # Linux
        xdg-open "http://localhost:$PORT/docs" &
    elif command -v open &> /dev/null; then
        # macOS - try to open in incognito mode
        open -na "Google Chrome" --args --incognito "http://localhost:$PORT/docs" 2>/dev/null || \
        open -na "Safari" --args --private "http://localhost:$PORT/docs" 2>/dev/null || \
        open "http://localhost:$PORT/docs"
    else
        echo "Could not detect browser command. Please open manually: http://localhost:$PORT/docs"
    fi
    echo ""
    run_backend_compose_stack "${DOCKER_COMPOSE_ENV_FILE:-$ACTIVE_BACKEND_ENV_FILE}" "$COMPOSE_FILES" up --build --remove-orphans
else
    echo "🐳 Starte Backend mit Docker Compose..."
    echo "Backend wird verfügbar sein auf: http://localhost:$PORT"
    echo ""

    show_main_menu "$PORT" "$COMPOSE_FILE"
fi
