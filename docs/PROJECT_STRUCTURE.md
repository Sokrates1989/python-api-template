# Project Structure Guide

This guide explains where backend code belongs in the multi-app template. The
default rule is app-slice-first: product behavior lives under
`app/apps/<app_id>/`, while global folders hold reusable infrastructure,
contracts, provider adapters, shared route groups, and documented shared
feature runtimes.

See also: `docs/APP_SLICE_BOUNDARY_GUIDE.md`.

## Route Ownership

| Code type | Correct location | Notes |
| --- | --- | --- |
| Product route facade | `app/apps/<app_id>/routes/` | Register through the app definition. |
| Product service facade | `app/apps/<app_id>/services/` | Keep product copy and app-specific behavior here. |
| Product schema aliases | `app/apps/<app_id>/schemas/` | Re-export shared schemas here when an app uses a shared runtime. |
| Product SQL migrations | `app/apps/<app_id>/migrations/versions/` | Declare with `migration_version_locations`. |
| Shared route group | `app/api/shared_routes/` | Must be explicitly selected by an app definition. |
| Shared feature runtime | `app/backend/` or `app/api/schemas/` | Allowed only when product-neutral and documented. |
| Provider-wide migration | `alembic/versions/` | Use only for schema required by all SQL app profiles. |
| Legacy route compatibility | `app/api/routes/` | Compatibility-only; do not add new product routes here. |

Never add `/api/` as a route prefix in this API service.

## Directory Overview

```text
python-api-template/
|-- app/
|   |-- apps/
|   |   |-- contracts.py
|   |   |-- registry.py
|   |   |-- template_app/
|   |   |   |-- config/
|   |   |   |-- definition.py
|   |   |   |-- deployment/
|   |   |   |-- env/
|   |   |   |-- migrations/versions/
|   |   |   |-- routes/
|   |   |   |-- schemas/
|   |   |   `-- services/
|   |   `-- <app_id>/
|   |-- api/
|   |   |-- shared_routes/
|   |   |-- shared_dependencies/
|   |   |-- shared_schemas/
|   |   |-- schemas/
|   |   |-- routes/
|   |   |-- middleware/
|   |   |-- config/
|   |   `-- settings.py
|   |-- backend/
|   |   |-- adapters/
|   |   |-- database/
|   |   |-- ports/
|   |   |-- services/
|   |   `-- shared_services/
|   |-- models/
|   `-- main.py
|-- alembic/versions/
|-- docs/
`-- tests/
```

## Backend App Slices

`app/apps/<app_id>/` contains selected-app code. Each slice owns its public
route facades, service facades, schema aliases, config, deployment overrides,
and app-owned migrations.

```python
"""
Felix backend definition.

This module declares the route families owned by the Felix backend slice.
"""
from apps.contracts import BackendAppDefinition, RouteRegistration
from apps.felix.config import FELIX_APP_CONFIG
from apps.felix.routes import sync, wellness


FELIX_APP_DEFINITION = BackendAppDefinition(
    app_id=FELIX_APP_CONFIG.app_id,
    display_name=FELIX_APP_CONFIG.display_name,
    backend_data_profile=FELIX_APP_CONFIG.backend_data_profile,
    route_registrations=(
        RouteRegistration(
            router=wellness.router,
            external_prefix=FELIX_APP_CONFIG.wellness_mount_prefix,
            public_prefix=FELIX_APP_CONFIG.wellness_public_prefix,
        ),
        RouteRegistration(
            router=sync.router,
            external_prefix="",
            public_prefix=FELIX_APP_CONFIG.sync_public_prefix,
        ),
    ),
    migration_version_locations=("migrations/versions",),
    shared_route_groups=("cache", "users"),
)
```

## Shared Routes

Shared route groups live under `app/api/shared_routes/`. They are reusable HTTP
surfaces, not product routes. Apps opt in explicitly through
`BackendAppDefinition.shared_route_groups`.

Current shared groups include:

- `cache`: Redis cache diagnostics.
- `database_lock`: database restore lock management.
- `examples`: provider-neutral example CRUD routes.
- `files`: file inspection helpers.
- `packages`: package inspection helpers.
- `test`: database test helpers.
- `users`: shared user profile routes.

Template and demo apps may expose broad helper groups. Product apps should list
only the groups they actually need.

## Global API Folder

`app/api/` is for HTTP infrastructure, shared dependencies, shared schemas, and
explicit shared route groups. `app/api/routes/` remains only for legacy
compatibility modules. Do not add new product endpoints there.

## Backend Runtime

`app/backend/` contains provider-neutral runtime code:

- `ports/`: contracts such as repository or capability interfaces.
- `adapters/`: provider factory and adapter selection logic.
- `shared_services/`: reusable service facades.
- `services/`: provider-specific service implementations.
- `database/`: database initialization, handlers, migrations, and probes.

Shared runtimes must stay product-neutral. If a module mentions Felix rewards,
Startlist, streaks, Sonnen copy, or a single product route, it belongs in the
owning app slice unless a documented shared feature runtime justifies it.

## Request Flow

```text
HTTP request
  -> FastAPI app in app/main.py
  -> selected shared route group or app-owned RouteRegistration
  -> app route facade under app/apps/<app_id>/routes/
  -> app service facade under app/apps/<app_id>/services/
  -> shared runtime or provider adapter
  -> database/provider
```

`main.py` composes selected routes. It should not import product route modules
directly or mount app-specific routers by hand.

## Adding Product Features

1. Put route handlers in `app/apps/<app_id>/routes/`.
2. Put app-specific schemas in `app/apps/<app_id>/schemas/`.
3. Put app-specific services in `app/apps/<app_id>/services/`.
4. Put app-owned migrations in `app/apps/<app_id>/migrations/versions/`.
5. Register route families in `app/apps/<app_id>/definition.py`.
6. Add only necessary shared route groups to `shared_route_groups`.

Use global folders only for reusable infrastructure or product-neutral shared
runtime code.

## Migration Ownership

Global migrations in `alembic/versions/` apply to every SQL app profile.
Product tables and selected-feature tables belong in the selected app's
migration stream:

```text
app/apps/<app_id>/migrations/versions/
```

Declare that stream in the app definition:

```python
BackendAppDefinition(
    ...,
    migration_version_locations=("migrations/versions",),
)
```

The startup migration runner applies global migrations first, then the selected
app's declared migration locations using an app-specific version table.

## Summary

Use app slices for product behavior, `app/api/shared_routes/` for opt-in shared
HTTP groups, and global backend folders for product-neutral infrastructure.
When in doubt, start inside `app/apps/<app_id>/` and extract globally only after
the reusable boundary is clear.
