# Backend Deployment Selection

## Purpose

`compose-files.txt` selects the shared API and Redis services plus the
`postgres` provider service and this app's public override.

## Ownership

The generated public-runtime example contains only validated provider fields
read by the API template. The deployment operator owns environment loading,
credentials, database URLs, signing keys, network exposure, backups, and
provider lifecycle. Set `POSTGRES_DATA_ROOT` and `PGADMIN_DATA_ROOT` to app-isolated host paths.

## Verification

Resolve the listed Compose files from the Python API template root, merge only
the public example values into deployment-owned configuration, and inspect the
result before starting services. Never add credentials to the generated public
example.
