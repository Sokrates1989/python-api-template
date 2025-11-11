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

echo "🚀 FastAPI Redis API Test - Quick Start"
echo "======================================"

# Docker-Verfügbarkeit prüfen
echo "🔍 Überprüfe Docker-Installation..."
if ! command -v docker &> /dev/null; then
    echo "❌ Docker ist nicht installiert!"
    echo "📥 Bitte installiere Docker von: https://www.docker.com/get-started"
    exit 1
fi

# Docker-Daemon prüfen
if ! docker info &> /dev/null; then
    echo "❌ Docker-Daemon läuft nicht!"
    echo "🔄 Bitte starte Docker Desktop oder den Docker-Service"
    exit 1
fi

# Docker Compose prüfen
if ! docker compose version &> /dev/null; then
    echo "❌ Docker Compose ist nicht verfügbar!"
    echo "📥 Bitte installiere eine aktuelle Docker-Version mit Compose-Plugin"
    exit 1
fi

echo "✅ Docker ist installiert und läuft"
echo ""

# Check if initial setup is needed
if [ ! -f .setup-complete ]; then
    echo "🚀 Erstmalige Einrichtung erkannt!"
    echo ""
    echo "Dies scheint das erste Mal zu sein, dass du dieses Projekt ausführst."
    echo "Möchtest du den interaktiven Setup-Assistenten ausführen?"
    echo ""
    echo "Der Setup-Assistent hilft dir bei der Konfiguration von:"
    echo "  • Docker Image-Name und Version"
    echo "  • Python-Version"
    echo "  • Datenbanktyp (PostgreSQL oder Neo4j)"
    echo "  • Datenbankmodus (lokal oder extern)"
    echo "  • API-Konfiguration"
    echo ""
    
    read -p "Setup-Assistenten jetzt ausführen? (Y/n): " runSetup
    if [[ ! "$runSetup" =~ ^[Nn]$ ]]; then
        echo ""
        echo "Starte Setup-Assistenten..."
        docker compose -f setup/docker-compose.setup.yml run --rm setup
        echo ""
    else
        echo ""
        echo "Setup-Assistent übersprungen. Erstelle einfache .env aus Vorlage..."
        if [ -f setup/.env.template ]; then
            cp setup/.env.template .env
            echo "✅ .env wurde aus Vorlage erstellt."
            echo "⚠️  Bitte bearbeite .env, um deine Umgebung zu konfigurieren, bevor du fortfährst."
        else
            echo "❌ setup/.env.template nicht gefunden!"
            exit 1
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
    else
        echo "❌ setup/.env.template nicht gefunden!"
        exit 1
    fi
    echo ""
fi

# Port aus .env lesen (Standard: 8000)
PORT=$(grep "^PORT=" .env 2>/dev/null | cut -d'=' -f2 | tr -d ' "' || echo "8000")

# Database configuration aus .env lesen
DB_TYPE=$(grep "^DB_TYPE=" .env 2>/dev/null | cut -d'=' -f2 | tr -d ' "' || echo "neo4j")
DB_MODE=$(grep "^DB_MODE=" .env 2>/dev/null | cut -d'=' -f2 | tr -d ' "' || echo "local")

# Docker Compose Datei basierend auf DB_TYPE und DB_MODE bestimmen
if [ "$DB_MODE" = "external" ]; then
    COMPOSE_FILE="local-deployment/docker-compose.yml"
    echo "🔌 Detected external database mode"
    echo "   Database Type: $DB_TYPE"
    echo "   Will connect to external database (no local DB container)"
elif [ "$DB_TYPE" = "neo4j" ]; then
    COMPOSE_FILE="local-deployment/docker-compose.neo4j.yml"
    echo "🗄️  Detected local Neo4j database"
    echo "   Will start Neo4j container"
elif [ "$DB_TYPE" = "postgresql" ] || [ "$DB_TYPE" = "mysql" ]; then
    COMPOSE_FILE="local-deployment/docker-compose.postgres.yml"
    echo "🗄️  Detected local $DB_TYPE database"
    echo "   Will start PostgreSQL container"
else
    COMPOSE_FILE="local-deployment/docker-compose.yml"
    echo "⚠️  Unknown DB_TYPE: $DB_TYPE, using default local-deployment/docker-compose.yml"
fi

echo "   Using: $COMPOSE_FILE"
echo ""

