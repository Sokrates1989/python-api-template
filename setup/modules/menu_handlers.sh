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

handle_backend_start() {
    local port="$1"
    local compose_file="$2"
    
    echo "🚀 Starte Backend direkt..."
    
    # Determine if Neo4j is included
    local include_neo4j="false"
    if [[ "$compose_file" == *neo4j* ]]; then
        include_neo4j="true"
    fi
    
    # Open browsers automatically when services are ready
    open_browsers_delayed "$port" "$include_neo4j" 120
    
    docker compose --env-file .env -f "$compose_file" up --build
}

handle_dependency_management() {
    echo "📦 Öffne Dependency Management..."

    local core_menu_script="./tools/core-pdm-manager/menu/menu.sh"
    if [ -x "$core_menu_script" ]; then
        "$core_menu_script" --project-root .
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
    
    echo "📦 Öffne zuerst Dependency Management..."

    local core_menu_script="./tools/core-pdm-manager/menu/menu.sh"
    if [ -x "$core_menu_script" ]; then
        "$core_menu_script" --project-root . --action dependency-management
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
    if [[ "$compose_file" == *neo4j* ]]; then
        include_neo4j="true"
    fi
    
    # Open browsers automatically when services are ready
    open_browsers_delayed "$port" "$include_neo4j" 120
    
    docker compose --env-file .env -f "$compose_file" up
}

handle_environment_diagnostics() {
    echo "🔍 Starte Systemdiagnose für Docker-Setup..."

    local core_menu_script="./tools/core-pdm-manager/menu/menu.sh"
    if [ -x "$core_menu_script" ]; then
        "$core_menu_script" --project-root . --action diagnostics
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
    
    echo "🛑 Stoppe und entferne Container..."
    echo "   Using compose file: $compose_file"
    echo ""
    docker compose --env-file .env -f "$compose_file" down --remove-orphans
    echo ""
    echo "✅ Container gestoppt und entfernt"
}

handle_backend_start_no_cache() {
    local port="$1"
    local compose_file="$2"
    
    echo "🚀 Starte Backend direkt (mit --no-cache)..."
    
    # Determine if Neo4j is included
    local include_neo4j="false"
    if [[ "$compose_file" == *neo4j* ]]; then
        include_neo4j="true"
    fi
    
    # Open browsers automatically when services are ready
    open_browsers_delayed "$port" "$include_neo4j" 120
    
    docker compose --env-file .env -f "$compose_file" build --no-cache
    docker compose --env-file .env -f "$compose_file" up
}

open_browser_incognito() {
    local port="$1"
    local compose_file="$2"

    local api_url="http://localhost:$port/docs"
    local neo4j_url="http://localhost:7474"
    local urls=("$api_url")

    if [[ "$compose_file" == *neo4j* ]]; then
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

handle_build_production_image() {
    echo "🏗️  Building production Docker image..."
    echo ""
    if [ -f "build-image/docker-compose.build.yml" ]; then
        docker compose -f build-image/docker-compose.build.yml run --rm build-image
    else
        echo "❌ build-image/docker-compose.build.yml not found"
        echo "⚠️  Please ensure the build-image directory exists"
    fi
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
        echo ""
        echo "Build / CI/CD:"
        echo "  ${MENU_BUILD_PROD_IMAGE}) Production Docker Image bauen"
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
            handle_build_production_image
            summary_msg="Production Docker Image Build ausgeführt"
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
            update_image_version
            summary_msg="IMAGE_VERSION aktualisiert"
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
