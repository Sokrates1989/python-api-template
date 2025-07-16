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
  if [ -f .env.template ]; then
    cp .env.template .env
    echo "✅ .env wurde aus .env.template erstellt."
    echo "📝 Bitte öffne die .env Datei und passe die Werte an:"
    echo "   nano .env"
    echo ""
    read -p "Drücke Enter, wenn du die .env Datei angepasst hast ..."
  else
    echo "❌ .env.template nicht gefunden! Bitte stelle sicher, dass die Vorlage existiert."
    exit 1
  fi
fi

# Port aus .env lesen (Standard: 8000)
PORT=$(grep "^PORT=" .env 2>/dev/null | cut -d'=' -f2 | tr -d ' "' || echo "8000")

echo ""
echo "🐳 Starte Backend mit Docker Compose..."
echo "Backend wird verfügbar sein auf: http://localhost:$PORT"
echo ""

# Auswahlmenü vor dem Start
echo "Wähle eine Option:"
echo "1) Backend direkt starten (docker compose up)"
echo "2) Zuerst Dependency Management öffnen"
echo "3) Beides - Dependency Management und dann Backend starten"
echo ""
read -p "Deine Wahl (1-3): " choice

case $choice in
  1)
    echo "🚀 Starte Backend direkt..."
    docker compose up --build
    ;;
  2)
    echo "📦 Öffne Dependency Management..."
    ./manage-python-project-dependencies.sh
    echo ""
    echo "ℹ️  Dependency Management beendet."
    echo "💡 Um das Backend zu starten, führe aus: docker compose up --build"
    ;;
  3)
    echo "📦 Öffne zuerst Dependency Management..."
    ./manage-python-project-dependencies.sh
    echo ""
    echo "🚀 Starte nun das Backend..."
    docker compose up --build
    ;;
  *)
    echo "❌ Ungültige Auswahl. Starte Backend direkt..."
    docker compose up --build
    ;;
esac

echo ""
echo "📋 Nützliche Befehle für später:"
echo "================================"
echo "• Backend starten:           docker compose up --build"
echo "• Backend stoppen:           Ctrl+C oder docker compose down"
echo "• Dependency Management:     ./manage-python-project-dependencies.sh"
echo "• Logs anzeigen:             docker compose logs -f"
echo "• Container neu bauen:       docker compose up --build"
echo ""
echo "📚 Weitere Infos im README.md" 