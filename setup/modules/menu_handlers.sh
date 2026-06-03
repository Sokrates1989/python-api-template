#!/bin/bash
#
# menu_handlers.sh
#
# Module for handling menu actions in quick-start script

# Source browser helpers for auto-open functionality
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/browser_helpers.sh" ]; then
    source "$SCRIPT_DIR/browser_helpers.sh"
fi

# Source auth provider module
if [ -f "$SCRIPT_DIR/auth_provider.sh" ]; then
    source "$SCRIPT_DIR/auth_provider.sh"
fi

# Source Keycloak bootstrap utilities if available
if [ -f "$SCRIPT_DIR/bootstrap_utils.sh" ]; then
    source "$SCRIPT_DIR/bootstrap_utils.sh"
fi

# Resolve the dependency-management project root for the active backend app.
resolve_dependency_management_project_root() {
    local configured_root="${PDM_MANAGER_PROJECT_ROOT:-.}"

    case "$configured_root" in
        /*)
            printf '%s' "$configured_root"
            ;;
        *)
            printf '%s' "$(pwd)/${configured_root#./}"
            ;;
    esac
}

# Print the active app-specific paths so users know where to edit dependencies and stack files.
print_active_backend_context() {
    local compose_file="${1:-}"
    local app_id="${ACTIVE_BACKEND_APP_ID:-demo_app}"
    local dependency_root
    local app_root
    local deployment_root
    local compose_manifest
    local env_file

    dependency_root="$(resolve_dependency_management_project_root)"
    app_root="$(pwd)/app/apps/${app_id}"
    deployment_root="${ACTIVE_BACKEND_DEPLOYMENT_ROOT:-$(pwd)/local-deployment}"
    compose_manifest="${ACTIVE_BACKEND_COMPOSE_MANIFEST:-}"
    env_file="${DOCKER_COMPOSE_ENV_FILE:-${ACTIVE_BACKEND_ENV_FILE:-.env}}"

    echo ""
    echo "📍 Active backend app context"
    echo "   App id: ${app_id}"
    echo "   App folder: ${app_root}"
    echo "   Deployment root: ${deployment_root}"
    echo "   Dependency root: ${dependency_root}"
    echo "   Env file: ${env_file}"
    if [ -n "$compose_manifest" ]; then
        echo "   Compose manifest: ${compose_manifest}"
    fi
    if [ -n "$compose_file" ]; then
        echo "   Compose file: ${compose_file}"
    fi
    echo ""
}

# Return the active list of Docker Compose files exported by quick-start.
#
# Args:
#   fallback_compose_file: Single compose file path used when no compose stack is exported.
#
# Returns:
#   Writes newline-delimited compose file paths to stdout.
get_active_compose_files() {
    local fallback_compose_file="${1:-}"

    if [ -n "${ACTIVE_BACKEND_COMPOSE_FILES:-}" ]; then
        printf '%s\n' "${ACTIVE_BACKEND_COMPOSE_FILES}"
        return 0
    fi

    if [ -n "$fallback_compose_file" ]; then
        printf '%s\n' "$fallback_compose_file"
    fi
}

# Determine whether the active compose stack includes a Neo4j service.
#
# Args:
#   fallback_compose_file: Single compose file path used when no compose stack is exported.
#
# Returns:
#   0 when the active stack references Neo4j, 1 otherwise.
test_compose_includes_neo4j() {
    local fallback_compose_file="${1:-}"
    local active_compose_file

    while IFS= read -r active_compose_file || [ -n "$active_compose_file" ]; do
        active_compose_file="${active_compose_file%$'\r'}"
        [ -z "$active_compose_file" ] && continue
        if [[ "$active_compose_file" == *neo4j* ]]; then
            return 0
        fi
    done < <(get_active_compose_files "$fallback_compose_file")

    return 1
}

# Run Docker Compose against the full active compose stack.
#
# Args:
#   env_file: Env file path passed to Docker Compose.
#   fallback_compose_file: Single compose file path used when no compose stack is exported.
#   command arguments: Remaining docker compose arguments such as up or down.
#
# Returns:
#   Propagates the exit code from docker compose.
run_backend_compose_command() {
    local env_file="$1"
    local fallback_compose_file="$2"
    shift 2
    local compose_args=(docker compose --env-file "$env_file")
    local active_compose_file

    while IFS= read -r active_compose_file || [ -n "$active_compose_file" ]; do
        active_compose_file="${active_compose_file%$'\r'}"
        [ -z "$active_compose_file" ] && continue
        compose_args+=(-f "$active_compose_file")
    done < <(get_active_compose_files "$fallback_compose_file")

    compose_args+=("$@")
    "${compose_args[@]}"
}

# Open an app-specific file or folder in the local file browser.
#
# Args:
#   path: Absolute or relative file-system path to reveal.
#   description: Friendly label printed before opening the artifact.
#
# Returns:
#   0 when the artifact was opened or printed, 1 when the path is missing.
open_backend_artifact() {
    local target_path="$1"
    local description="$2"
    local resolved_path=""
    local browser_path=""

    if [ ! -e "$target_path" ]; then
        echo "⚠️  ${description} not found: ${target_path}"
        return 1
    fi

    if command -v realpath >/dev/null 2>&1; then
        resolved_path="$(realpath "$target_path")"
    else
        resolved_path="$(cd "$(dirname "$target_path")" && pwd)/$(basename "$target_path")"
    fi

    echo "📂 Opening ${description}: ${resolved_path}"

    if command -v explorer.exe >/dev/null 2>&1; then
        if command -v cygpath >/dev/null 2>&1; then
            browser_path="$(cygpath -w "$resolved_path")"
        else
            browser_path="$resolved_path"
        fi

        if [ -d "$resolved_path" ]; then
            explorer.exe "$browser_path" >/dev/null 2>&1 &
        else
            explorer.exe "/select,${browser_path}" >/dev/null 2>&1 &
        fi
        return 0
    fi

    if [ -d "$resolved_path" ]; then
        if command -v open >/dev/null 2>&1; then
            open "$resolved_path" >/dev/null 2>&1 &
            return 0
        fi

        if command -v xdg-open >/dev/null 2>&1; then
            xdg-open "$resolved_path" >/dev/null 2>&1 &
            return 0
        fi
    else
        if command -v open >/dev/null 2>&1; then
            open "$(dirname "$resolved_path")" >/dev/null 2>&1 &
            return 0
        fi

        if command -v xdg-open >/dev/null 2>&1; then
            xdg-open "$(dirname "$resolved_path")" >/dev/null 2>&1 &
            return 0
        fi
    fi

    echo "ℹ️  Open manually: ${resolved_path}"
    return 0
}

# Display a submenu with the most relevant app-specific folders and files.
#
# Args:
#   compose_file: Active Docker Compose file path selected by quick-start.
#
# Returns:
#   0 when the user returns to the main menu.
show_app_artifact_menu() {
    local compose_file="${1:-}"
    local project_root="$(pwd)"
    local app_id="${ACTIVE_BACKEND_APP_ID:-demo_app}"
    local app_root="${project_root}/app/apps/${app_id}"
    local deployment_root="${ACTIVE_BACKEND_DEPLOYMENT_ROOT:-${project_root}/local-deployment}"
    local compose_manifest_path="${ACTIVE_BACKEND_COMPOSE_MANIFEST:-${deployment_root}/compose-files.txt}"
    local compose_override_path="${deployment_root}/compose.override.yml"
    local routes_path="${app_root}/routes"
    local services_path="${app_root}/services"
    local schemas_path="${app_root}/schemas"
    local config_path="${app_root}/config"
    local dependency_root
    local pyproject_path
    local lockfile_path
    local env_file="${DOCKER_COMPOSE_ENV_FILE:-${ACTIVE_BACKEND_ENV_FILE:-.env}}"
    local env_path
    local choice

    dependency_root="$(resolve_dependency_management_project_root)"
    pyproject_path="${dependency_root}/pyproject.toml"
    lockfile_path="${dependency_root}/pdm.lock"

    if [[ "$env_file" = /* ]] || [[ "$env_file" =~ ^[A-Za-z]:[\\/].* ]]; then
        env_path="$env_file"
    else
        env_path="${project_root}/${env_file#./}"
    fi

    while true; do
        echo ""
        echo "============= App-Specific Files ============="
        print_active_backend_context "$deployment_root"
        echo "  1) API endpoints and functionality (routes)"
        echo "  2) Services / business logic"
        echo "  3) Schemas / data contracts"
        echo "  4) App config / metadata"
        echo "  5) Containers / Docker Compose deployment folder"
        echo "  6) Docker Compose manifest (compose-files.txt)"
        echo "  7) App Docker Compose override"
        echo "  8) Environment file"
        echo "  9) Dependency manifest (pyproject.toml)"
        echo "  10) Dependency lockfile (pdm.lock)"
        echo "  11) App root folder"
        echo "  0) Back to main menu"
        echo ""

        if [[ -r /dev/tty ]]; then
            read -r -p "Deine Wahl (0-11): " choice < /dev/tty
        else
            read -r -p "Deine Wahl (0-11): " choice
        fi

        case "$choice" in
            1)
                echo "ℹ️  Endpoint handlers live in ${routes_path}. Business logic usually lives in ${services_path}."
                open_backend_artifact "$routes_path" "API routes folder"
                ;;
            2)
                open_backend_artifact "$services_path" "services folder"
                ;;
            3)
                open_backend_artifact "$schemas_path" "schemas folder"
                ;;
            4)
                open_backend_artifact "$config_path" "app config folder"
                ;;
            5)
                open_backend_artifact "$deployment_root" "Docker Compose deployment folder"
                ;;
            6)
                open_backend_artifact "$compose_manifest_path" "Docker Compose manifest"
                ;;
            7)
                open_backend_artifact "$compose_override_path" "app Docker Compose override"
                ;;
            8)
                open_backend_artifact "$env_path" "environment file"
                ;;
            9)
                open_backend_artifact "$pyproject_path" "dependency manifest"
                ;;
            10)
                open_backend_artifact "$lockfile_path" "dependency lockfile"
                ;;
            11)
                open_backend_artifact "$app_root" "app root folder"
                ;;
            0)
                return 0
                ;;
            *)
                echo "⚠️  Invalid selection. Please choose a value between 0 and 11."
                ;;
        esac
    done
}

handle_backend_start() {
    local port="$1"
    local compose_file="$2"
    local env_file="${DOCKER_COMPOSE_ENV_FILE:-${ACTIVE_BACKEND_ENV_FILE:-.env}}"
    
    echo "🚀 Starte Backend direkt..."
    
    # Determine if Neo4j is included
    local include_neo4j="false"
    if test_compose_includes_neo4j "$compose_file"; then
        include_neo4j="true"
    fi
    
    # Open browsers automatically when services are ready
    open_browsers_delayed "$port" "$include_neo4j" 120
    
    run_backend_compose_command "$env_file" "$compose_file" up --build --remove-orphans
}

handle_dependency_management() {
    echo "📦 Öffne Dependency Management..."

    local dependency_root
    dependency_root="$(resolve_dependency_management_project_root)"

    print_active_backend_context

    local core_menu_script="./tools/core-pdm-manager/menu/menu.sh"
    if [ -x "$core_menu_script" ]; then
        "$core_menu_script" --project-root "$dependency_root"
    else
        echo "⚠️  core-pdm-manager menu not found. Falling back to root dependency wrapper."
        echo "    To fix: git submodule update --init --recursive"
        if [ -f "./manage-python-project-dependencies.sh" ]; then
            bash ./manage-python-project-dependencies.sh
        else
            echo "❌ ./manage-python-project-dependencies.sh not found"
        fi
    fi

    echo ""
    echo "ℹ️  Dependency Management beendet."
}

handle_dependency_and_backend() {
    local port="$1"
    local compose_file="$2"
    local env_file="${DOCKER_COMPOSE_ENV_FILE:-${ACTIVE_BACKEND_ENV_FILE:-.env}}"
    local dependency_root

    dependency_root="$(resolve_dependency_management_project_root)"
    
    echo "📦 Öffne zuerst Dependency Management..."

    print_active_backend_context "$compose_file"

    local core_menu_script="./tools/core-pdm-manager/menu/menu.sh"
    if [ -x "$core_menu_script" ]; then
        "$core_menu_script" --project-root "$dependency_root" --action dependency-management
    else
        echo "⚠️  core-pdm-manager menu not found. Falling back to root dependency wrapper."
        echo "    To fix: git submodule update --init --recursive"
        if [ -f "./manage-python-project-dependencies.sh" ]; then
            bash ./manage-python-project-dependencies.sh
        else
            echo "❌ ./manage-python-project-dependencies.sh not found"
        fi
    fi

    echo ""
    echo "🚀 Starte nun das Backend..."
    
    # Determine if Neo4j is included
    local include_neo4j="false"
    if test_compose_includes_neo4j "$compose_file"; then
        include_neo4j="true"
    fi
    
    # Open browsers automatically when services are ready
    open_browsers_delayed "$port" "$include_neo4j" 120
    
    run_backend_compose_command "$env_file" "$compose_file" up --remove-orphans
}

handle_environment_diagnostics() {
    echo "🔍 Starte Systemdiagnose für Docker-Setup..."

    local dependency_root
    dependency_root="$(resolve_dependency_management_project_root)"

    local core_menu_script="./tools/core-pdm-manager/menu/menu.sh"
    if [ -x "$core_menu_script" ]; then
        "$core_menu_script" --project-root "$dependency_root" --action diagnostics
    else
        local diagnostics_script="run-docker-build-diagnostics.sh"
        if [ -f "$diagnostics_script" ]; then
            echo "⚠️  core-pdm-manager diagnostics unavailable. Using root diagnostics wrapper."
            bash "$diagnostics_script"
        else
            echo "❌ ./$diagnostics_script not found"
        fi
    fi
}

# Run the Keycloak realm bootstrap.
#
# Returns:
#   0 when bootstrap succeeds, 1 otherwise.
handle_keycloak_bootstrap() {
    if declare -F run_keycloak_bootstrap >/dev/null; then
        run_keycloak_bootstrap
        return $?
    fi

    echo "⚠️  Keycloak Bootstrap Modul wurde nicht geladen."
    echo "    Bitte stelle sicher, dass setup/modules/bootstrap_utils.sh verfügbar ist."
    return 1
}

handle_rerun_setup_wizard() {
    echo "🔁 Re-running the interactive setup wizard"
    echo ""
    echo "To launch the wizard again, delete the .setup-complete file and restart quick-start."
    echo "The wizard automatically backs up your current .env before writing a new one."
    echo ""

    if [ ! -f .setup-complete ]; then
        echo ".setup-complete is already missing. The next quick-start run will start the wizard automatically."
    fi

    if [[ -r /dev/tty ]]; then
        read -r -p "Delete .setup-complete and restart ./quick-start.sh now? (y/N): " rerun_choice < /dev/tty
    else
        read -r -p "Delete .setup-complete and restart ./quick-start.sh now? (y/N): " rerun_choice
    fi
    if [[ ! "$rerun_choice" =~ ^[Yy]$ ]]; then
        echo "No changes were made. Remove .setup-complete manually and run ./quick-start.sh when you're ready."
        return 1
    fi

    if [ -f .setup-complete ]; then
        rm -f .setup-complete
        echo ".setup-complete removed."
    else
        echo ".setup-complete was not found, continuing."
    fi

    echo "Restarting ./quick-start.sh so you can walk through the wizard again..."
    ./quick-start.sh
    exit $?
}

handle_docker_compose_down() {
    local compose_file="$1"
    local env_file="${DOCKER_COMPOSE_ENV_FILE:-${ACTIVE_BACKEND_ENV_FILE:-.env}}"
    
    echo "🛑 Stoppe und entferne Container..."
    echo "   Using compose file: $compose_file"
    echo ""
    run_backend_compose_command "$env_file" "$compose_file" down --remove-orphans
    echo ""
    echo "✅ Container gestoppt und entfernt"
}

handle_backend_start_no_cache() {
    local port="$1"
    local compose_file="$2"
    local env_file="${DOCKER_COMPOSE_ENV_FILE:-${ACTIVE_BACKEND_ENV_FILE:-.env}}"
    
    echo "🚀 Starte Backend direkt (mit --no-cache)..."
    
    # Determine if Neo4j is included
    local include_neo4j="false"
    if test_compose_includes_neo4j "$compose_file"; then
        include_neo4j="true"
    fi
    
    # Open browsers automatically when services are ready
    open_browsers_delayed "$port" "$include_neo4j" 120
    
    run_backend_compose_command "$env_file" "$compose_file" build --no-cache
    run_backend_compose_command "$env_file" "$compose_file" up --remove-orphans
}

open_browser_incognito() {
    local port="$1"
    local compose_file="$2"

    local api_url="http://localhost:$port/docs"
    local neo4j_url="http://localhost:7474"
    local urls=("$api_url")

    if test_compose_includes_neo4j "$compose_file"; then
        urls+=("$neo4j_url")
        echo "Neo4j Browser will open at $neo4j_url using the same private window."
    fi

    echo "Opening browser..."

    if command -v microsoft-edge &> /dev/null; then
        microsoft-edge --inprivate "${urls[@]}" >/dev/null 2>&1 &
        return
    fi

    if command -v google-chrome &> /dev/null; then
        google-chrome --incognito "${urls[@]}" >/dev/null 2>&1 &
        return
    fi

    if command -v chromium-browser &> /dev/null; then
        chromium-browser --incognito "${urls[@]}" >/dev/null 2>&1 &
        return
    fi

    if command -v open &> /dev/null; then
        open -na "Google Chrome" --args --incognito "${urls[@]}" 2>/dev/null || \
        open -na "Safari" --args --private "${urls[@]}" 2>/dev/null || \
        open "${urls[0]}"
        return
    fi

    if command -v xdg-open &> /dev/null; then
        for url in "${urls[@]}"; do
            xdg-open "$url" &
        done
    else
        echo "Could not detect browser command. Please open manually: $api_url"
        if [[ "$compose_file" == *neo4j* ]]; then
            echo "Neo4j Browser: $neo4j_url"
        fi
    fi
}

# Legacy Docker Compose builder kept only as a reference during migration.
#
# Returns:
#   Runs the previous containerized build helper when called manually.
handle_build_production_image_legacy() {
    echo "🏗️  Building production Docker image..."
    echo ""
    if [ -f "build-image/docker-compose.build.yml" ]; then
        docker compose -f build-image/docker-compose.build.yml run --rm build-image
    else
        echo "❌ build-image/docker-compose.build.yml not found"
        echo "⚠️  Please ensure the build-image directory exists"
    fi
}

# Resolve the active backend app env file as an absolute path.
#
# Returns:
#   Writes the selected backend app env file path to stdout.
resolve_active_backend_env_path() {
    local env_file="${DOCKER_COMPOSE_ENV_FILE:-${ACTIVE_BACKEND_ENV_FILE:-.env}}"

    case "$env_file" in
        /*|[A-Za-z]:[\\/]*)
            printf '%s\n' "$env_file"
            ;;
        *)
            printf '%s\n' "$(pwd)/${env_file#./}"
            ;;
    esac
}

# Resolve the selected backend app pyproject.toml path.
#
# Args:
#   app_id: Selected backend app id.
#
# Returns:
#   Writes the app package manifest path to stdout.
resolve_active_backend_package_path() {
    local app_id="${1:-demo_app}"
    printf '%s\n' "$(pwd)/app/apps/${app_id}/pyproject.toml"
}

# Read the committed package version for a backend app.
#
# Args:
#   app_id: Selected backend app id.
#   default_value: Version returned when pyproject.toml has no project version.
#
# Returns:
#   Writes the app package version to stdout.
get_active_backend_package_version() {
    local app_id="$1"
    local default_value="${2:-0.1.0}"
    local package_path
    package_path="$(resolve_active_backend_package_path "$app_id")"

    if [ ! -f "$package_path" ]; then
        printf '%s\n' "$default_value"
        return 0
    fi

    awk -v default_value="$default_value" '
        /^\[project\][[:space:]]*$/ { in_project = 1; next }
        /^\[/ && in_project { in_project = 0 }
        in_project && /^[[:space:]]*version[[:space:]]*=/ {
            value = $0
            sub(/^[^=]*=[[:space:]]*/, "", value)
            gsub(/"/, "", value)
            gsub(/[[:space:]]/, "", value)
            print value
            found = 1
            exit
        }
        END {
            if (!found) {
                print default_value
            }
        }
    ' "$package_path"
}

