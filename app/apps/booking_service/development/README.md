# Persistent Booking Service development runtime

## Purpose

This profile runs the selected Booking Service API, PostgreSQL, and Redis while
reusing the separately managed Keycloak instance at `http://localhost:9090`.
It never creates or bootstraps another Keycloak service. Port `9094` remains
reserved for the disposable automated qualification stack.

## Prerequisites

From `D:\Development\Code\keycloak`, start the existing stack and reconcile
the local-only realm:

```powershell
docker compose up -d
python tools\booking_local_realm.py check
python tools\booking_local_realm.py reconcile
python tools\booking_local_realm.py verify
```

The Keycloak `.env` remains deployment-owned and contains no Booking-specific
demo credential. Reconciliation does not read or reset demo-user passwords. It
writes the confidential backend-client value and a non-secret demo-user subject
manifest to its ignored `data/local-realms` path.

Set or rotate browser-test credentials explicitly. This operation prompts
twice for a distinct local-only password of at least 16 characters per user and
retains each value only in process and Admin API request memory:

```powershell
python tools\booking_local_realm.py credentials
```

## Start and stop

From the Python repository root, create the ignored development environment,
replace every placeholder with a unique URL-safe local value, and start only
the API/database/cache profile:

```powershell
Copy-Item `
  app\apps\booking_service\development\.env.example `
  app\apps\booking_service\development\.env

docker compose `
  --project-name booking-service-local `
  --env-file app\apps\booking_service\development\.env `
  --file app\apps\booking_service\development\compose.yml `
  up --build --detach
```

Seed the persistent database with two neutral companies and role-compatible
memberships. The organization administrator belongs to both companies; the
worker and customer belong only to the North fixture. The command reads the
non-secret reconciler-produced subject manifest and passes only validated
opaque subjects to the running API container. It never reads or uses demo-user
credentials:

```powershell
python tools\booking_service_local_seed.py
```

The seed is idempotent. Re-run it after recreating the database volume or after
reconciling replacement Keycloak demo users.

Inspect the service state and the selected API metadata:

```powershell
docker compose `
  --project-name booking-service-local `
  --env-file app\apps\booking_service\development\.env `
  --file app\apps\booking_service\development\compose.yml `
  ps

Invoke-RestMethod http://localhost:8084/health
Invoke-RestMethod http://localhost:8084/openapi.json
```

Stop the API stack without touching Keycloak or the retained PostgreSQL volume:

```powershell
docker compose `
  --project-name booking-service-local `
  --env-file app\apps\booking_service\development\.env `
  --file app\apps\booking_service\development\compose.yml `
  down
```

Add `--volumes` only when intentionally deleting local Booking Service data.
The operation still cannot affect the separately managed Keycloak stack.

## Safety and ownership

- Never commit `development/.env` or the backend-client secret.
- Keep all API routes service-root relative; `/api` and `/api/*` are forbidden.
- Bind local ports to loopback and keep debug/body/header logging disabled.
- Run the disposable paired qualifier separately; it owns `9094` and removes
  all of its own containers, images, networks, and volumes.
