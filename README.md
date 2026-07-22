# 🚀 FastAPI Python API Template

A production-ready FastAPI template with multi-database support, Redis cache, Docker-based development, and modern Python dependency management.

Template V2 pair generation uses the versioned, executable backend-foundation
contract documented in [`template_v2/README.md`](template_v2/README.md).
Keycloak/PostgreSQL is its standard Connected profile; Cognito and MongoDB are
retained compatibility paths rather than defaults. The same guide documents
the Python-owned check/plan/diff/create/reconcile/detach/apply lifecycle used by
the paired Flutter creator, including exact-intent writes and rollback. The
standard pair also consumes the Python-owned, checksum-pinned neutral records
starter (model, repository, service, schemas, `/records` routes, and Alembic
migration); retained compatibility profiles remain route-empty.

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
- ✅ **Multi-database support**: Neo4j, PostgreSQL, MySQL, SQLite
- ✅ Redis integration as caching layer
- ✅ Docker & Docker Compose for reproducible environments
- ✅ Environment variable-based configuration
- ✅ Modular architecture with clean separation of concerns
- ✅ Modern Python dependency management with PDM

## 📋 Prerequisites

**Only requirement:** Docker must be installed and running.

- [Download Docker Desktop](https://www.docker.com/get-started)
- Start Docker Desktop

> **Important:** No local Python, Poetry, or PDM installation required! Everything runs in Docker containers.

## 🚀 Quick Start

### Create a new Template V2 app/backend pair

New generated applications must start from the shared creator in the sibling
`flutter_app_template` repository. The creator gathers this Python template
root, the empty backend publication repository, and the exact
`app/apps/<app_id>` destination, then shows one content-free app/backend plan
before either repository can change.

**Windows PowerShell (from `flutter_app_template`):**

```powershell
.\quick-start-v2.ps1
```

**Linux/macOS/WSL (from `flutter_app_template`):**

```bash
./quick-start-v2.sh
```

Choose `author` to create public blueprint/brand inputs, then `create` for the
paired plan. Choose `manage` later for paired reconcile, rebrand/extension
apply, or role-scoped detach. Enter, cancellation, and missing exact intent are
read-only. Credentials, database passwords, Keycloak administrator setup, and
signing values remain deployment inputs and are never creator inputs.

The Python `quick-start.ps1`/`quick-start.sh` scripts below configure and run an
already selected backend checkout. They are not an alternative application
generator and must not create `app/apps/<app_id>` targets directly.

### Guided Setup (Recommended)

On first run, the quick-start scripts will launch an **interactive setup wizard** that helps you configure:
- Docker image name and version
- Python version
- Database type (PostgreSQL, Neo4j, or MongoDB)
- Database mode (local Docker or external)
- API settings (port, debug mode)

**Windows PowerShell:**
```powershell
.\quick-start.ps1
```

**Linux/Mac:**
```bash
./quick-start.sh
```

The script will:
- ✅ Check Docker installation
- ✅ Create `.env` from template
- ✅ Detect database type (PostgreSQL/Neo4j/MongoDB) and mode (local/external)
- ✅ Start the correct containers automatically

### 🔐 Keycloak Bootstrap (Optional)

If you plan to use Keycloak authentication, you can bootstrap a ready-to-use realm
with default clients, roles, and users via Docker.

**Steps:**
1. Ensure your Keycloak server is running (default URL: `http://localhost:9090`).
2. Run the quick-start script and choose **"Run Keycloak realm bootstrap (Docker)"** from the Setup menu.
3. Adjust the bootstrap environment variables in `.env` if needed (see `setup/.env.template`).

**Defaults used by the bootstrap script:**
- Realm: `python-api-template`
- Backend client: `python-api-template-backend`
- Frontend client: `python-api-template-frontend`
- Frontend root URL: `http://localhost:3000`
- API root URL: `http://localhost:8081`

**Useful bootstrap variables (optional):**
- `KEYCLOAK_BOOTSTRAP_URL` (override the Keycloak URL used by the bootstrap container)
- `KEYCLOAK_ADMIN` / `KEYCLOAK_ADMIN_PASSWORD`
- `KEYCLOAK_FRONTEND_CLIENT_ID` / `KEYCLOAK_BACKEND_CLIENT_ID`
- `KEYCLOAK_ROLES` (semicolon-separated)
- `KEYCLOAK_USERS` (semicolon-separated `username:password:role1,role2` specs)

### Option 1: Quick Start with PostgreSQL (Manual)

**Windows:**
```bash
# Automatically sets up and starts PostgreSQL + Redis + API
cd testing
start-postgres.bat
```

**Linux/Mac:**
```bash
# Copy environment configuration
cp .env.postgres.example .env

# Start services
docker-compose -f docker-compose.postgres.yml up --build
```

**Access:**
- **API**: http://localhost:8081/docs
- **PostgreSQL**: localhost:5433 (user: postgres, password: postgres)

### Option 2: Quick Start with Neo4j (Manual)

**Windows:**
```bash
# Automatically sets up and starts Neo4j + Redis + API
cd testing
start-neo4j.bat
```

**Linux/Mac:**
```bash
# Copy environment configuration
cp .env.neo4j.example .env

# Start services
docker-compose -f docker-compose.neo4j.yml up --build
```

**Access:**
- **API**: http://localhost:8081/docs
- **Neo4j Browser**: http://localhost:7474 (user: neo4j, password: password)

### Test the API

**Windows:**
```bash
test-api.bat
```

**Linux/Mac:**
```bash
curl http://localhost:8081/test/db-test
curl http://localhost:8081/test/db-info
curl http://localhost:8081/test/db-sample-query
```

### Detailed Setup

For complete setup instructions, see **[docs/DOCKER_SETUP.md](docs/DOCKER_SETUP.md)**

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

> Internally this now delegates to the reusable submodule at
> `tools/core-pdm-manager`.

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
python-api-template/
├── app/                          # Main application code
│   ├── api/                      # API layer
│   │   ├── routes/              # Route handlers
│   │   ├── schemas/             # Pydantic request/response models
│   │   └── settings.py          # Configuration
│   ├── backend/                  # Backend layer
│   │   └── database/            # Database handlers
│   │       ├── base.py          # Abstract base class
│   │       ├── factory.py       # Database factory
│   │       ├── neo4j_handler.py # Neo4j implementation
│   │       ├── sql_handler.py   # SQL implementation
│   │       ├── init_db.py       # Initialization
│   │       └── queries.py       # Query helpers
│   ├── models/                   # Data models
│   │   └── sql/example_sql_models.py
│   ├── mounted_data/             # Example data for volume mounts
│   └── main.py                   # FastAPI application entrypoint
├── docs/                         # Documentation
│   ├── DATABASE.md              # Database guide
│   ├── QUICK_START.md           # Quick start guide
│   └── README-DE.md             # German README
├── tools/
│   └── core-pdm-manager/        # Reusable dependency manager submodule
├── .env.template                # Environment variable template
├── docker-compose.yml           # Docker services configuration
├── Dockerfile                   # Docker build file
├── pyproject.toml              # Project metadata and dependencies
├── quick-start.sh              # Smart onboarding script
├── manage-python-project-dependencies.sh # Dependency management wrapper
└── run-docker-build-diagnostics.sh # Dependency diagnostics wrapper
```

## ⚙️ Configuration

### Environment Variables (.env)

| Variable | Description | Default |
|----------|-------------|---------|
| `PORT` | API Port | `8000` |
| `REDIS_URL` | Redis connection | `redis://redis:6379` |
| `DB_TYPE` | Database type | `neo4j` |
| `NEO4J_URL` | Neo4j connection (if DB_TYPE=neo4j) | - |
| `DB_USER` | Database user (Neo4j) | - |
| `DB_PASSWORD` | Database password (Neo4j) | - |
| `DATABASE_URL` | SQL database URL (if DB_TYPE=postgresql/postgres) | - |

Official stability matrix: `postgresql/postgres`, `neo4j`, `mongodb`.  
See [docs/SUPPORT_MATRIX.md](docs/SUPPORT_MATRIX.md) for details.

### Example .env (Neo4j)
```env
PORT=8000
REDIS_URL=redis://redis:6379
DB_TYPE=neo4j
NEO4J_URL=bolt://localhost:7687
DB_USER=neo4j
DB_PASSWORD=password
```

### Example .env (PostgreSQL)
```env
PORT=8000
REDIS_URL=redis://redis:6379
DB_TYPE=postgresql
DATABASE_URL=postgresql://user:password@localhost:5433/mydb
```

## 🧪 API Tests

**Available endpoints:**
- `GET /` - Visitor counter (Redis)
- `GET /cache/{key}` - Get cache value
- `POST /cache/{key}` - Set cache value
- `GET /health` - Health check
- `GET /version` - Show version
- `GET /test/db-test` - Test database connection
- `POST /examples/` - Create example (CRUD demo)
- `GET /examples/` - List examples (CRUD demo)
- `GET /examples/{id}` - Get example (CRUD demo)
- `PUT /examples/{id}` - Update example (CRUD demo)
- `DELETE /examples/{id}` - Delete example (CRUD demo)

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
3. **Test API:** [http://localhost:8081/docs](http://localhost:8081/docs)

### Daily Development
1. **Start backend:** `./quick-start.sh` (with selection menu)
2. **Change code:** Automatic reload in Docker
3. **Add packages:** `./manage-python-project-dependencies.sh` → `pdm add <package>`
4. **Test API:** [http://localhost:8081/docs](http://localhost:8081/docs)

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

### Database Support

This template supports multiple database backends:
- **Neo4j**: Graph database for connected data
- **PostgreSQL**: Powerful relational database
- **MongoDB**: Document database
- **MySQL**: Legacy compatibility backend
- **SQLite**: Legacy compatibility backend

See `docs/DATABASE.md` for detailed database configuration and usage.

### Documentation

- **Database Lock Coordination**: `docs/DATABASE_LOCK.md` - Lock/unlock API for external backup-restore orchestration
- **External Backup/Restore Integration**: `docs/DATABASE_BACKUP.md` - Use the standalone backup-restore service
- **Migration Guide**: `docs/MIGRATION_GUIDE.md` - Real-world schema changes (add tables, columns, relationships) ⭐ **NEW**
- **Database Examples**: `docs/DATABASE_EXAMPLES.md` - SQL vs Neo4j CRUD examples ⭐ **NEW**
- **Database Migrations**: `docs/DATABASE_MIGRATIONS.md` - Production-ready schema management ⭐
- **CRUD Example**: `docs/CRUD_EXAMPLE.md` - Complete CRUD operations guide ⭐
- **Quick CRUD Reference**: `docs/QUICK_CRUD_REFERENCE.md` - Quick reference cheat sheet ⭐
- **Docker Setup**: `docs/DOCKER_SETUP.md` - Complete Docker setup guide ⭐
- **How to Add Endpoint**: `docs/HOW_TO_ADD_ENDPOINT.md` - Step-by-step guide ⭐
- **Database Credentials**: `docs/DATABASE_CREDENTIALS.md` - Security & credential management ⭐
- **Project Structure**: `docs/PROJECT_STRUCTURE.md` - Structure explanation
- **Quick Start**: `docs/QUICK_START.md` - Get started quickly
- **Database Guide**: `docs/DATABASE.md` - Database configuration and usage
- **Architecture**: `docs/ARCHITECTURE.md` - Architecture overview
- **German README**: `docs/README-DE.md` - Deutsche Dokumentation

### Deployment

- **Registry:** GitLab Container Registry
- **Deployment:** Azure Container Apps compatible
- **Setup Marker:** `.setup-complete` is automatically created/deleted

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
