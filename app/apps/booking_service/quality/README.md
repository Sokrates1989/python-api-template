# Booking Service quality runtime

## Purpose

This directory defines the disposable BKG-004 runtime: the selected Python
3.13 API image, PostgreSQL 16, Redis 7, Keycloak 26.0, and the credential-free
Keycloak bootstrap summary. The stack uses named Compose volumes for temporary
PostgreSQL data and the generated BKG-103 identity-administration client secret;
the quality runner removes both volumes, containers, network, and locally built
images after an automated run.

The bootstrap assigns the confidential `booking-service-backend` service
account only the selected `realm-management` user/client lookup and role-mapping
permissions. Its generated secret is written into the ephemeral secret volume,
which the unprivileged API mounts read-only. The summary, process arguments,
logs, and tracked files never contain that value. Production must use its
deployment secret manager instead of this disposable handoff.

Focused repository tests receive read-only mounts for `tests`, `tools`,
`keycloak`, `template_v2`, the canonical booking pair contract, and the exact
public source paths hashed by the backend-foundation contract. The runner does
not mount the repository root, `.git`, local `.env`, mounted data, logs, or
backups into the quality container.

The Compose file owns service wiring only. `tools/booking_service_quality.py`
is the stable command wrapper; the focused `tools/booking_quality/` modules own
configuration, orchestration, health/auth assertions, seeded-role token checks,
two-tenant context/isolation/lifecycle proofs, scoped membership grants,
last-admin lockout, missing-subject compensation, provider-backed role
transitions, focused tests, route guards, log scanning, and guaranteed teardown.

## Automated run

From the Python repository root:

```powershell
python tools/booking_service_quality.py run
```

The command generates infrastructure and proof-user passwords in memory. It
never prints or writes them, validates the stack, and tears everything down in
a `finally` path. The public local endpoints are API `8084`, Keycloak `9094`,
PostgreSQL `5544`, and Redis `6384`; each can be overridden through the public
port variables documented by `python tools/booking_service_quality.py --help`.

## Interactive development

`up` and `verify` require the four proof-user passwords to exist only in the
operator environment so a later command can authenticate the same identities.
They also require the five infrastructure secrets so the later log scan checks
the exact values used by the running services:

```powershell
$env:BOOKING_QUALITY_PLATFORM_ADMIN_PASSWORD = '<local-only value>'
$env:BOOKING_QUALITY_ORGANIZATION_ADMIN_PASSWORD = '<local-only value>'
$env:BOOKING_QUALITY_WORKER_PASSWORD = '<local-only value>'
$env:BOOKING_QUALITY_CUSTOMER_PASSWORD = '<local-only value>'
$env:BOOKING_QUALITY_DB_PASSWORD = '<16+ URL-safe local-only value>'
$env:BOOKING_QUALITY_KEYCLOAK_ADMIN_PASSWORD = '<local-only value>'
$env:BOOKING_QUALITY_ADMIN_API_KEY = '<local-only value>'
$env:BOOKING_QUALITY_RESTORE_API_KEY = '<local-only value>'
$env:BOOKING_QUALITY_DELETE_API_KEY = '<local-only value>'
python tools/booking_service_quality.py up
python tools/booking_service_quality.py verify
python tools/booking_service_quality.py down
```

Never commit those values or paste them into evidence. Usernames are neutral
defaults (`booking-platform-admin`, `booking-organization-admin`,
`booking-worker`, and `booking-customer`) and may be overridden with their
matching `_USER` variables. Runtime summaries contain usernames, roles, public
ports, and counts only.

## Safe editing

- Keep all API routes service-root relative; `/api` and `/api/*` are forbidden.
- Keep `/records` absent because it belongs only to the detached neutral proof.
- Keep seed subjects derived only from real local identity projection; never
  pass or persist a bearer token in the seed command.
- Keep organization A/B identifiers neutral and prove foreign lookup, suspend,
  context removal, reactivation, and context restoration in every live run.
- Do not add provider credentials, passwords, tokens, or personal identities.
- Pin image/runtime versions and update tests when service wiring changes.
- Run `down` after interrupted interactive work; it is safe without passwords.
