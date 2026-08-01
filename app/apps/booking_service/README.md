# Booking Service Backend Profile

## Purpose

This selected app package owns the authenticated PostgreSQL backend for
`booking_service`. BKG-100 introduces the first product route,
`GET /v1/me/identity`, without adding a booking table or tenant state. Later
domain models, migrations, and endpoints remain focused implementation slices.

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
issuer/audience plus four real `/v1/me/identity` projections, proves anonymous
`401`, runs the focused contracts and route guard, scans logs for invocation
secrets, and removes its containers, network, volume, and locally built images.
Keep later service routes relative to the API host and free of a redundant
`/api/` prefix.
