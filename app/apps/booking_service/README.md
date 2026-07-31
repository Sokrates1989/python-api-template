# Booking Service Backend Profile

## Purpose

This selected app package establishes the authenticated PostgreSQL foundation
for `booking_service` in the Python API template. Phase zero deliberately owns
no product routes or tables. Booking domain models, migrations, and endpoints
will be introduced by focused implementation slices after local and CI runtime
qualification is deterministic.

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

The phase-zero definition keeps database, Redis, and app-owned migration
requirements enabled while publishing no app-specific or shared routes. This
makes accidental template-demo APIs visible during review: any route added to
this profile must belong to an approved booking slice and must never use a
redundant `/api/` prefix.

## Verification

Run `pdm lock --check --project app/apps/booking_service` and the Python API
template's selected-app contract tests before deployment. Compare the public
runtime example with deployment-owned configuration. Exercise health, auth
configuration, and migration upgrade/downgrade through the BKG-004 quality
entrypoint. Keep later service routes relative to the API host and free of a
redundant `/api/` prefix.
