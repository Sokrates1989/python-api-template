# Architecture Overview

`python-api-template` hosts multiple backend apps inside one FastAPI runtime.
The central architecture rule is app-slice-first ownership: product-specific
behavior lives under `app/apps/<app_id>/`, while global modules stay
product-neutral and reusable.

## Design Principles

1. Product routes, services, schemas, config, deployment overrides, and app
   migrations belong to the selected app slice.
2. `app/main.py` composes selected apps and shared route groups; it does not
   collect product routes directly.
3. Shared route groups live under `app/api/shared_routes/` and are mounted only
   when app definitions opt in.
4. Shared feature runtimes may live globally only when they avoid product IDs,
   product copy, and app-only database ownership.
5. Provider adapters and database handlers are selected by contracts, not by
   route-level provider branching.
6. API route prefixes must never start with `/api/`.

## Runtime Composition

```text
app/main.py
  -> settings.get_backend_app_definition()
  -> selected BackendAppDefinition.route_registrations
  -> selected BackendAppDefinition.shared_route_groups
  -> FastAPI include_router calls
```

`BackendAppDefinition` is the manifest for one backend app. It declares app
metadata, app-owned routes, app migration locations, infrastructure needs, and
explicit shared route groups.

## Request Flow

```text
HTTP request
  -> FastAPI app
  -> shared route group or app-owned route registration
  -> app route facade under app/apps/<app_id>/routes/
  -> app service facade under app/apps/<app_id>/services/
  -> shared runtime or provider adapter
  -> database/provider
```

Shared routes such as `/users/*`, `/cache/*`, and `/database/*` are reusable
route groups. Product routes such as Felix wellness and rewards stay under the
Felix app slice.

## Directory Responsibilities

| Directory | Responsibility |
| --- | --- |
| `app/apps/` | Selected app slices and app composition contracts. |
| `app/api/shared_routes/` | Reusable opt-in route groups. |
| `app/api/shared_dependencies/` | Shared FastAPI dependencies such as auth and admin key checks. |
| `app/api/shared_schemas/` | Shared schemas for reusable route groups. |
| `app/api/schemas/` | Product-neutral schemas for documented shared runtimes. |
| `app/backend/ports/` | Provider-neutral contracts. |
| `app/backend/adapters/` | Provider adapter factories. |
| `app/backend/shared_services/` | Reusable service facades. |
| `app/backend/services/` | Provider-specific reusable services. |
| `app/backend/database/` | Database initialization, handlers, migrations, and startup probes. |
| `app/models/` | Provider models used by shared runtimes and platform code. |
| `alembic/versions/` | Provider-wide SQL migrations. |

`app/api/routes/` is legacy compatibility space. Do not add new product routes
there.

## Database Architecture

The backend uses provider contracts and factories to support PostgreSQL, Neo4j,
MongoDB, and no-database app profiles.

```text
route/service facade
  -> backend port
  -> provider adapter factory
  -> provider-specific service or repository
  -> database handler
```

Optional provider dependencies must not be imported at module import time unless
the selected profile requires that provider.

## Migration Architecture

The startup migration runner applies:

1. Global provider-wide migrations from `alembic/versions/`.
2. Selected app migrations declared in
   `BackendAppDefinition.migration_version_locations`.

Product tables and app-owned feature tables belong under
`app/apps/<app_id>/migrations/versions/`.

## Shared Feature Runtime Pattern

The wellness runtime is the current shared feature example. Its reusable service
and schema contracts can live globally because they are product-neutral. Apps
still own:

- route facades,
- service facades,
- schema aliases,
- public route prefixes,
- app-specific migrations,
- product-specific extensions such as Felix rewards.

## Operational Endpoints

`/health`, `/version`, `/`, and database stats remain platform endpoints in
`app/main.py`.

Redis cache diagnostics are an opt-in shared route group under
`app/api/shared_routes/cache.py`. Apps expose `/cache/{key}` only when they list
`"cache"` in `shared_route_groups`.

## Security And Middleware

Middleware, auth dependencies, OpenAPI configuration, and route security
requirements are shared infrastructure. App-specific security schemes and route
requirements are declared on the selected app definition so Swagger UI reflects
the active app profile.

## Adding New Backend Work

Start inside `app/apps/<app_id>/` when the work is product-specific. Extract to
global code only when the extracted unit is product-neutral, reusable, and
documented as shared infrastructure or a shared runtime.