# Prüfen, ob dies der erste Setup-Lauf ist
if [ ! -f ".setup-complete" ]; then
    echo "🎯 Erstes Setup erkannt - Führe automatische Dependency-Konfiguration durch..."
    echo "⚡ Beim ersten Start kann es etwas länger dauern, danach geht es meist deutlich schneller."
    echo ""
    
    # Test Python version configuration first
    echo "🔍 Testing Python version configuration..."
    if [ -f "python-dependency-management/scripts/test-python-version.sh" ]; then
        echo "Running Python version tests..."
        if ./python-dependency-management/scripts/test-python-version.sh; then
            echo "✅ Python version configuration test passed"
        else
            echo ""
            echo "❌ Python version configuration test failed!"
            echo "This indicates a problem with your .env file or Docker setup."
            echo ""
            echo "🔧 Troubleshooting steps:"
            echo "1. Check if .env file exists and contains PYTHON_VERSION=3.13"
            echo "2. Ensure Docker is running: docker --version"
            echo "3. Verify .env file format: cat .env"
            echo "4. Try manual test: ./python-dependency-management/scripts/test-python-version.sh (forces fresh build with latest Python base)"
            echo ""
            echo "The following steps may fail if Python version is not configured correctly."
            read -p "Continue anyway? (y/N): " continue_anyway
            if [[ ! "$continue_anyway" =~ ^[Yy]$ ]]; then
                echo "Setup aborted. Please fix the Python version configuration first."
                exit 1
            fi
            echo "⚠️  Continuing with potentially broken configuration..."
        fi
    else
        echo "⚠️  python-dependency-management/scripts/test-python-version.sh not found - skipping version test"
    fi
    echo ""
    echo "📦 Starte Dependency Management für initiales Setup..."
    
    # Führe das Dependency Management im initial-run Modus aus
    ./python-dependency-management/scripts/manage-python-project-dependencies.sh initial-run
    
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
    docker compose --env-file .env -f "$COMPOSE_FILE" up --build
else
    echo "🐳 Starte Backend mit Docker Compose..."
    echo "Backend wird verfügbar sein auf: http://localhost:$PORT"
    echo ""

    # Auswahlmenü für nachfolgende Starts
    echo "Wähle eine Option:"
    echo "1) Backend direkt starten (docker compose up)"
    echo "2) Nur Dependency Management öffnen"
    echo "3) Beides - Dependency Management und dann Backend starten"
    echo "4) Python Version Konfiguration testen"
    echo "5) Production Docker Image bauen"
    echo "6) CI/CD Pipeline einrichten"
    echo ""
    read -p "Deine Wahl (1-6): " choice

    case $choice in
      1)
        echo "🚀 Starte Backend direkt..."
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
            xdg-open "http://localhost:$PORT/docs" &
        elif command -v open &> /dev/null; then
            open -na "Google Chrome" --args --incognito "http://localhost:$PORT/docs" 2>/dev/null || \
            open -na "Safari" --args --private "http://localhost:$PORT/docs" 2>/dev/null || \
            open "http://localhost:$PORT/docs"
        else
            echo "Could not detect browser command. Please open manually: http://localhost:$PORT/docs"
        fi
        
        echo ""
        docker compose --env-file .env -f "$COMPOSE_FILE" up --build
        ;;
      2)
        echo "📦 Öffne Dependency Management..."
        ./python-dependency-management/scripts/manage-python-project-dependencies.sh
        echo ""
        echo "ℹ️  Dependency Management beendet."
        echo "💡 Um das Backend zu starten, führe aus: docker compose -f $COMPOSE_FILE up --build"
        ;;
      3)
        echo "📦 Öffne zuerst Dependency Management..."
        ./python-dependency-management/scripts/manage-python-project-dependencies.sh
        echo ""
        echo "🚀 Starte nun das Backend..."
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
            xdg-open "http://localhost:$PORT/docs" &
        elif command -v open &> /dev/null; then
            open -na "Google Chrome" --args --incognito "http://localhost:$PORT/docs" 2>/dev/null || \
            open -na "Safari" --args --private "http://localhost:$PORT/docs" 2>/dev/null || \
            open "http://localhost:$PORT/docs"
        else
            echo "Could not detect browser command. Please open manually: http://localhost:$PORT/docs"
        fi
        
        echo ""
        docker compose --env-file .env -f "$COMPOSE_FILE" up --build
        ;;
      4)
        echo "🔍 Testing Python version configuration..."
        if [ -f "python-dependency-management/scripts/test-python-version.sh" ]; then
            ./python-dependency-management/scripts/test-python-version.sh
        else
            echo "❌ python-dependency-management/scripts/test-python-version.sh not found"
        fi
        ;;
      5)
        echo "🏗️  Building production Docker image..."
        echo ""
        if [ -f "build-image/docker-compose.build.yml" ]; then
            docker compose -f build-image/docker-compose.build.yml run --rm build-image
        else
            echo "❌ build-image/docker-compose.build.yml not found"
            echo "⚠️  Please ensure the build-image directory exists"
        fi
        ;;
      6)
        echo "🚀 CI/CD Pipeline einrichten..."
        echo ""
        if [ -f "ci-cd/docker-compose.cicd-setup.yml" ]; then
            docker compose -f ci-cd/docker-compose.cicd-setup.yml run --rm cicd-setup
        else
            echo "❌ ci-cd/docker-compose.cicd-setup.yml not found"
            echo "⚠️  Please ensure the ci-cd directory exists"
        fi
        ;;
      *)
        echo "❌ Ungültige Auswahl. Starte Backend direkt..."
        docker compose --env-file .env up --build
        ;;
    esac
fi