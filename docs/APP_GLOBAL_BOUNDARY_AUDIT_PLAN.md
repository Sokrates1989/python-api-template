# Backend App/Global Boundary Audit And Plan

Last updated: 2026-07-01

## Purpose

This audit checks whether `python-api-template` keeps product-specific backend work inside `app/apps/<app_id>/` while reserving global folders for reusable platform behavior. It also records which app-owned patterns are good candidates for extraction and which global modules should become opt-in or app-owned.

The goal is not to make everything global. The goal is a clear boundary:

- App-specific folders own product behavior, product copy, product database tables, product route prefixes, and product migrations.
- Global folders own app discovery, route composition, auth, database adapters, provider-neutral contracts, shared route groups, shared feature runtimes, and operational tooling.
- Reusable feature runtimes may live globally only when they are product-neutral and each app still explicitly owns its public route facade, service facade, schema alias, and migrations.

## Executive Summary

The current architecture is mostly separated, but it is not 100% clean yet. The recent app-boundary work created the right foundation: selected apps are loaded through `BackendAppDefinition`, app routes are registered from `app/apps/<app_id>/definition.py`, Felix rewards live under `app/apps/felix/`, and app migrations are scoped through app-specific migration locations.

The remaining risk is mainly historical drift. Older global route modules, older docs, and broad backwards-compatible defaults still make it too easy for new work to land in global folders by habit. There is also duplicated app facade code that could be centralized without moving product decisions out of each app.

## Current Boundary Model

The backend currently uses this model:

- `app/apps/contracts.py` defines the app contract used by all backend apps.
- `app/apps/registry.py` discovers and loads the active app definition.
- `app/main.py` includes explicitly selected shared route groups and the active app's own `RouteRegistration` entries.
- `app/api/shared_routes/` owns reusable opt-in shared routes.
- `app/apps/<app_id>/routes/`, `schemas/`, `services/`, `config/`, and `migrations/` own app-specific behavior.
- `app/backend/shared_services/`, `app/backend/adapters/`, `app/backend/ports/`, and provider-specific backend services own reusable runtime behavior.
- `alembic/versions/` is for global provider-wide migrations only.
- `app/apps/<app_id>/migrations/versions/` is for app-owned tables and data shape.

This is the desired direction and should remain the core rule.

## Findings

### Finding 1: Felix rewards are correctly app-specific

Felix rewards currently live under `app/apps/felix/`:

- `app/apps/felix/routes/wellness.py`
- `app/apps/felix/services/rewards_service.py`
- `app/apps/felix/services/rewards_state.py`
- `app/apps/felix/migrations/versions/felix_002_rewards_state.py`

This is correct because reward unlocks, streak protection, media preferences, and Felix wording are product behavior. These files should not move into global folders unless a second app proves an identical neutral capability is needed.

Potential future global extraction: a generic per-user JSON state repository could be global if another app needs the same persistence mechanism. Felix reward state semantics must remain app-owned.

### Finding 2: App migrations are now correctly scoped

Felix migrations are under `app/apps/felix/migrations/versions/`, and the active app definition points to app-local migration locations. This prevents Felix tables from appearing in other databases by default.

This is the correct model. New product tables must never be placed in `alembic/versions/` unless they are provider-wide platform tables needed by all apps.

### Finding 3: Legacy global route modules still create boundary confusion

There are older global route modules under `app/api/routes/`. Some overlap conceptually with the newer explicit shared route group model in `app/api/shared_routes/`. The biggest risk is `app/api/routes/wellness.py`, which looks like a globally mounted wellness API but should not be the pattern for product apps.

Current desired state:

- App route facades belong in `app/apps/<app_id>/routes/`.
- Shared opt-in route groups belong in `app/api/shared_routes/`.
- Global `app/api/routes/` should not be the place for new product-facing routes.

Recommended action: quarantine or retire legacy `app/api/routes/*` modules that are no longer mounted by `main.py`. If compatibility requires keeping them briefly, add prominent module docs marking them legacy and non-authoritative.

Current status: duplicate legacy modules for `test`, `files`, `packages`,
`database_lock`, `users`, and `examples` are now thin compatibility shims to
`app/api/shared_routes/`. The legacy package has a README and module docs
marking it compatibility-only. Legacy wellness, backup, and SQL sync modules
remain unmounted compatibility surfaces and are documented as non-authoritative.

### Finding 4: Shared route group defaults are now explicit

`BackendAppDefinition.shared_route_groups` now defaults to an empty tuple.
Template/demo apps and generated compatibility slices must name their shared
route groups explicitly. Product apps like Felix keep a small explicit set so
they do not inherit demo, test, file, package, or database-lock routes by
accident.

Follow-up review: keep shared route exposure explicit in every new app
definition.

### Finding 5: Redis cache diagnostics are now an opt-in shared route group

`main.py` owns root, health, version, and database stats. Health/version are
reasonable platform endpoints. Redis cache diagnostics now live in
`app/api/shared_routes/cache.py` and are exposed only when an app lists the
`cache` shared route group.

