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
python tools\booking_local_realm.py login-check
```

The reconcile and login commands read `BOOKING_LOCAL_DEMO_PASSWORD` from the
ignored Keycloak `.env`. They do not print it. The reconciler also writes the
confidential backend-client value to its ignored `data/local-realms` path.

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
memberships. The command reads `BOOKING_LOCAL_DEMO_PASSWORD` from the current
process when present; otherwise it prompts without echo. It sends the password
only to the fixed loopback Keycloak realm and passes only opaque subjects to
the running API container:

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
