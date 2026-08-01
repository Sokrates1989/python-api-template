# Backend Deployment Selection

## Purpose

`compose-files.txt` selects the shared API and Redis services plus the
`postgres` provider service and this app's public override.

## Ownership

The generated public-runtime example contains only validated provider fields
read by the API template. The deployment operator owns environment loading,
credentials, database URLs, signing keys, network exposure, backups, and
provider lifecycle. Set `POSTGRES_DATA_ROOT` and `PGADMIN_DATA_ROOT` to app-isolated host paths.

BKG-103 identity-role delivery additionally requires a dedicated confidential
Keycloak service account. Supply its public client ID through
`KEYCLOAK_ADMIN_CLIENT_ID` and mount its secret through
`KEYCLOAK_ADMIN_CLIENT_SECRET_FILE`; never place the secret in the generated
public runtime example. Grant only the permissions required to read the target
subject and Booking client roles and to map those roles. Missing configuration
leaves database-first invitations visible for explicit retry or compensation.

## Verification

Resolve the listed Compose files from the Python API template root, merge only
the public example values into deployment-owned configuration, and inspect the
result before starting services. Never add credentials to the generated public
example.