Follow-up review: keep `/health` and `/version` in `main.py` unless
app-specific health semantics become necessary.

### Finding 6: Wellness is a valid shared runtime, but global feature coupling should be watched

Global wellness runtime code exists under paths such as:

- `app/api/schemas/wellness/`
- `app/backend/ports/wellness_repository.py`
- `app/backend/adapters/wellness_repository_factory.py`
- `app/backend/shared_services/wellness_service.py`
- `app/backend/services/sql/wellness_repository.py`
- `app/models/sql/wellness.py`

This is acceptable because wellness is currently treated as a reusable feature runtime used by several app slices. Apps still own their public route facade, service facade, schema alias, and SQL migrations.

Risk: provider sync services also contain wellness-specific replay logic. This is acceptable while wellness is the only reusable feature runtime, but the pattern should not grow into provider services with many feature-specific branches.

Recommended action: if a second reusable feature needs sync replay, introduce a feature replay registry so provider sync services stay generic.

### Finding 7: App route facades are duplicated across app slices

The wellness route facades in app slices are very similar. This duplication keeps ownership explicit, but it also increases maintenance cost and makes behavior drift more likely.

Recommended action: extract route mechanics into a product-neutral route factory, while keeping each app's registration explicit. For example, a helper could receive service dependencies, schema aliases, and an optional list of extra app-specific endpoints. Felix would still own Felix rewards endpoints separately.

Do not move Felix-specific route behavior into the shared factory.

### Finding 8: App schema re-exports are acceptable but should be documented

Template apps re-export shared wellness schemas from app-local schema files. This is a reasonable way to preserve app-local import boundaries while avoiding copy-paste schema definitions.

Recommended action: document this as an accepted pattern. If it becomes repetitive, create a scaffold template or a small code-generation helper instead of removing app-local schema boundaries.

### Finding 9: Docs still contain old global-first examples

`docs/APP_SLICE_BOUNDARY_GUIDE.md` is aligned with the desired boundary model. Other docs still contain older examples that tell contributors to add routes to global route folders or register app work directly in `main.py`.

Recommended action: update docs so the default path for product endpoints is always `app/apps/<app_id>/`. Global folders should be described as opt-in platform or shared runtime spaces only.

## App-Specific Code That Can Become Global

Only extract app-specific code when the extracted unit is truly product-neutral and needed by more than one app.

### Candidate A: Wellness route facade mechanics

Keep in apps:

- Route registration ownership.
- App route prefix.
- Product-specific extra endpoints.
- App-specific copy and response semantics.

Move or centralize globally:

- Common route factory mechanics for bootstrap, check-ins, diary entries, activities, and sync operation translation.
- Common HTTP error translation for shared service result objects.
- Common debug-only reset guard logic if it remains identical across apps.

Suggested location: `app/api/route_factories/` or `app/backend/route_factories/`, with docs explaining that factories never auto-mount routes.

### Candidate B: Shared result-to-HTTP error helpers

Several app facades translate shared service result objects into HTTP errors. This can become a global helper if the result contract is stable.

Suggested location: `app/api/http_errors.py` or `app/backend/shared_services/result_errors.py`.

### Candidate C: Generic per-user state persistence

Felix rewards should stay app-owned. A generic storage helper could become global later if a second app needs durable per-user JSON state with the same provider behavior.

Suggested rule: do not extract until there is another concrete app use case.

### Candidate D: App migration command helpers

The migration runner is already global. Additional helpers for creating app migration folders, validating app migration paths, or checking app version tables would be valid global tooling.

Suggested location: `scripts/` or `app/backend/database/` only if runtime code needs it.

## Global Code That Should Become App-Specific Or Opt-In

### Candidate A: Legacy `app/api/routes/wellness.py`

This file should not be treated as a current shared endpoint. It should be removed, moved behind an explicit shared route group, or marked legacy until deletion.

Preferred action: delete after verifying no app imports it.

### Candidate B: Other legacy `app/api/routes/*` modules

Any route module that is not included through `api/shared_routes` or an app definition should be reviewed. Keep only if it is an intentional compatibility shim. Otherwise, delete or move into the correct shared-route/app-slice home.

### Candidate C: Redis cache endpoints in `main.py`

Completed: cache diagnostics live in `app/api/shared_routes/cache.py` and are
mounted only through explicit `shared_route_groups` opt-in.

### Candidate D: Broad default shared route groups

Completed: `BackendAppDefinition.shared_route_groups` defaults to an empty
tuple, and existing app definitions that need shared routes declare them
explicitly.

### Candidate E: Feature-specific provider sync branches

Keep wellness-specific sync replay global only while wellness is intentionally a reusable runtime. If replay becomes product-specific, move it app-local. If multiple shared features need replay, use a global replay registry.

## Documentation Updates Needed

Update these docs so they consistently teach the app-slice-first architecture:

