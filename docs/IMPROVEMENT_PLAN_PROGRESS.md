# Improvement Plan Progress

Last updated: 2026-03-03

## Current Step

- Phase 5 / Step 2: Swarm deployment alignment and end-to-end restore drills (completed).
- Parallel hardening: Phase 6 / Step 2 startup probes and structured diagnostics (completed).
- Parallel hardening: Phase 6 / Step 3 release checklist and safe verification flow (completed).
- Parallel hardening: Phase 6 / Step 4 deprecation cleanup and release polish (completed).
- Parallel hardening: Phase 6 / Step 5 release-candidate closeout and commit grouping (completed).

## Phase Status

### Phase 0: Truth alignment and safety hardening

- [x] Support matrix aligned to official backends (`postgresql/postgres`, `neo4j`, `mongodb`) with legacy compatibility notes for `mysql` and `sqlite`.
- [x] Startup fails fast on DB initialization and SQL migration failures.
- [x] Lock check defaults to fail-closed behavior.
- [x] Sensitive HTTP logging disabled by default with explicit opt-in flags.
- [x] Stale duplicate runtime files removed (legacy handlers/routes).

### Phase 1: Architecture refactor for extensibility

- [x] Introduced first domain port: `UserRepository` (`app/backend/ports/user_repository.py`).
- [x] Added provider adapters + factory registry:
  - `app/backend/adapters/user_repository_factory.py`
- [x] Switched shared user facade to port/adapters:
  - `app/backend/services/user_service.py`
- [x] Extend ports/adapters pattern to `ExampleRepository`.
- [x] Extend ports/adapters pattern to backup/restore capability contracts.
- [x] Replace route-level provider branching with factory-based capability checks.

### Phase 2: SQL model/migration consolidation

- [x] Shared SQL base introduced (`app/models/sql/base.py`).
- [x] Verify all SQL models are consistently imported through shared metadata in Alembic.
- [x] Add migration smoke checks for each SQL backend profile used in CI.

### Phase 3: Quality gates and CI reliability

- [x] Added and updated unit tests for adapterized user flow.
- [x] Add provider contract tests for repository interfaces.
- [x] Add integration test matrix for `postgresql`, `neo4j`, `mongodb`.
- [x] Gate image build/deploy on lint/type/test jobs.
- [x] Introduce initial pytest-native contract test structure while keeping unittest baseline.
- [x] Migrate first unittest batch to pytest-native unit tests (`qa_pytest/unit`) and run them in CI.
- [x] Validate unittest + pytest on PostgreSQL profile.
- [x] Validate unittest + pytest on MongoDB profile.
- [x] Resolve Neo4j local bind-mounted credential drift for full local matrix parity.
- [x] Validate unittest + pytest on Neo4j profile.

### Phase 4: MongoDB-ready plugin model

- [x] Add explicit provider capability contract (`supports_transactions`, `supports_migrations`, etc.).
- [x] Add MongoDB example repository adapter/service parity for `/examples` routes.
- [x] Remove exposed built-in `/backup/*` routes from API template and keep external lock orchestration only.
- [x] Complete external backup/restore integration flow and verify contracts against live PostgreSQL profile.
- [x] Implement parity adapters for currently supported shared template domains (`users`, `examples`, provider stats/capabilities).
- [x] Enforce parity via shared contract test suite.
- [x] Validate shared capability contracts on local `postgresql`, `neo4j`, and `mongodb` profiles.

## Detailed Roadmap (Phases 0-6)

### Phase 0: Truth alignment and safety hardening (completed)

- Align support matrix and setup/docs defaults.
- Fail fast on startup/init/migration errors.
- Default to fail-closed lock behavior.
- Disable sensitive HTTP payload/header logging by default.
- Remove stale duplicate runtime files and legacy route bindings.

### Phase 1: Architecture refactor for extensibility (completed)

- Introduce domain ports and provider adapters.
- Keep routes provider-agnostic through factory/registry binding.
- Move provider branching to adapter/factory layers.
- Preserve provider capability metadata via explicit contracts.

### Phase 2: SQL model/migration consolidation (completed)

- Unify SQL models under shared metadata base.
- Ensure Alembic imports all SQL model metadata consistently.
- Add migration checks to quality gates.

### Phase 3: Quality gates and CI reliability (completed)

- Add unittest + pytest quality layers.
- Add provider contract tests.
- Add DB-profile matrix (`postgresql`, `neo4j`, `mongodb`) in CI.
- Gate build/deploy after lint/type/test completion.

