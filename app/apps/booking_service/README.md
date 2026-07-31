# Booking Service Backend Profile

## Purpose

This generated app package selects the `postgresql` data profile for
`booking_service` in the Python API template. It includes the Python-owned, subject-scoped `/records` starter and its app-owned Alembic migration.

## Ownership

Template V2 owns every file listed in `.template_v2/ownership.json`. The
adjacent public-runtime manifest is derived from the same connected/auth recipe
plans as Flutter output. `.template_v2/backend_foundation.json` records the
exact validated Python contract revision and canonical source digest used for
composition. Runtime credentials, database URLs, provider secrets, and CORS
policy remain deployment-owned.

## Verification

Run `pdm lock --check --project app/apps/booking_service` and the Python API
template's selected-app contract tests before deployment. Compare the public
runtime example with deployment-owned configuration. Exercise authenticated records CRUD and migration upgrade/downgrade before deployment. Keep
service routes relative to the API host and free of a redundant `/api/` prefix.