- `docs/PROJECT_STRUCTURE.md`
- `docs/HOW_TO_ADD_A_NEW_ENDPOINT.md`
- `docs/HOW_MIGRATIONS_WORK.md`
- `docs/ARCHITECTURE.md`
- `docs/APP_SLICE_BOUNDARY_GUIDE.md`

Required documentation messages:

- Product endpoints start in `app/apps/<app_id>/routes/`.
- Product services start in `app/apps/<app_id>/services/`.
- Product schemas start in `app/apps/<app_id>/schemas/`, even when they re-export shared schemas.
- Product migrations start in `app/apps/<app_id>/migrations/versions/`.
- Shared route groups must be opt-in and live under `app/api/shared_routes/`.
- Shared feature runtimes are allowed globally only when product-neutral and explicitly documented.
- `main.py` composes apps; it should not collect product routes directly.
- Never use `/api/` route prefixes in this API service.

## Implementation Plan

### Phase 1: Documentation cleanup

1. Update global docs to prefer app-slice-first examples.
2. Add a short route ownership table to `PROJECT_STRUCTURE.md`.
3. Add app migration examples to `HOW_MIGRATIONS_WORK.md`.
4. Add a warning that `app/api/routes/` is legacy or compatibility-only if those files remain.

Status: completed for the main architecture, endpoint, migration, project
structure, quick-start, app README, model README, German README, and CRUD
reference docs.

Expected risk: low.

### Phase 2: Legacy route cleanup

1. Search for imports of `api.routes.*`.
2. Confirm `main.py` mounts only `api.shared_routes` and app definitions.
3. Delete unused legacy global route modules or move intentional shared modules into `api/shared_routes`.
4. Add tests or import checks for selected shared route groups.

Status: partially completed. Duplicate shared implementations in
`app/api/routes/` were replaced with compatibility shims. Legacy wellness,
backup, and SQL sync modules remain for compatibility and are marked
non-authoritative.

Expected risk: medium because old scripts or docs may import legacy modules.

### Phase 3: Shared route factory extraction

1. Compare app wellness route facades and list identical operations.
2. Extract a product-neutral route factory for shared wellness operations.
3. Keep app route files as small composition modules.
4. Keep Felix rewards endpoints app-owned beside the shared route factory usage.
5. Run route import checks and API smoke tests.

Expected risk: medium because route dependency injection and OpenAPI metadata can drift.

### Phase 4: Shared route opt-in hardening

1. Change `BackendAppDefinition.shared_route_groups` default to an empty tuple.
2. Add explicit shared route groups to demo/template app definitions.
3. Keep Felix restricted to only the route groups it needs.
4. Add a docs note and possibly a lightweight registry validation test.

Status: completed. The default shared route group tuple is empty, existing app
definitions opt in explicitly, and cache diagnostics are selected through the
same mechanism.

Expected risk: medium because backwards compatibility changes.

### Phase 5: Provider feature replay registry

1. Keep current wellness replay code until another shared feature needs replay.
2. When needed, introduce a product-neutral replay registry.
3. Let shared feature runtimes register replay handlers without provider services importing product details.

Expected risk: medium to high, depending on sync coverage.

## Ongoing Review Checklist

Use this checklist before accepting new backend code:

- Does the code mention a product name such as Felix, rewards, startlist, streaks, or Sonnen? If yes, it belongs under `app/apps/<app_id>/` unless a documented shared feature runtime justifies otherwise.
- Does the code create or migrate product tables? If yes, the migration belongs under `app/apps/<app_id>/migrations/versions/`.
- Does the code expose a route for one product? If yes, the route belongs under `app/apps/<app_id>/routes/`.
- Does the code expose a reusable route group? If yes, it belongs under `app/api/shared_routes/` and must be explicitly selected by app definitions.
- Does the code import optional provider libraries at module import time? If yes, ensure the selected database profile actually requires that provider.
- Does the route start with `/api/`? If yes, reject it.
- Does a global module include product copy? If yes, move the copy app-local.
- Does a shared helper require app-specific assumptions? If yes, keep it app-local until another app proves reuse.

## Suggested Verification Commands

Run these commands when implementing the cleanup phases:

```powershell
rg -n "felix|reward|rewards|startlist|sonnen|streak" app\backend app\api app\models alembic
rg -n "@router\.|APIRouter|include_router|/api/" app\api app\apps app\main.py
rg -n "api\.routes|from api.routes|import api.routes" app tests docs scripts
rg -n "migration_version_locations|shared_route_groups|RouteRegistration" app\apps app\main.py docs
```

The first command should only return documented shared runtime references or app-local product files. The route scan should not show `/api/` prefixes.

## Decision Record

For now, the target architecture is app-slice-first with opt-in shared route groups and documented shared feature runtimes. Felix-specific rewards and startlist behavior must remain under `app/apps/felix/`. Wellness can remain a shared runtime because several app slices use it, but its public API surface stays app-owned.
