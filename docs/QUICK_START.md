# Quick Start Guide

Get started with this FastAPI template in minutes.

## New Template V2 Applications

Create and manage a new Flutter/backend pair only through the shared Template
V2 creator in `flutter_app_template`. From that repository run
`.\quick-start-v2.ps1` on PowerShell or `./quick-start-v2.sh` on Bash, then use
the `author`, `create`, and `manage` menu actions. The guided flow requests this
Python template root, a distinct empty backend repository, and the exact
`app/apps/<app_id>` destination. It renders one content-free aggregate plan and
requires exact intent before app or backend publication.

This repository's own `quick-start.ps1` and `quick-start.sh` configure and run
an existing backend checkout. They do not generate new application targets.
Provider credentials, database passwords, Keycloak administrator setup, and
signing values remain runtime/deployment inputs and must not be placed in
creator inputs or generated files.

## Prerequisites

- Docker and Docker Compose installed
- Git (for cloning the repository)

## Setup Steps

### 1. Clone and Navigate

```bash
git clone <your-repo-url>
cd python-api-template
```

### 2. Configure Environment

```bash
# Copy the template
cp .env.template .env

# Edit .env and set your database type
# Official options: neo4j, postgresql (or postgres), mongodb
# Legacy compatibility values: mysql, sqlite
```

### 3. Choose Your Database

#### Option A: Neo4j (Default)

```bash
# .env
DB_TYPE=neo4j
NEO4J_URL=bolt://localhost:7687
DB_USER=neo4j
DB_PASSWORD=password
```

Start Neo4j:
```bash
docker run -d -p 7687:7687 -p 7474:7474 \
  -e NEO4J_AUTH=neo4j/password \
  neo4j:latest
```

#### Option B: PostgreSQL

```bash
# .env
DB_TYPE=postgresql
DATABASE_URL=postgresql://postgres:password@localhost:5433/mydb
```

Start PostgreSQL:
```bash
docker run -d -p 5433:5432 \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=mydb \
  postgres:latest
```

#### Option C: MongoDB

```bash
# .env
DB_TYPE=mongodb
MONGODB_URL=mongodb://mongo:mongo@localhost:27017
MONGODB_DB_NAME=apidb
```

### 4. Start the Application

```bash
# Using Docker Compose (recommended)
docker-compose up

# Or run locally
uvicorn app.main:app --reload
```

### 5. Test the API

```bash
# Health check
curl http://localhost:8081/health

# Database test
curl http://localhost:8081/test/db-test

# API documentation
open http://localhost:8081/docs
```

Expected health response includes provider diagnostics:
`status`, `database_type`, `provider_profile`, `startup_probe_status`.

## Project Structure

```
python-api-template/
├── app/
│   ├── api/                    # API layer
│   │   ├── routes/            # Route handlers
│   │   └── settings.py        # Configuration
│   ├── backend/               # Backend layer
│   │   └── database/          # Database handlers
│   │       ├── base.py        # Abstract base class
│   │       ├── factory.py     # Database factory
│   │       ├── neo4j_handler.py
│   │       ├── sql_handler.py
│   │       ├── init_db.py     # Initialization
│   │       └── queries.py     # Query helpers
│   ├── models/                # Data models
│   │   └── sql/example_sql_models.py
│   └── main.py               # Application entry point
├── docs/                      # Documentation
│   ├── DATABASE.md           # Database guide
│   └── QUICK_START.md        # This file
├── .env.template             # Environment template
└── docker-compose.yml        # Docker configuration
```

## Next Steps

1. **Add your models**: Edit `app/models/` for SQL databases
2. **Create routes**: Add product routes in `app/apps/<app_id>/routes/`, then
   register them through the app definition
3. **Read the docs**: Check `docs/DATABASE.md` for detailed database usage
4. **Customize**: Modify the template to fit your needs

## Common Commands

```bash
# View logs
docker-compose logs -f

# Restart services
docker-compose restart

# Stop services
docker-compose down

# Rebuild after changes
docker-compose up --build
```

## Troubleshooting

### Database connection failed

- Check if database server is running
- Verify connection settings in `.env`
- Check firewall/network settings

### Port already in use

- Change `PORT` in `.env`
- Or stop the conflicting service

### Module not found

- Run `poetry install` or `pdm install`
- Rebuild Docker image: `docker-compose up --build`

## Getting Help

- Check `docs/DATABASE.md` for database-specific help
- Review API docs at `http://localhost:8081/docs`
- Check logs: `docker-compose logs`

