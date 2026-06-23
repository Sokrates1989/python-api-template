# Local Deployment Directory

This directory contains Docker Compose files for **local development**.

## Files

- **`docker-compose.yml`** - Base configuration (app + Redis)
- **`docker-compose.postgres.yml`** - PostgreSQL database extension
- **`docker-compose.neo4j.yml`** - Neo4j database extension
- **`docker-compose.mongodb.yml`** - MongoDB database extension
- **`../tools/core-pdm-manager/docker/docker-compose.pdm-manager.yml`** - Python dependency management (recommended)

## Usage

### Via Quick-Start Scripts (Recommended)

The easiest way to start local development:

```bash
# Linux/Mac
./quick-start.sh

# Windows
.\quick-start.ps1
```

These scripts automatically select the correct compose files based on your `.env` configuration.

### Manual Docker Compose

If you prefer to use Docker Compose directly:

#### PostgreSQL (Local)
```bash
docker compose -f local-deployment/docker-compose.postgres.yml -f local-deployment/docker-compose.yml --env-file .env up
```

#### Neo4j (Local)
```bash
docker compose -f local-deployment/docker-compose.neo4j.yml -f local-deployment/docker-compose.yml --env-file .env up
```

#### MongoDB (Local)
```bash
docker compose -f local-deployment/docker-compose.mongodb.yml -f local-deployment/docker-compose.yml --env-file .env up
```

#### External Database
```bash
docker compose -f local-deployment/docker-compose.yml --env-file .env up
```

### Phase 5 Provider Drill (Postgres + Neo4j + MongoDB)

Use the checked-in drill script to verify the external backup/restore contract endpoints:

```powershell
.\local-deployment\run-phase5-drill.ps1 -Profile all
```

Options:

- `-Profile postgres|neo4j|mongodb|all`
- `-TimeoutSeconds 300` (override readiness timeout)
- `-NoBuild` (skip image rebuild during drill)
- `-KeepLastProfileRunning` (keep final profile stack running for manual checks)

The drill validates, per profile:

1. `GET /health` reachable (HTTP 200)
2. `GET /database/provider-info` matches expected provider profile
3. `POST /database/lock` succeeds
4. `POST /database/unlock` succeeds

The script uses `.env.drill.postgres`, `.env.drill.neo4j`, and `.env.drill.mongodb`.

### Release Gate (Safe Checks + Drill)

Run the one-command local release gate:

```powershell
.\local-deployment\run-release-gate.ps1 -NoBuild
```

Options:

- `-SkipSafeChecks` (run drill only)
- `-SkipDrill` (safe checks only)
- `-DrillTimeoutSeconds 300` (override drill readiness timeout)

## Volume Mounts

The compose files mount several directories for live development:

- **`../app`** - Application code (live reload)
- **`../alembic`** - Database migrations
- **`../backups`** - Database backups (persisted to host)
- **`../app/mounted_data`** - Mounted data directory

## Ports

Default ports (configurable via `.env`):

- **API**: 8081 (or value from `PORT` in `.env`)
- **PostgreSQL**: 5433
- **Neo4j Bolt**: 7687
- **Neo4j HTTP**: 7474
- **MongoDB**: 27017
- **Redis**: 6379

## Dependencies

The compose files depend on:

- **`.env`** file in project root (created by setup)
- **`Dockerfile`** in project root
- **`interactive-scripts/Dockerfile`** for dependency management

## Development Workflow

1. **Start services**: `./quick-start.sh` (or `.ps1`)
2. **Make code changes**: Files are live-reloaded
3. **View logs**: `docker compose logs -f app`
4. **Stop services**: `docker compose down`
5. **Clean restart**: `docker compose down -v && docker compose up --build`

## Troubleshooting

### Port Already in Use
Change the `PORT` value in your `.env` file.

### Database Connection Issues
- Check that database service is healthy: `docker compose ps`
- Verify credentials in `.env` match the compose file
- For external databases, ensure `DB_HOST` points to correct server

### Volume Permission Issues
On Linux, you may need to adjust ownership:
```bash
sudo chown -R $USER:$USER backups/
```

### WSL + Docker Desktop Bind Mount Issues

When running on Windows with Docker Desktop's WSL2 backend, the bind-mount
broker can get into a stale state if the `/.docker/apps/<app_id>/postgres-data`
directory is manually created or deleted from Windows/PowerShell instead of
being created by the container on first startup.

Root cause: PostgreSQL (`initdb`) and pgAdmin both require `chmod`/`chown` on
their data directories. NTFS DrvFs mounts (`/mnt/d/...`) do not support Linux
ownership changes. Any postgres or pgadmin bind mount must point to a WSL2-native
path (e.g. `/home/<user>/.docker-data/...`) not a Windows drive path.

Symptoms:
- `postgres-1 | initdb: error: could not change permissions of directory "/var/lib/postgresql/data": Operation not permitted`
- `pgadmin-1  | chmod: /var/lib/pgadmin/pgpassfile: Operation not permitted`
- `mkdir /mnt/d/.../.docker/apps/<app_id>: file exists`
- `mkdir /run/desktop/mnt/host/wsl/docker-desktop-bind-mounts/...: file exists`

**Fix:**
1. Stop the compose project: `docker compose -p <project> down -v`
2. Shut down WSL completely to flush the DrvFs metadata cache:
   ```powershell
   wsl --shutdown
   ```
3. Remove the stale directory from **WSL** (run after WSL restarts):
   ```bash
   wsl -d <your-distro>
   rm -rf /mnt/d/Development/Code/python/python-api-template/.docker/apps/<app_id>
   ```
   Or pre-create it cleanly:
   ```bash
   mkdir -p /mnt/d/.../path/to/.docker/apps/<app_id>/postgres-data
   mkdir -p /mnt/d/.../path/to/.docker/apps/<app_id>/pgadmin
   ```
4. Restart the stack via the quick-start script:
   ```bash
   ./quick-start.sh
   # Windows:
   # .\quick-start.ps1
   ```

**Prevention:**
- Do not manually create or copy `/.docker/apps/<app_id>/` when adding a new app.
- Use the app slice copy instructions in `app/apps/README.md`.
- Always start the stack through `quick-start.sh` or `quick-start.ps1`.