# Write the committed package version for a backend app.
#
# Args:
#   app_id: Selected backend app id.
#   version: Semantic version to persist.
#
# Returns:
#   0 when the file is updated, non-zero otherwise.
set_active_backend_package_version() {
    local app_id="$1"
    local version="$2"
    local package_path
    local temp_file

    package_path="$(resolve_active_backend_package_path "$app_id")"
    if [ ! -f "$package_path" ]; then
        echo "[ERROR] Missing active backend package file: ${package_path}" >&2
        return 1
    fi

    temp_file="$(mktemp)" || return 1
    awk -v version="$version" '
        /^\[project\][[:space:]]*$/ {
            in_project = 1
            print
            next
        }
        /^\[/ && in_project && !updated {
            print "version = \"" version "\""
            updated = 1
            in_project = 0
        }
        in_project && /^[[:space:]]*version[[:space:]]*=/ {
            print "version = \"" version "\""
            updated = 1
            next
        }
        { print }
        END {
            if (!updated) {
                print "version = \"" version "\""
            }
        }
    ' "$package_path" > "$temp_file" && mv "$temp_file" "$package_path"
    echo "[OK] Updated ${package_path} to version ${version}"
}

# Normalize an app id into a Docker repository name segment.
#
# Args:
#   app_id: Selected backend app id.
#
# Returns:
#   Writes a repository-safe app name segment to stdout.
normalize_docker_app_name() {
    local app_id="${1:-app}"
    local normalized
    normalized=$(printf '%s' "$app_id" | tr '[:upper:]' '[:lower:]' | tr '_' '-' | sed -E 's/[^a-z0-9.-]+/-/g; s/^[.-]+//; s/[.-]+$//')

    if [ -z "$normalized" ]; then
        normalized="app"
    fi

    printf '%s\n' "$normalized"
}

# Build the canonical API image name for a backend app.
#
# Args:
#   app_id: Selected backend app id.
#
# Returns:
#   Writes the Docker image name without a tag to stdout.
get_active_backend_api_image_name() {
    local app_id="$1"
    local app_name
    app_name="$(normalize_docker_app_name "$app_id")"
    printf 'sokrates1989/python-api-%s\n' "$app_name"
}

# Prompt for the API image version using patch/minor/major/manual/current options.
#
# Args:
#   current_version: Current package version from the active app pyproject.toml.
#
# Returns:
#   Writes the selected semantic version to stdout.
read_api_image_version_selection() {
    local current_version="${1:-0.1.0}"
    local patch_version
    local minor_version
    local major_version
    local version_choice
    local manual_version

    patch_version="$(bump_semver "$current_version" "patch")"
    minor_version="$(bump_semver "$current_version" "minor")"
    major_version="$(bump_semver "$current_version" "major")"

    echo "" >&2
    echo "Version options:" >&2
    echo "  [1] Patch  (${current_version} -> ${patch_version})" >&2
    echo "  [2] Minor  (${current_version} -> ${minor_version})" >&2
    echo "  [3] Major  (${current_version} -> ${major_version})" >&2
    echo "  [4] Enter manually" >&2
    echo "  [5] Keep current (${current_version})" >&2
    echo "" >&2

    while true; do
        if [[ -r /dev/tty ]]; then
            read -r -p "Choose version option [1]: " version_choice < /dev/tty
        else
            read -r -p "Choose version option [1]: " version_choice
        fi
        version_choice="${version_choice:-1}"

        case "$version_choice" in
            1) printf '%s\n' "$patch_version"; return 0 ;;
            2) printf '%s\n' "$minor_version"; return 0 ;;
            3) printf '%s\n' "$major_version"; return 0 ;;
            4)
                if [[ -r /dev/tty ]]; then
                    read -r -p "Enter version tag: " manual_version < /dev/tty
                else
                    read -r -p "Enter version tag: " manual_version
                fi
                if [[ "$manual_version" =~ ^[vV]?[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
                    printf '%s\n' "$manual_version"
                    return 0
                fi
                echo "Invalid SemVer value. Use x.y.z, for example 1.2.3." >&2
                ;;
            5) printf '%s\n' "$current_version"; return 0 ;;
            *) echo "Invalid option. Choose 1-5." >&2 ;;
        esac
    done
}

