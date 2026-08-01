# Booking Service Backend Profile

## Purpose

This selected app package owns the authenticated PostgreSQL backend for
`booking_service`. BKG-100 introduced the authenticated coarse identity;
BKG-101 adds app-owned subjects, organizations, memberships, tenant-bound
membership roles, dual-gated platform access, and audited organization
lifecycle. Booking, availability, payments, and notification delivery remain
later focused slices.

## Ownership

Template V2 owns every file listed in `.template_v2/ownership.json`. The
adjacent public-runtime manifest is derived from the same connected/auth recipe
plans as Flutter output. `.template_v2/backend_foundation.json` records the
exact validated Python contract revision and canonical source digest used for
composition. Detached neutral starter files remain recorded in the ownership
manifest as lifecycle history, but they are not part of the product target.
Runtime credentials, database URLs, provider secrets, and CORS policy remain
deployment-owned.

## Product boundary

The selected definition keeps database, Redis, and app-owned migration
requirements enabled while publishing no shared routes. The BKG-100 principal
accepts only verified Keycloak access tokens, requires a non-empty `sub`, and
reads the four independent roles exclusively from
`resource_access[KEYCLOAK_CLIENT_ID].roles`. Realm-only, unknown, malformed,
or unconfigured roles grant nothing. The response contains only `subject_id`
and deterministic `roles`; it never returns raw claims or provider secrets.

`GET /v1/me/context` creates only the app-owned subject primitive and returns
active memberships whose PostgreSQL roles intersect the verified coarse roles.
The client-provided organization selection is never an authorization input.
Member reads require an explicit organization predicate, hide absent/foreign
scope as `404`, and reject known suspended scope as `403`.

Platform organization list/create/suspend/reactivate operations require both
the `platform_admin` coarse role and active `booking_platform_access`. Lifecycle
updates lock the organization, require an expected revision, preserve history,
and write a sanitized audit event in the same transaction. Revision conflicts
return retryable `409`. All routes are rooted at `/v1`; `/api` is forbidden.

Every later route must belong to an approved booking slice and must never use
a redundant `/api/` prefix. Keycloak administration and production realm
bootstrap remain deployment-owned.

## Verification

Run `pdm lock --check --project app/apps/booking_service` and the Python API
template's selected-app contract tests before deployment. Compare the public
runtime example with deployment-owned configuration. Exercise health, auth
configuration, and migration upgrade/downgrade through the BKG-004 quality
entrypoint:

```powershell
python tools/booking_service_quality.py run
```

The command builds the Python 3.13 app image, starts disposable PostgreSQL,
Redis, and Keycloak fixtures, creates matching frontend client roles, verifies
issuer/audience plus four real `/v1/me/identity` projections, seeds two isolated
organizations from the projected non-personal subjects, and proves active
context, explicit multi-membership, dual platform access, foreign-scope `404`,
suspension `403`, reactivation, and anonymous `401`. It also runs focused
contracts and the route guard, scans logs for invocation secrets, and removes
its containers, network, volume, and locally built images.
Keep later service routes relative to the API host and free of a redundant
`/api/` prefix.
