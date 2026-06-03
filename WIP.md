# Work in Progress

Last updated: 2026-06-03

## Status

Large WIP snapshot. Major backend restructuring in progress.

## What has been done (uncommitted)

- **Multi-app architecture slice**: new `app/apps/` directory structure for app-owned routes/services/schemas
  - `app/apps/contracts.py`, `app/apps/registry.py`
  - `app/apps/demo_app/`, `app/apps/template_app/` directories
- **Shared service separation**: `app/backend/shared_services/` extracted from monolithic services
- **Shared API layout**: `app/api/shared_routes/`, `app/api/shared_dependencies/`, `app/api/shared_schemas/`
- **Refactored services**: `backup_service`, `database_service`, `example_service`, `file_service`, `sync_service`, `wellness_service` all moved toward shared/app-specific split
- **Lazy-loaded database factory**: `app/backend/database/factory.py` no longer eagerly imports unused providers
- **Dockerfile updated**: supports `app/apps/<app_id>/pyproject.toml` + `pdm.lock`, falls back to root
- **Removed legacy root env files**: `.env.drill.*`, `.env.*` profiles replaced by app-level config
- **Removed root `pyproject.toml` + `pdm.lock`**: per-app dependency management
- **Quick-start major refactor**: `quick-start.sh` and `quick-start.ps1` substantially rewritten
- **Menu handlers refactor**: `setup/modules/menu_handlers.sh` and `.ps1` major additions
- **`tools/core-pdm-manager`** submodule marker updated

## Remaining TODOs

- [ ] Complete physical extraction of app-owned route modules into `app/apps/<app_id>/routes/`
- [ ] Complete physical extraction of app-owned service modules into `app/apps/<app_id>/services/`
- [ ] Complete physical extraction of app-owned schema modules into `app/apps/<app_id>/schemas/`
- [ ] Verify `app/apps/mongodb_template` and `app/apps/postgres_template` slices work end-to-end
- [ ] Ensure `pdm.lock` files are generated per app in `app/apps/<app_id>/pdm.lock`
- [ ] Verify Docker build still works after root `pyproject.toml` removal
- [ ] Update `local-deployment/` compose files for new app-id-based Docker build args
- [ ] Update `README.md` to reflect new multi-app architecture
- [ ] Integration test: run full local deployment with a selected app profile

## Related repos

- `d:\Development\Code\swarm\python-api-template` — deployment counterpart (already committed/clean)
- `d:\Development\Code\Flutter\flutter_app_template` — Flutter monorepo (Phase 03 in progress)