# Build the selected backend app API Docker image.
#
# Args:
#   image_name: Docker image name without tag.
#   tag_version: Version tag to build.
#   app_id: Selected backend app id baked into the image.
#   python_version: Python base image version.
#   backend_data_profile: Database/backend profile.
#
# Returns:
#   0 when Docker build succeeds, non-zero otherwise.
build_backend_api_docker_image() {
    local image_name="$1"
    local tag_version="$2"
    local app_id="$3"
    local python_version="$4"
    local backend_data_profile="$5"
    local build_args=(
        --build-arg "PYTHON_VERSION=${python_version}"
        --build-arg "IMAGE_TAG=${tag_version}"
        --build-arg "BACKEND_APP_ID=${app_id}"
    )

    if [ -n "$backend_data_profile" ]; then
        build_args+=(--build-arg "BACKEND_DATA_PROFILE=${backend_data_profile}")
    fi

    echo ""
    echo "Building Docker image: ${image_name}:${tag_version}"
    echo ""
    echo "Building Docker image: ${image_name}:${tag_version}"
    echo "  Dockerfile: Dockerfile"
    echo "  Context: ."
    echo "  Platform: linux/amd64 (for Swarm compatibility)"
    echo "  Backend app: ${app_id}"
    echo ""

    if docker buildx version >/dev/null 2>&1; then
        echo "Using docker buildx for platform linux/amd64..."
        docker buildx build --platform "linux/amd64" -t "${image_name}:${tag_version}" -f "Dockerfile" "${build_args[@]}" "." --load
    else
        echo "docker buildx not found, falling back to docker build (host architecture)..."
        docker build -t "${image_name}:${tag_version}" -f "Dockerfile" "${build_args[@]}" "."
    fi
}

