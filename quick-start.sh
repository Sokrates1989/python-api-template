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

# 1. .env Datei erstellen
if [ -f .env ]; then
  echo "✅ .env Datei existiert bereits."
  echo "Bitte prüfe die Werte in .env bei Bedarf."
else
  if [ -f config/.env.template ]; then
    cp config/.env.template .env
    echo "✅ .env wurde aus .env.template erstellt."
    echo "📝 Bitte öffne die .env Datei und passe die Werte an:"
    echo "   nano .env"
    echo ""
    echo "🔐 Alternativ kannst du die .env auch für ein erfolgreiches Test-Setup kopieren von:"
    echo "   https://engaigegmbh.1password.com/app#/owzedt7yssm3ztfznims4metkm/AllItems/owzedt7yssm3ztfznims4metkm4dkrqgkllfr5f7ohu62orikvii"
    echo "   Falls diese Datei nicht freigegeben ist, bitte den Administrator um Freigabe zum Tresor: FASTAPI-REDIS-API-TEST"
    echo ""
    read -p "Drücke Enter, wenn du die .env Datei angepasst hast ..."
  else
    echo "❌ config/.env.template nicht gefunden! Bitte stelle sicher, dass die Vorlage existiert."
    exit 1
  fi
fi

# Port aus .env lesen (Standard: 8000)
PORT=$(grep "^PORT=" .env 2>/dev/null | cut -d'=' -f2 | tr -d ' "' || echo "8000")

# Database configuration aus .env lesen
DB_TYPE=$(grep "^DB_TYPE=" .env 2>/dev/null | cut -d'=' -f2 | tr -d ' "' || echo "neo4j")
DB_MODE=$(grep "^DB_MODE=" .env 2>/dev/null | cut -d'=' -f2 | tr -d ' "' || echo "local")

# Docker Compose Datei basierend auf DB_TYPE und DB_MODE bestimmen
if [ "$DB_MODE" = "external" ]; then
    COMPOSE_FILE="docker/docker-compose.yml"
    echo "🔌 Detected external database mode"
    echo "   Database Type: $DB_TYPE"
    echo "   Will connect to external database (no local DB container)"
elif [ "$DB_TYPE" = "neo4j" ]; then
    COMPOSE_FILE="docker/docker-compose.neo4j.yml"
    echo "🗄️  Detected local Neo4j database"
    echo "   Will start Neo4j container"
elif [ "$DB_TYPE" = "postgresql" ] || [ "$DB_TYPE" = "mysql" ]; then
    COMPOSE_FILE="docker/docker-compose.postgres.yml"
    echo "🗄️  Detected local $DB_TYPE database"
    echo "   Will start PostgreSQL container"
else
    COMPOSE_FILE="docker/docker-compose.yml"
    echo "⚠️  Unknown DB_TYPE: $DB_TYPE, using default docker/docker-compose.yml"
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
    echo "Backend wird verfügbar sein auf: http://localhost:$PORT"
    echo ""
    docker compose -f "$COMPOSE_FILE" up --build
else
    echo "🐳 Starte Backend mit Docker Compose..."
    echo "Backend wird verfügbar sein auf: http://localhost:$PORT"
    echo ""

    # Auswahlmenü für nachfolgende Starts
    echo "Wähle eine Option:"
    echo "1) Backend direkt starten (docker compose up)"
    echo "2) Zuerst Dependency Management öffnen"
    echo "3) Beides - Dependency Management und dann Backend starten"
    echo "4) Python Version Konfiguration testen"
    echo ""
    read -p "Deine Wahl (1-4): " choice

    case $choice in
      1)
        echo "🚀 Starte Backend direkt..."
        docker compose -f "$COMPOSE_FILE" up --build
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
        docker compose -f "$COMPOSE_FILE" up --build
        ;;
      4)
        echo "🔍 Testing Python version configuration..."
        if [ -f "python-dependency-management/scripts/test-python-version.sh" ]; then
            ./python-dependency-management/scripts/test-python-version.sh
        else
            echo "❌ python-dependency-management/scripts/test-python-version.sh not found"
        fi
        ;;
      *)
        echo "❌ Ungültige Auswahl. Starte Backend direkt..."
        docker compose up --build
        ;;
    esac
fi

echo ""
echo "📋 Nützliche Befehle für später:"
echo "================================"
echo "• Guided usage -> Backend starten/ dependency management menu: "    
echo "./quick-start.sh"
echo ""
echo "• Backend starten:           docker compose -f docker/docker-compose.yml up --build"
echo "• Backend stoppen:           Ctrl+C oder docker compose down"
echo "• Dependency Management:     ./python-dependency-management/scripts/manage-python-project-dependencies.sh"
echo "• Python Version Test:       ./python-dependency-management/scripts/test-python-version.sh"
echo "• Logs anzeigen:             docker compose logs -f"
echo "• Container neu bauen:       docker compose up --build"
echo ""
echo "📚 Weitere Infos im README.md" 