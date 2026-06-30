# Postgres Template Migrations

This folder contains SQL Alembic version files that belong only to the
Postgres Template backend slice.

The global migration runner includes `migrations/versions` from this folder
only when `APP_PROFILE=postgres_template` selects the Postgres Template
definition. Shared provider-wide tables still live in the repository-level
`alembic/versions` tree.

Safe editing rules:
- Put Postgres Template-only SQL schema changes here.
- Keep shared provider-wide migrations in the global Alembic tree.
- Do not copy product-specific Felix migrations into this folder.
- App migration revisions normally chain within this folder. The startup runner
  applies global migrations first, so app tables may reference shared global
  tables such as `users` without using the global revision as `down_revision`.