### Phase 4: MongoDB-ready plugin model (completed)

- Add provider capability profile contract.
- Add MongoDB parity for shared template domains.
- Validate capability contract parity with shared tests across all supported profiles.

### Phase 5: External backup-restore integration (completed)

- Keep backup/restore execution in dedicated external services/repos.
- Keep API responsibilities limited to lock/status/capability boundaries needed by external orchestrator.
- [x] Add target discovery endpoint `GET /database/provider-info` (db profile + capabilities + lock state).
- [x] Enforce target provider preflight in external `backup-restore` routes before lock/restore (`sql`, `neo4j`, `mongodb`).
- [x] Update `swarm-backup-restore` stack/env templates with Mongo runtime settings and optional `backup_mongodb` service (`docker compose config` validated).
- [x] Add deterministic local drill runner for provider contract checks: `local-deployment/run-phase5-drill.ps1`.
- [x] Harden drill runner with profile-aware readiness wait and PowerShell basic parsing compatibility to avoid interactive web parsing prompts.
- [x] Fix drill runner command argument handling and service-state parsing bugs.
- [x] Add fail-fast diagnostics for non-running app containers (compose status + logs).
- [x] Isolate drill profile host ports to reduce collisions with local services (configurable `REDIS_PORT`, Neo4j host ports, drill-specific env values).
- [x] Validate full local drill matrix success (`postgresql`, `neo4j`, `mongodb`) using:
  - `.\local-deployment\run-phase5-drill.ps1 -Profile all -NoBuild -TimeoutSeconds 300`
- Align API contract with:
  - `D:\Development\Code\python\backup-restore`
  - `D:\Development\Code\swarm\swarm-backup-restore`
- Add/verify MongoDB support and run integration drills from backup service against template DB profiles.

### Phase 6: Operational hardening and release readiness (planned)

- Added `.gitattributes` with explicit line-ending policy for `*.sh`/`*.ps1` and source/config files.
- Normalized `setup/setup.sh` to ASCII-safe output strings to remove mojibake risk.
- Added provider startup probe module with provider-specific checks:
  - SQL connectivity + dialect/model metadata summary
  - Neo4j connectivity + component/version check
  - MongoDB connectivity + required startup index verification (`users`, `examples`)
- Lifecycle startup now records structured startup/shutdown diagnostics and fails fast when provider probe fails.
- Migration runner now emits structured diagnostics and warnings instead of print output (`app/backend/database/migrations.py`).
- Added unit tests for startup probe coverage (`qa_pytest/unit/test_startup_probe.py`).
- Added operations note for startup probes and health diagnostics (`docs/STARTUP_PROBES.md`).
- Added release checklist (`docs/RELEASE_CHECKLIST.md`).
- Added safe release verification runner (`local-deployment/verify-release-safe.ps1`) and validated it locally.
- Added one-command local release gate runner (`local-deployment/run-release-gate.ps1`) combining safe checks + provider drill matrix.
- Added health payload regression tests (`qa_pytest/unit/test_health_endpoint_payload.py`).
- Migrated startup/shutdown wiring from deprecated `@app.on_event` hooks to FastAPI lifespan context (`app/api/config/lifecycle.py`, `app/main.py`).
- Validated release gate end-to-end (`.\local-deployment\run-release-gate.ps1 -NoBuild`) and targeted runtime pytest for health payload contract.
- Removed Pydantic V2 class-config deprecations in API settings/schemas (`SettingsConfigDict`/`ConfigDict` migration).
- Re-validated targeted runtime pytest with warnings eliminated for lifecycle/settings/schema deprecations.
- CI matrix now includes explicit provider contract endpoint checks per profile (`/health`, `/database/provider-info`, `/database/lock`, `/database/unlock`).
- Updated setup/operations docs to align with current host port and health payload diagnostics (`docs/QUICK_START.md`, `docs/DOCKER_SETUP.md`, `docs/ARCHITECTURE.md`).
- Completed docs drift pass for host-facing URLs and startup lifecycle examples (`README.md`, `docs/DOCKER_SETUP.md`, `docs/QUICK_START.md`, migration docs).
- Re-validated strict safe checks and full provider drill matrix locally:
  - `.\local-deployment\verify-release-safe.ps1 -Strict`
  - `.\local-deployment\run-phase5-drill.ps1 -Profile all -NoBuild -TimeoutSeconds 300`
- Normalize script encodings and line endings across setup/runtime scripts.
- Add startup probes and structured provider-specific diagnostics.
- Add release checklist and smoke tests for local + CI + swarm deployment paths.
