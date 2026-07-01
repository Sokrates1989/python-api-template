# Backend App Slice Boundary Guide

Last updated: 2026-07-01

## Purpose

This guide defines the split between selected-app code and global backend
infrastructure in `python-api-template`.

Use it before adding routes, schemas, services, migrations, SQL models,
provider adapters, or shared route exposure.

## App-Owned Code

Product-specific backend code belongs under `app/apps/<app_id>/`.

Examples:

- Felix rewards services, schemas, routes, and SQL migrations belong under
  `app/apps/felix/`.
- Template App example feature migrations belong under `app/apps/template_app/`.
- Postgres Template SQL example migrations belong under
  `app/apps/postgres_template/`.

App slices own:

- route registration,
- product route modules,
- app-specific schemas,
- app-specific service facades,
- app-specific config,
- app-specific deployment overrides,
- app-specific Alembic migrations.

## Global Code

Global code is allowed only when it is product-neutral infrastructure.

Allowed global code:

- app discovery and selected-app contracts,
- FastAPI composition and lifecycle hooks,
- auth, OpenAPI, middleware, database handlers, and provider adapters,
- shared routes selected explicitly by each app,
- shared feature runtimes that do not know product-specific IDs or copy,
- provider-wide SQL migrations that must affect every SQL app profile.

Disallowed global code:

- Felix reward logic,
- Startlist logic,
- product-specific copy,
- app-specific route prefixes,
- product-specific SQL tables,
- app-only notification or settings state.

## Shared Feature Runtime Rule

A feature runtime may live under `app/backend` or `app/api/schemas` only when
it is reusable and product-neutral.

Apps that use a shared feature runtime still own:

- their route facade under `app/apps/<app_id>/routes`,
- their app-specific service facade under `app/apps/<app_id>/services`,
- their SQL table creation under `app/apps/<app_id>/migrations/versions`.

The wellness runtime follows this pattern. The shared runtime remains global,
but SQL wellness table migrations now live in the selected SQL app slices.

## Shared Route Exposure

Apps must explicitly choose shared route groups through
`BackendAppDefinition.shared_route_groups`.

Examples:

- Felix exposes only explicitly selected shared groups such as `("cache", "users")`.
- Template/demo apps may expose broader example or maintenance groups.
- Internal apps such as secure messaging can disable shared routes entirely.

`BackendAppDefinition.shared_route_groups` defaults to an empty tuple. Do not
rely on broad defaults for any app profile.

## Legacy Route Package

`app/api/routes/` is compatibility-only. It exists so older imports can be
retired deliberately, but it is not the authoritative home for new endpoint
work.

Use:

- `app/apps/<app_id>/routes/` for product route facades,
- `app/api/shared_routes/` for reusable opt-in route groups,
- `app/main.py` only for app composition and platform endpoints.

## SQL Migration Ownership

The global Alembic stream `alembic/versions/` is for provider-wide schema only.

Use global migrations for:

- shared users/auth tables,
- provider-wide sync infrastructure,
- schema that every SQL app profile must have.

Use `app/apps/<app_id>/migrations/versions/` for:

- product tables,
- app-owned feature tables,
- selected-app extensions,
- data migrations that should only run for one app profile.

The startup migration runner applies:

1. global migrations with `alembic_version`,
2. selected app migrations with `alembic_version_<app_id>`.

## New Backend File Checklist

Before adding a file, answer:

1. Does it mention a product name, product route, reward, Startlist, or app-only
   setting?
   - Put it in `app/apps/<app_id>/`.
2. Does it create a table or index that only one app needs?
   - Put it in the selected app migration stream.
3. Does it expose a route?
   - Put the route in the app slice unless it is an explicitly selected shared
     route group.
4. Does it implement provider-neutral infrastructure used by multiple apps?
   - It may belong under `app/backend` or `app/api`.
5. Does it start with `/api/`?
   - Reject it. API services must never use `/api/` route prefixes.