# Push a Docker image and retry once after docker login on auth failures.
#
# Args:
#   image_ref: Full Docker image reference including tag.
#
# Returns:
#   0 when push succeeds, non-zero otherwise.
push_docker_image_with_login_retry() {
    local image_ref="$1"
    local push_output
    local login_choice

    echo "Pushing image: ${image_ref}"
    if push_output="$(docker push "$image_ref" 2>&1)"; then
        printf '%s\n' "$push_output"
        return 0
    fi

    printf '%s\n' "$push_output"
    if printf '%s\n' "$push_output" | grep -qiE 'insufficient_scope|unauthorized|authentication required|no basic auth credentials|requested access'; then
        echo ""
        echo "Docker registry login may be required."
        if [[ -r /dev/tty ]]; then
            read -r -p "Run docker login and retry? (Y/n): " login_choice < /dev/tty
        else
            read -r -p "Run docker login and retry? (Y/n): " login_choice
        fi

        if [[ ! "$login_choice" =~ ^[Nn]$ ]]; then
            docker login || return 1
            echo ""
            echo "Retrying push: ${image_ref}"
            docker push "$image_ref"
            return $?
        fi
    fi

    return 1
}

# Build and push the selected backend app API image.
#
# Returns:
#   0 when build and push succeed, non-zero otherwise.
handle_build_production_image() {
    local app_id="${ACTIVE_BACKEND_APP_ID:-demo_app}"
    local env_file
    local image_name
    local current_version
    local tag_version
    local python_version
    local backend_data_profile

    env_file="$(resolve_active_backend_env_path)"
    image_name="$(get_active_backend_api_image_name "$app_id")"
    current_version="$(get_active_backend_package_version "$app_id" "0.1.0")"
    python_version="$(read_env_variable "PYTHON_VERSION" "$env_file" "3.13-slim")"
    backend_data_profile="$(read_env_variable "DB_TYPE" "$env_file" "")"

    echo ""
    echo "Docker Build & Push"
    echo "======================"
    echo ""
    echo "Images to build:"
    echo "  API:      ${image_name}"
    echo "  (auto-detected from active backend app: ${app_id})"

    tag_version="$(read_api_image_version_selection "$current_version")" || return 1

    if [ "$tag_version" != "$current_version" ]; then
        set_active_backend_package_version "$app_id" "$tag_version" || return 1
    else
        echo "[OK] Keeping app package version ${tag_version}"
    fi

    if ! build_backend_api_docker_image "$image_name" "$tag_version" "$app_id" "$python_version" "$backend_data_profile"; then
        echo "[ERROR] Docker build failed for ${image_name}:${tag_version}"
        return 1
    fi

    echo ""
    echo "[OK] Docker image built successfully: ${image_name}:${tag_version}"
    echo ""

    if ! push_docker_image_with_login_retry "${image_name}:${tag_version}"; then
        echo "[ERROR] Push failed for ${image_name}:${tag_version}"
        return 1
    fi
    echo "[OK] Image pushed successfully"

    echo "Tagging and pushing as 'latest'..."
    docker tag "${image_name}:${tag_version}" "${image_name}:latest" || return 1
    if ! push_docker_image_with_login_retry "${image_name}:latest"; then
        echo "[ERROR] Latest push failed for ${image_name}:latest"
        return 1
    fi
    echo "[OK] Latest tag pushed"
}

