# Database-Specific CRUD Examples

This template provides database-specific CRUD examples while keeping auth and user routes shared across providers.

## Overview

Routes are registered conditionally from `app/main.py` using `settings.normalized_db_type()`.

| Database Type | Route Families | Notes |
|---|---|---|
| `postgresql` / `postgres` (official) | `/examples/`, `/v1/sync/*`, `/users/*` | SQLAlchemy + Alembic migrations |
| `neo4j` (official) | `/example-nodes/`, `/users/*` | Graph-native Cypher queries |
| `mongodb` (official) | `/examples/`, `/users/*` | Document model, index-based constraints |
| `mysql` / `sqlite` (legacy compatibility) | `/examples/`, `/v1/sync/*`, `/users/*` | Kept for compatibility, not in stability matrix |

Official matrix details: [SUPPORT_MATRIX.md](SUPPORT_MATRIX.md)

## SQL Example Routes

- Path: `/examples/`
- Model: `app/models/sql/example.py`
- Service facade: `app/backend/services/example_service.py`
- SQL adapter target: `app/backend/services/sql/example_service.py`
- Routes: `app/api/shared_routes/examples.py` (explicit shared route group)

## Neo4j Example Routes

- Path: `/example-nodes/`
- Model: `app/models/neo4j/example.py`
- Service facade: `app/backend/services/example_service.py`
- Neo4j adapter target: `app/backend/services/neo4j/example_node_service.py`
- Routes: `app/api/shared_routes/examples.py` (explicit shared route group)

## MongoDB Example Routes

- Path: `/examples/`
- Service facade: `app/backend/services/example_service.py`
- MongoDB adapter target: `app/backend/services/mongodb/example_service.py`
- Routes: `app/api/shared_routes/examples.py` (explicit shared route group)

## Shared User Routes

- Path: `/users/*`
- Routes: `app/api/shared_routes/users.py` (explicit shared route group)
- Service facade: `app/backend/services/user_service.py`
- Provider services:
  - SQL: `app/backend/services/sql/user_service.py`
  - Neo4j: `app/backend/services/neo4j/user_service.py`
  - MongoDB: `app/backend/services/mongodb/user_service.py`

## Route Registration (Current)

```python
from apps.contracts import BackendAppDefinition, RouteRegistration
from apps.template_app.config import TEMPLATE_APP_CONFIG
from apps.template_app.routes import sync, wellness

TEMPLATE_APP_DEFINITION = BackendAppDefinition(
    app_id=TEMPLATE_APP_CONFIG.app_id,
    display_name=TEMPLATE_APP_CONFIG.display_name,
    backend_data_profile=TEMPLATE_APP_CONFIG.backend_data_profile,
    route_registrations=(
        RouteRegistration(
            router=wellness.router,
            external_prefix=TEMPLATE_APP_CONFIG.wellness_mount_prefix,
            public_prefix=TEMPLATE_APP_CONFIG.wellness_public_prefix,
        ),
        RouteRegistration(
            router=sync.router,
            external_prefix="",
            public_prefix=TEMPLATE_APP_CONFIG.sync_public_prefix,
        ),
    ),
    shared_route_groups=("cache", "users", "examples"),
)
```

Shared route groups are selected explicitly by each app definition. The shared
routers enforce provider capabilities at runtime:
- `examples` endpoints return `400` only for unsupported/unknown DB providers.
- `sync` endpoints return `400` when `DB_TYPE` is not SQL-compatible.

## Switching Providers

1. Update `.env`.
2. Start the matching compose profile.
3. Verify routes in Swagger (`/docs`).

```bash
# PostgreSQL
DB_TYPE=postgresql

# Neo4j
DB_TYPE=neo4j

# MongoDB
DB_TYPE=mongodb
```

```bash
# PostgreSQL profile
docker compose -f local-deployment/docker-compose.postgres.yml -f local-deployment/docker-compose.yml --env-file .env up

# Neo4j profile
docker compose -f local-deployment/docker-compose.neo4j.yml -f local-deployment/docker-compose.yml --env-file .env up

# MongoDB profile
docker compose -f local-deployment/docker-compose.mongodb.yml -f local-deployment/docker-compose.yml --env-file .env up
```

## Notes

- SQL migrations run only for SQL backends.
- Neo4j and MongoDB skip Alembic migrations by design.
- For long-term stability, prefer `postgresql/postgres`, `neo4j`, or `mongodb`.
