# 🚀 FastAPI Redis API Test

A production-ready FastAPI template with Redis cache, Docker-based development, and modern Python dependency management.

## 📚 Table of Contents

1. [📖 Overview](#-overview)
2. [📋 Prerequisites](#-prerequisites)
3. [🚀 Quick Start](#-quick-start)
4. [🔧 Dependency Management](#-dependency-management)
5. [📁 Project Structure](#-project-structure)
6. [⚙️ Configuration](#-configuration)
7. [🧪 API Tests](#-api-tests)
8. [🐳 Docker Commands](#-docker-commands)
9. [🔄 Development Workflow](#-development-workflow)
10. [🏗️ Docker Image Build & Deploy](#-docker-image-build--deploy)
11. [✨ Benefits](#-benefits)
12. [📚 Additional Information](#-additional-information)
13. [⚠️ Deprecated: Alternative Installation Methods](#-deprecated-alternative-installation-methods)

## 📖 Overview

This template is a clean and extensible FastAPI project with:

- ✅ FastAPI framework with automatic documentation
- ✅ Redis integration as caching layer
- ✅ Docker & Docker Compose for reproducible environments
- ✅ Environment variable-based configuration
- ✅ Optional integrations for Neo4j and AWS
- ✅ Modern Python dependency management with PDM

## 📋 Prerequisites

**Only requirement:** Docker must be installed and running.

- [Download Docker Desktop](https://www.docker.com/get-started)
- Start Docker Desktop

> **Important:** No local Python, Poetry, or PDM installation required! Everything runs in Docker containers.

## 🚀 Quick Start

### 1. Clone the project
```bash
git clone https://gitlab.com/speedie3/fastapi-redis-api-test
cd fastapi-redis-api-test
```

### 2. Run Quick Start
```bash
./quick-start.sh
```

**On first run:**
- ✅ Checks Docker installation
- ✅ Creates `.env` from `.env.template` (if not present)
- ✅ Automatically runs dependency management (`initial-run`)
- ✅ Updates PDM lock files for Docker builds
- ✅ Starts backend automatically with `docker compose up --build`
- ⚡ **Note:** First start may take longer, subsequent runs are usually much faster

**On subsequent runs:**
- 🎛️ Provides selection menu:
  1. Start backend directly
  2. Open dependency management first
  3. Dependency management + start backend

### 3. .env Configuration
If the automatically created `.env` is not sufficient, you can:
- 📝 Manually edit the `.env` file: `nano .env`
- 🔐 Or copy configuration from the 1Password vault (link shown in script)
- 📧 If permission is missing: Ask administrator for access to vault `FASTAPI-REDIS-API-TEST`

### 4. Use the API
- **Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **API Endpoints:** Port from your `.env` (default: 8000)

## 🔧 Dependency Management

### Automatic Setup (on first quick-start.sh)
Initial dependency management is executed automatically:
```bash
./manage-python-project-dependencies.sh initial-run
```
- 🔄 Updates PDM lock files automatically
- 🚀 Prepares Docker builds
- 📦 Runs `pdm install` in container
- ⚡ Non-interactive, runs in background

### Interactive Dependency Management
For manual package management:
```bash
./manage-python-project-dependencies.sh
```

**In the interactive container:**
```bash
# Add packages
pdm add requests
pdm add pytest --dev

# Remove packages
pdm remove requests

# Install dependencies
pdm install

# Update lock file
pdm lock

# Exit container
exit
```

**Important PDM commands:**
- `pdm add <package>` - Add package
- `pdm remove <package>` - Remove package
- `pdm install` - Install all dependencies
- `pdm update` - Update all packages
- `pdm list` - Show installed packages
- `pdm lock` - Update lock file
- `exit` - Exit container

### Modes Overview
| Mode | Command | Usage |
|------|---------|-------|
| **Initial** | `./manage-python-project-dependencies.sh initial-run` | Automatic setup on first start |
| **Interactive** | `./manage-python-project-dependencies.sh` | Manual package management |

## 📁 Project Structure

```
fastapi-redis-api-test/
├── app/                          # Main application code
│   ├── api/                      # API-specific modules (routes, settings)
│   ├── backend/                  # Business logic
│   ├── mounted_data/             # Example data for volume mounts
│   └── main.py                   # FastAPI application entrypoint
├── python-dependency-management/ # Dockerized dependency management tools
├── .env.template               # Environment variable template
├── .gitignore                  # Git ignore file
├── docker-compose.yml           # Docker services configuration
├── Dockerfile                   # Docker build file for the backend
├── pdm.lock                      # PDM lock file
├── pyproject.toml              # Project metadata and dependencies (PDM)
├── quick-start.sh              # Smart onboarding script
└── manage-python-project-dependencies.sh # Dependency management script
```

## ⚙️ Configuration

### Environment Variables (.env)

| Variable | Description | Default |
|----------|-------------|---------|
| `PORT` | API Port | `8000` |
| `REDIS_URL` | Redis connection | `redis://redis:6379` |
| `NEO4J_URL` | Neo4j connection (optional) | - |
| `DB_USER` | Database user | - |
| `DB_PASSWORD` | Database password | - |

### Example .env
```env
PORT=8000
REDIS_URL=redis://redis:6379
NEO4J_URL=bolt://localhost:7687
DB_USER=neo4j
DB_PASSWORD=secret-password
```

## 🧪 API Tests

**Available endpoints:**
- `GET /` - Visitor counter (Redis)
- `GET /cache/{key}` - Get cache value
- `POST /cache/{key}` - Set cache value
- `GET /health` - Health check
- `GET /version` - Show version

## 🐳 Docker Commands

```bash
# Start backend
docker compose up --build

# Stop backend
docker compose down

# Show logs
docker compose logs -f

# Rebuild containers
docker compose up --build --force-recreate

# Dependency Management
./manage-python-project-dependencies.sh
```

## 🔄 Development Workflow

### First Setup (one-time)
1. **Clone project:** `git clone ...`
2. **Quick Start:** `./quick-start.sh` (runs everything automatically)
3. **Test API:** [http://localhost:8000/docs](http://localhost:8000/docs)

### Daily Development
1. **Start backend:** `./quick-start.sh` (with selection menu)
2. **Change code:** Automatic reload in Docker
3. **Add packages:** `./manage-python-project-dependencies.sh` → `pdm add <package>`
4. **Test API:** [http://localhost:8000/docs](http://localhost:8000/docs)

### Deployment
```bash
docker compose up --build
```

### Reset (if problems occur)
```bash
# Delete setup marker for complete restart
rm .setup-complete
./quick-start.sh
```

## 🏗️ Docker Image Build & Deploy

```bash
# Set image tag
export IMAGE_TAG=0.1.0

# Docker Registry Login
docker login registry.gitlab.com -u gitlab+deploy-token-XXXXXX -p YOUR_DEPLOY_TOKEN

# Build & Push (Linux/amd64 for Azure)
docker buildx build --platform linux/amd64 --build-arg IMAGE_TAG=$IMAGE_TAG \
  -t registry.gitlab.com/speedie3/fastapi-redis-api-test:$IMAGE_TAG --push .
```

## ✨ Benefits

- **🚀 Smart Onboarding:** Automatic setup on first run
- **🎯 Adaptive UX:** Different menus for first vs. repeated usage
- **🔒 Consistent Environment:** All developers use the same Docker environment
- **⚡ Fast Dependency Management:** PDM with uv backend, automatic lock updates
- **🛠️ No Local Tools:** Only Docker required
- **🔄 Automatic Reload:** Code changes are immediately applied
- **🔐 Secure Configuration:** 1Password integration for production settings
- **🧘 Stress-free Setup:** Everything runs automatically, first time may take longer

## 📚 Additional Information

- **Secrets:** Stored in 1Password Vault `FASTAPI-REDIS-API-TEST`
- **Registry:** GitLab Container Registry
- **Deployment:** Azure Container Apps compatible
- **Setup Marker:** `.setup-complete` is automatically created/deleted
- **Configuration:** 1Password link is automatically shown in `quick-start.sh`

---

## ⚠️ Deprecated: Alternative Installation Methods

> **Note:** The following methods are deprecated and no longer recommended. Use the Docker workflow above instead.

<details>
<summary>🔽 Local Poetry Installation (Deprecated)</summary>

```bash
# Not recommended - only for legacy purposes
curl -sSL https://install.python-poetry.org | python3 -
poetry install
poetry run uvicorn main:app --reload
```

</details>

<details>
<summary>🔽 Local PDM Installation (Deprecated)</summary>

```bash
# Not recommended - only for legacy purposes
pipx install pdm
pdm install
pdm run uvicorn main:app --reload
```

</details>

<details>
<summary>🔽 Pip Installation (Deprecated)</summary>

```bash
# Not recommended - only for legacy purposes
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

</details>
