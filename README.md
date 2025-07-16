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

Das Script:
- ✅ Überprüft Docker-Installation
- ✅ Erstellt `.env` aus `.env.template` (falls nicht vorhanden)
- ✅ Bietet Auswahlmenü für Dependency-Management oder direkten Backend-Start
- ✅ Startet Backend automatisch mit `docker compose up --build`

### 3. API verwenden
- **Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **API-Endpunkte:** Port aus deiner `.env` (Standard: 8000)

## 🔧 Dependency Management

### Python-Pakete verwalten (optional)
```bash
./manage-python-project-dependencies.sh
```

Im interaktiven Container:
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
```

**Wichtige PDM-Befehle:**
- `pdm add <package>` - Paket hinzufügen
- `pdm remove <package>` - Paket entfernen
- `pdm install` - Alle Abhängigkeiten installieren
- `pdm update` - Alle Pakete aktualisieren
- `pdm list` - Installierte Pakete anzeigen
- `exit` - Container verlassen

## 📁 Projekt-Struktur

```
fastapi-redis-api-test/
├── api/                          # API-Module
│   ├── routes/                   # API-Routen
│   └── settings.py              # Konfiguration
├── backend/                      # Backend-Logic
├── python-dependency-management/ # Docker-Dependency-Tools
├── main.py                      # FastAPI-Hauptdatei
├── docker-compose.yml           # Docker-Services
├── Dockerfile                   # Backend-Container
├── pyproject.toml              # PDM-Konfiguration
├── .env.template               # Umgebungsvariablen-Vorlage
├── quick-start.sh              # Onboarding-Tool
└── manage-python-project-dependencies.sh # Dependency-Management
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
- `GET /` - Besucher-Zähler (Redis)
- `GET /cache/{key}` - Cache-Wert abrufen
- `POST /cache/{key}` - Cache-Wert setzen
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

1. **Projekt-Setup:** `./quick-start.sh`
2. **Pakete hinzufügen:** `./manage-python-project-dependencies.sh` → `pdm add <package>`
3. **Backend testen:** [http://localhost:8000/docs](http://localhost:8000/docs)
4. **Code ändern:** Automatisches Reload in Docker
5. **Deployment:** `docker compose up --build`

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

- **🚀 Einfaches Onboarding:** Ein Befehl startet alles
- **🔒 Konsistente Umgebung:** Alle Entwickler verwenden dieselbe Docker-Umgebung
- **⚡ Schnelle Abhängigkeitsverwaltung:** PDM mit uv-Backend
- **🛠️ Keine lokalen Tools:** Nur Docker erforderlich
- **🔄 Automatisches Reload:** Code-Änderungen werden sofort übernommen

## 📚 Weitere Informationen

- **Secrets:** Gespeichert in 1Password Vault `Fontanherzen`
- **Registry:** GitLab Container Registry
- **Deployment:** Azure Container Apps kompatibel

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
