# Felix App Migrations

This folder contains SQL Alembic version files that belong only to the Felix
backend app slice.

The global migration runner includes `migrations/versions` from this folder
only when `APP_PROFILE=felix` selects the Felix app definition. Shared template
provider-wide tables still live in the repository-level `alembic/versions`
tree.

Safe editing rules:
- Put Felix-only SQL schema changes here.
- Put Felix-owned tables for shared feature runtimes here when Felix selects
  that feature, such as the SQL wellness tables.
- Keep provider-wide migrations in the global Alembic tree.
- App migration revisions normally chain within this folder. The startup runner
  applies global migrations first, so app tables may reference shared global
  tables such as `users` without using the global revision as `down_revision`.
