# 🚀 FastAPI Redis API Test

Ein produktionsreifes FastAPI-Template mit Redis-Cache, Docker-basierter Entwicklung und modernem Python-Dependency-Management.

## 📚 Inhaltsverzeichnis

1. [📖 Übersicht](#-übersicht)
2. [📋 Voraussetzungen](#-voraussetzungen)
3. [🚀 Schnellstart](#-schnellstart)
4. [🔧 Dependency Management](#-dependency-management)
5. [📁 Projekt-Struktur](#-projekt-struktur)
6. [⚙️ Konfiguration](#-konfiguration)
7. [🧪 API-Tests](#-api-tests)
8. [🐳 Docker-Befehle](#-docker-befehle)
9. [🔄 Entwicklungsworkflow](#-entwicklungsworkflow)
10. [🏗️ Docker Image Build & Deploy](#-docker-image-build--deploy)
11. [✨ Vorteile](#-vorteile)
12. [📚 Weitere Informationen](#-weitere-informationen)
13. [⚠️ Deprecated: Alternative Installationsmethoden](#-deprecated-alternative-installationsmethoden)

## 📖 Übersicht

Dieses Template ist ein sauberes und erweiterbares FastAPI-Projekt mit:

- ✅ FastAPI-Framework mit automatischer Dokumentation
- ✅ Redis-Integration als Caching-Layer
- ✅ Docker & Docker Compose für reproduzierbare Umgebungen
- ✅ Umgebungsvariablen-basierte Konfiguration
- ✅ Optionale Integrationen für Neo4j und AWS
- ✅ Modernes Python-Dependency-Management mit PDM

## 📋 Voraussetzungen

**Einzige Voraussetzung:** Docker muss installiert und gestartet sein.

- [Docker Desktop herunterladen](https://www.docker.com/get-started)
- Docker Desktop starten

> **Wichtig:** Keine lokale Python-, Poetry- oder PDM-Installation erforderlich! Alles läuft in Docker-Containern.

## 🚀 Schnellstart

### 1. Projekt clonen
```bash
git clone https://gitlab.com/speedie3/fastapi-redis-api-test
cd fastapi-redis-api-test
```

### 2. Quick Start ausführen
```bash
./quick-start.sh
```

**Beim ersten Aufruf:**
- ✅ Überprüft Docker-Installation
- ✅ Erstellt `.env` aus `.env.template` (falls nicht vorhanden)
- ✅ Führt automatisch Dependency Management durch (`initial-run`)
- ✅ Aktualisiert PDM Lock-Dateien für Docker-Builds
- ✅ Startet Backend automatisch mit `docker compose up --build`
- ⚡ **Hinweis:** Beim ersten Start kann es etwas länger dauern, danach geht es meist deutlich schneller

**Bei nachfolgenden Aufrufen:**
- 🎛️ Bietet Auswahlmenü:
  1. Backend direkt starten
  2. Zuerst Dependency Management öffnen
  3. Dependency Management + Backend starten

### 3. .env Konfiguration
Falls die automatisch erstellte `.env` nicht ausreicht, kannst du:
- 📝 Die `.env` Datei manuell bearbeiten: `nano .env`
- 🔐 Oder die Konfiguration aus dem 1Password Vault kopieren (Link wird im Script angezeigt)
- 📧 Bei fehlender Berechtigung: Administrator um Zugang zum Tresor `FASTAPI-REDIS-API-TEST` bitten

### 4. API verwenden
- **Swagger UI:** [http://localhost:8081/docs](http://localhost:8081/docs)
- **API-Endpunkte:** Port aus deiner `.env` (Standard: 8000)

## 🔧 Dependency Management

### Automatisches Setup (beim ersten quick-start.sh)
Das initiale Dependency Management wird automatisch ausgeführt:
```bash
./manage-python-project-dependencies.sh initial-run
```
- 🔄 Aktualisiert PDM Lock-Dateien automatisch
- 🚀 Bereitet Docker-Builds vor
- 📦 Führt `pdm install` im Container aus
- ⚡ Nicht-interaktiv, läuft im Hintergrund

### Interaktives Dependency Management
Für manuelle Paket-Verwaltung:
```bash
./manage-python-project-dependencies.sh
```

**Im interaktiven Container:**
```bash
# Pakete hinzufügen
pdm add requests
pdm add pytest --dev

# Pakete entfernen
pdm remove requests

# Abhängigkeiten installieren
pdm install

# Lock-Datei aktualisieren
pdm lock

# Container verlassen
exit
```

**Wichtige PDM-Befehle:**
- `pdm add <package>` - Paket hinzufügen
- `pdm remove <package>` - Paket entfernen
- `pdm install` - Alle Abhängigkeiten installieren
- `pdm update` - Alle Pakete aktualisieren
- `pdm list` - Installierte Pakete anzeigen
- `pdm lock` - Lock-Datei aktualisieren
- `exit` - Container verlassen

### Modi im Überblick
| Modus | Befehl | Verwendung |
|-------|--------|------------|
| **Initial** | `./manage-python-project-dependencies.sh initial-run` | Automatisches Setup beim ersten Start |
| **Interaktiv** | `./manage-python-project-dependencies.sh` | Manuelle Paket-Verwaltung |

## 📁 Projekt-Struktur

```
fastapi-redis-api-test/
├── app/                          # Main application code
│   ├── api/                      # API-specific modules (routes, settings)
│   ├── backend/                  # Business logic
│   ├── mounted_data/             # Example data for volume mounts
│   └── main.py                   # FastAPI application entrypoint
├── tools/
│   └── core-pdm-manager/         # Wiederverwendbares Dependency-Management-Submodul
├── .env.template               # Environment variable template
├── .gitignore                  # Git ignore file
├── docker-compose.yml           # Docker services configuration
├── Dockerfile                   # Docker build file for the backend
├── pdm.lock                      # PDM lock file
├── pyproject.toml              # Project metadata and dependencies (PDM)
├── quick-start.sh              # Smart onboarding script
├── manage-python-project-dependencies.sh # Dependency-Management-Wrapper
└── run-docker-build-diagnostics.sh # Dependency-Diagnose-Wrapper
```

## ⚙️ Konfiguration

### Umgebungsvariablen (.env)

| Variable | Beschreibung | Standard |
|----------|-------------|----------|
| `PORT` | API-Port | `8000` |
| `REDIS_URL` | Redis-Verbindung | `redis://redis:6379` |
| `NEO4J_URL` | Neo4j-Verbindung (optional) | - |
| `DB_USER` | Datenbank-Benutzer | - |
| `DB_PASSWORD` | Datenbank-Passwort | - |

### Beispiel .env
```env
PORT=8000
REDIS_URL=redis://redis:6379
NEO4J_URL=bolt://localhost:7687
DB_USER=neo4j
DB_PASSWORD=secret-password
```

## 🧪 API-Tests

**Verfügbare Endpunkte:**
- `GET /` - Besucher-Zähler, wenn das gewählte App-Profil Redis benötigt
- `GET /cache/{key}` - Cache-Wert abrufen, wenn die App die Shared Route Group `cache` aktiviert
- `POST /cache/{key}` - Cache-Wert setzen, wenn die App die Shared Route Group `cache` aktiviert
- `GET /health` - Gesundheitscheck
- `GET /version` - Version anzeigen

## 🐳 Docker-Befehle

```bash
# Backend starten
docker compose up --build

# Backend stoppen
docker compose down

# Logs anzeigen
docker compose logs -f

# Container neu bauen
docker compose up --build --force-recreate

# Dependency Management
./manage-python-project-dependencies.sh
```

## 🔄 Entwicklungsworkflow

### Erstes Setup (einmalig)
1. **Projekt clonen:** `git clone ...`
2. **Quick Start:** `./quick-start.sh` (läuft automatisch alles durch)
3. **API testen:** [http://localhost:8081/docs](http://localhost:8081/docs)

### Tägliche Entwicklung
1. **Backend starten:** `./quick-start.sh` (mit Auswahlmenü)
2. **Code ändern:** Automatisches Reload in Docker
3. **Pakete hinzufügen:** `./manage-python-project-dependencies.sh` → `pdm add <package>`
4. **API testen:** [http://localhost:8081/docs](http://localhost:8081/docs)

### Deployment
```bash
docker compose up --build
```

### Reset (bei Problemen)
```bash
# Setup-Marker löschen für kompletten Neustart
rm .setup-complete
./quick-start.sh
```

## 🏗️ Docker Image Build & Deploy

```bash
# Image-Tag setzen
export IMAGE_TAG=0.1.0

# Docker Registry Login
docker login registry.gitlab.com -u gitlab+deploy-token-XXXXXX -p YOUR_DEPLOY_TOKEN

# Build & Push (Linux/amd64 für Azure)
docker buildx build --platform linux/amd64 --build-arg IMAGE_TAG=$IMAGE_TAG \
  -t registry.gitlab.com/speedie3/fastapi-redis-api-test:$IMAGE_TAG --push .
```

## ✨ Vorteile

- **🚀 Intelligentes Onboarding:** Automatisches Setup beim ersten Aufruf
- **🎯 Adaptive UX:** Unterschiedliche Menüs für erste vs. wiederholte Nutzung
- **🔒 Konsistente Umgebung:** Alle Entwickler verwenden dieselbe Docker-Umgebung
- **⚡ Schnelle Abhängigkeitsverwaltung:** PDM mit uv-Backend, automatische Lock-Updates
- **🛠️ Keine lokalen Tools:** Nur Docker erforderlich
- **🔄 Automatisches Reload:** Code-Änderungen werden sofort übernommen
- **🔐 Sichere Konfiguration:** 1Password-Integration für Produktions-Einstellungen
- **🧘 Stressfreies Setup:** Alles läuft automatisch, beim ersten Mal kann es etwas länger dauern

## 📚 Weitere Informationen

- **Secrets:** Gespeichert in 1Password Vault `FASTAPI-REDIS-API-TEST`
- **Registry:** GitLab Container Registry
- **Deployment:** Azure Container Apps kompatibel
- **Setup-Marker:** `.setup-complete` wird automatisch erstellt/gelöscht
- **Konfiguration:** 1Password-Link wird automatisch in `quick-start.sh` angezeigt

---

## ⚠️ Deprecated: Alternative Installationsmethoden

> **Hinweis:** Die folgenden Methoden sind veraltet und werden nicht mehr empfohlen. Verwende stattdessen den Docker-Workflow oben.

<details>
<summary>🔽 Lokale Poetry-Installation (Deprecated)</summary>

```bash
# Nicht empfohlen - nur für Legacy-Zwecke
curl -sSL https://install.python-poetry.org | python3 -
poetry install
poetry run uvicorn main:app --reload
```

</details>

<details>
<summary>🔽 Lokale PDM-Installation (Deprecated)</summary>

```bash
# Nicht empfohlen - nur für Legacy-Zwecke
pipx install pdm
pdm install
pdm run uvicorn main:app --reload
```

</details>

<details>
<summary>🔽 Pip-Installation (Deprecated)</summary>

```bash
# Nicht empfohlen - nur für Legacy-Zwecke
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

</details>