handle_cicd_setup() {
    echo "🚀 CI/CD Pipeline einrichten..."
    echo ""
    if [ -f "ci-cd/docker-compose.cicd-setup.yml" ]; then
        docker compose -f ci-cd/docker-compose.cicd-setup.yml run --rm cicd-setup
    else
        echo "❌ ci-cd/docker-compose.cicd-setup.yml not found"
        echo "⚠️  Please ensure the ci-cd directory exists"
    fi
}

# Display the interactive quick-start menu and dispatch actions.
#
# Args:
#   port: API port number.
#   compose_file: Docker Compose file path.
show_main_menu() {
    local port="$1"
    local compose_file="$2"

    local has_cognito=0
    if declare -F run_cognito_setup >/dev/null; then
        has_cognito=1
    fi

    local has_keycloak_bootstrap=0
    if declare -F run_keycloak_bootstrap >/dev/null; then
        has_keycloak_bootstrap=1
    fi

    local summary_msg=""
    local exit_code=0
    local choice

    while true; do
        local MENU_NEXT=1
        local MENU_START_BACKEND=$MENU_NEXT; MENU_NEXT=$((MENU_NEXT+1))
        local MENU_START_BACKEND_NO_CACHE=$MENU_NEXT; MENU_NEXT=$((MENU_NEXT+1))
        local MENU_START_DEP_AND_BACKEND=$MENU_NEXT; MENU_NEXT=$((MENU_NEXT+1))

        local MENU_MAINT_DOWN=$MENU_NEXT; MENU_NEXT=$((MENU_NEXT+1))
        local MENU_MAINT_DEP_MGMT=$MENU_NEXT; MENU_NEXT=$((MENU_NEXT+1))
        local MENU_MAINT_DIAGNOSTICS=$MENU_NEXT; MENU_NEXT=$((MENU_NEXT+1))
        local MENU_MAINT_APP_FILES=$MENU_NEXT; MENU_NEXT=$((MENU_NEXT+1))

        local MENU_BUILD_PROD_IMAGE=$MENU_NEXT; MENU_NEXT=$((MENU_NEXT+1))
        local MENU_BUILD_CICD_SETUP=$MENU_NEXT; MENU_NEXT=$((MENU_NEXT+1))
        local MENU_BUILD_BUMP_VERSION=$MENU_NEXT; MENU_NEXT=$((MENU_NEXT+1))

        local MENU_SETUP_AUTH=$MENU_NEXT; MENU_NEXT=$((MENU_NEXT+1))
        local MENU_SETUP_KEYCLOAK_BOOTSTRAP=""
        if [ "$has_keycloak_bootstrap" -eq 1 ]; then
            MENU_SETUP_KEYCLOAK_BOOTSTRAP=$MENU_NEXT; MENU_NEXT=$((MENU_NEXT+1))
        fi
        local MENU_SETUP_WIZARD=$MENU_NEXT; MENU_NEXT=$((MENU_NEXT+1))

        local MENU_EXIT=$MENU_NEXT
        local active_api_version
        active_api_version="$(get_active_backend_package_version "${ACTIVE_BACKEND_APP_ID:-demo_app}" "0.1.0")"

        echo ""
        echo "================ Main Menu ================"
        echo ""
        echo "Start:"
        echo "  ${MENU_START_BACKEND}) Backend direkt starten (docker compose up)"
        echo "  ${MENU_START_BACKEND_NO_CACHE}) Backend starten mit --no-cache (behebt Caching-Probleme)"
        echo "  ${MENU_START_DEP_AND_BACKEND}) Beides - Dependency Management und dann Backend starten"
        echo ""
        echo "Maintenance:"
        echo "  ${MENU_MAINT_DOWN}) Docker Compose Down (Container stoppen und entfernen)"
        echo "  ${MENU_MAINT_DEP_MGMT}) Nur Dependency Management öffnen"
        echo "  ${MENU_MAINT_DIAGNOSTICS}) Docker/Build Diagnose ausführen"
        echo "  ${MENU_MAINT_APP_FILES}) App-spezifische Dateien und Ordner öffnen"
        echo ""
        echo "Build / CI/CD:"
        echo "  ${MENU_BUILD_PROD_IMAGE}) Build & Push API Docker Image (v${active_api_version})"
        echo "  ${MENU_BUILD_CICD_SETUP}) CI/CD Pipeline einrichten"
        echo "  ${MENU_BUILD_BUMP_VERSION}) Bump release version for docker image"
        echo ""
        echo "Setup:"
        echo "  ${MENU_SETUP_AUTH}) Authentication Provider konfigurieren (Cognito/Keycloak/Dual)"
        if [ "$has_keycloak_bootstrap" -eq 1 ]; then
            echo "  ${MENU_SETUP_KEYCLOAK_BOOTSTRAP}) Keycloak Realm Bootstrap ausführen (Docker)"
        fi
        echo "  ${MENU_SETUP_WIZARD}) Setup-Assistent erneut ausführen"
        echo ""
        echo "  ${MENU_EXIT}) Skript beenden"
        echo ""

        if [[ -r /dev/tty ]]; then
            read -r -p "Deine Wahl (1-${MENU_EXIT}): " choice < /dev/tty
        else
            read -r -p "Deine Wahl (1-${MENU_EXIT}): " choice
        fi

        case $choice in
          ${MENU_START_BACKEND})
            handle_backend_start "$port" "$compose_file"
            summary_msg="Backend start ausgelöst (docker compose up)"
            break
            ;;
          ${MENU_START_BACKEND_NO_CACHE})
            handle_backend_start_no_cache "$port" "$compose_file"
            summary_msg="Backend start mit --no-cache ausgelöst"
            break
            ;;
          ${MENU_MAINT_DOWN})
            handle_docker_compose_down "$compose_file"
            summary_msg="Docker Compose Down ausgeführt"
            break
            ;;
          ${MENU_MAINT_DEP_MGMT})
            handle_dependency_management
            echo "💡 Um das Backend zu starten, führe aus: docker compose -f $compose_file up --build"
            summary_msg="Dependency Management ausgeführt"
            break
            ;;
          ${MENU_START_DEP_AND_BACKEND})
            handle_dependency_and_backend "$port" "$compose_file"
            summary_msg="Dependency Management und Backendstart ausgeführt"
            break
            ;;
          ${MENU_MAINT_DIAGNOSTICS})
            handle_environment_diagnostics
            summary_msg="Docker/Build Diagnose gestartet"
            break
            ;;
          ${MENU_MAINT_APP_FILES})
            show_app_artifact_menu "$compose_file"
            summary_msg="App-spezifisches Dateimenü geöffnet"
            break
            ;;
          ${MENU_SETUP_AUTH})
            if declare -F setup_auth_provider >/dev/null; then
                setup_auth_provider
                echo ""
                summary_msg="Authentication Provider Setup ausgeführt"
            else
                echo "⚠️  Auth Provider Modul wurde nicht geladen."
                echo "    Bitte stelle sicher, dass setup/modules/auth_provider.sh eingebunden ist."
                summary_msg="Auth Provider Setup konnte nicht ausgeführt werden"
                exit_code=1
            fi
            break
            ;;
          ${MENU_SETUP_KEYCLOAK_BOOTSTRAP})
            if handle_keycloak_bootstrap; then
                summary_msg="Keycloak Realm Bootstrap ausgeführt"
            else
                summary_msg="Keycloak Realm Bootstrap fehlgeschlagen"
                exit_code=1
            fi
            break
            ;;
          ${MENU_BUILD_PROD_IMAGE})
            if handle_build_production_image; then
                summary_msg="API Docker image build/push completed"
            else
                summary_msg="API Docker image build/push failed"
                exit_code=1
            fi
            break
            ;;
          ${MENU_BUILD_CICD_SETUP})
            handle_cicd_setup
            summary_msg="CI/CD Setup ausgeführt"
            break
            ;;
          ${MENU_SETUP_WIZARD})
            handle_rerun_setup_wizard
            summary_msg="Setup-Assistent erneut gestartet"
            break
            ;;
          ${MENU_BUILD_BUMP_VERSION})
            version_app_id="${ACTIVE_BACKEND_APP_ID:-demo_app}"
            current_app_version="$(get_active_backend_package_version "$version_app_id" "0.1.0")"
            new_app_version="$(read_api_image_version_selection "$current_app_version")" || exit_code=1
            if [ "$exit_code" -eq 0 ]; then
                set_active_backend_package_version "$version_app_id" "$new_app_version"
            fi
            summary_msg="Active app package version updated"
            break
            ;;
          ${MENU_EXIT})
            echo "👋 Skript wird beendet."
            exit 0
            ;;
          *)
            echo "❌ Ungültige Auswahl. Bitte erneut versuchen."
            echo ""
            continue
            ;;
        esac
    done

    echo ""
    if [ -n "$summary_msg" ]; then
        echo "✅ $summary_msg"
    fi
    echo "ℹ️  Quick-Start beendet. Für weitere Aktionen bitte erneut aufrufen."
    echo ""
    exit $exit_code
}
