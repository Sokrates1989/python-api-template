# Backend App Slices

This directory contains backend app slices. Each slice is a self-contained app
that owns its own routes, services, schemas, configuration, and deployment
overrides.

## Adding a new backend app

The canonical way to add a new app is to copy `template_app` and rename it.

### 1. Copy the template app

```bash
cp -r app/apps/template_app app/apps/<new_app>
```

On Windows, copy the folder with the file manager or `Copy-Item` and then
continue inside WSL or `quick-start.ps1`.

### 2. Rename everything inside the copied folder

Inside `app/apps/<new_app>` replace:

- `template_app` → `<new_app>`
- `TemplateApp` → `<NewApp>`
- `TEMPLATE_APP` → `<NEW_APP>`
- `Template App` → `<New App>`

Also rename the environment file:

```bash
mv app/apps/<new_app>/env/.env.template_app app/apps/<new_app>/env/.env.<new_app>
```

### 3. Update app metadata

Edit `app/apps/<new_app>/config/app_metadata.py`:

- `app_id`
- `display_name`
- `wellness_mount_prefix` / `wellness_public_prefix` (if relevant)

### 4. Update `compose.override.yml`

Use the `POSTGRES_DATA_ROOT` and `PGADMIN_DATA_ROOT` environment variables
injected by `quick-start.sh`. This pattern works on all platforms:

```yaml
# POSTGRES_DATA_ROOT and PGADMIN_DATA_ROOT are injected by quick-start.sh.
# On Windows/WSL2 they resolve to a WSL2-native path so that PostgreSQL and
# pgAdmin can chown their data directories (NTFS DrvFs mounts do not allow
# Linux ownership changes). On macOS/Linux they resolve to the standard
# project-relative .docker/apps/<new_app>/ path.

services:
  postgres:
    volumes:
      - ${POSTGRES_DATA_ROOT}:/var/lib/postgresql/data

  pgadmin:
    volumes:
      - ${PGADMIN_DATA_ROOT}:/var/lib/pgadmin
```

`quick-start.sh` automatically:
- detects Windows/WSL2 vs macOS/Linux
- sets the correct OS-native path
- pre-creates the directories with correct ownership
- `chown`s the pgadmin dir to uid 5050 (the pgAdmin container user)

If you pre-create directories manually on WSL2, you must also run:

```bash
sudo chown -R 5050:5050 /home/<wsl_user>/.docker-data/python-api-template/<new_app>/pgadmin
```

pgAdmin writes `servers.json` and `pgpassfile` on startup and will fail with
`Permission denied` if the directory is owned by any other uid.

**Do not hardcode `/home/<user>/.docker-data/...` or `../../.docker/apps/...`
paths in `compose.override.yml`.** Always use the env vars.

### 5. Do NOT create or copy `/.docker/apps/<new_app>`

The directory `.docker/apps/<new_app>` is **runtime data**. It is **not** part
of the app source. It will be created automatically on first startup by the
PostgreSQL container with the correct ownership.

Never manually create, copy, or delete this directory from Windows PowerShell.
That will create ownership/permission conflicts and break Docker Desktop's
WSL bind-mount broker.

### 6. Start the stack

Always start the new app via the quick-start script:

```bash
./quick-start.sh
# Windows:
# .\quick-start.ps1
```

Select the new app, then start the backend.

## What to copy

Copy these source-controlled files only:

- `config/`
- `definition.py`
- `deployment/`
- `env/.env.template_app`
- `pyproject.toml`
- `pdm.lock`
- `routes/`
- `schemas/`
- `services/`
- `__init__.py`

## What NOT to copy

- `__pycache__/`
- `.docker/` or `.docker/apps/template_app/` (runtime data)
- Any generated container data, build caches, or logs
- `env/.env.template_app` should be renamed, not kept as-is

## Troubleshooting

### `Operation not permitted` / `chmod failed`

The `.docker/apps/<new_app>` directory was created with wrong ownership.

Fix: remove it from WSL and start the stack again:

```bash
wsl -d <your-distro>
rm -rf /mnt/d/Development/Code/python/python-api-template/.docker/apps/<new_app>
```

Then restart via `quick-start.ps1` / `quick-start.sh`.

### `mkdir ...: file exists` after Docker Desktop restart

Docker Desktop's WSL bind-mount broker cached a stale entry. Remove it from
WSL, then restart the stack. Do not create or delete the directory from Windows.
