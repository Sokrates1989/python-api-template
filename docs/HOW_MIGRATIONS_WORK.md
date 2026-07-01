# How Alembic Migrations Work

This project has two SQL migration streams:

- Global provider-wide migrations in `alembic/versions/`.
- Selected-app migrations in `app/apps/<app_id>/migrations/versions/`.

Use the global stream only for schema that every SQL app profile needs. Product
tables, selected-feature tables, product indexes, and app data migrations belong
inside the owning app slice.

## Quick Answers

**How does Alembic know what ran?**  
Alembic stores the current revision in a version table. The global stream uses
`alembic_version`. Selected app streams use app-specific tables such as
`alembic_version_felix`.

**Does Alembic run every file in a directory?**  
No. Alembic follows the revision chain from the current revision to the target
head and runs only pending migrations in that chain.

**Where should a product migration go?**  
Use `app/apps/<app_id>/migrations/versions/` and declare that folder in the app
definition with `migration_version_locations=("migrations/versions",)`.

## Runtime Migration Order

On startup, SQL-backed apps run migrations in this order:

1. Global provider-wide migrations from `alembic/versions/`.
2. Selected app migrations declared by
   `BackendAppDefinition.migration_version_locations`.

No app migration location is active unless the selected app definition declares
it.

## Global Migration Example

Use `alembic/versions/` for schema that intentionally affects every SQL app
profile, such as provider-wide user infrastructure.

```python
"""
Create shared user profile table.

Revision ID: 001_shared_users
Revises: None
"""
from alembic import op
import sqlalchemy as sa

revision = "001_shared_users"
down_revision = None


def upgrade() -> None:
    """
    Apply the shared user table migration.

    Args:
        None.

    Returns:
        None.

    Side Effects:
        Creates the provider-wide ``users`` table.
    """
    op.create_table(
        "users",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("email", sa.String(), nullable=True),
    )


def downgrade() -> None:
    """
    Revert the shared user table migration.

    Args:
        None.

    Returns:
        None.

    Side Effects:
        Drops the provider-wide ``users`` table.
    """
    op.drop_table("users")
```

## App Migration Example

Use `app/apps/<app_id>/migrations/versions/` for app-owned tables.

```text
app/apps/felix/migrations/versions/felix_002_rewards_state.py
```

Declare the app migration folder in `app/apps/felix/definition.py`:

```python
BackendAppDefinition(
    ...,
    migration_version_locations=("migrations/versions",),
)
```

The runner resolves the relative path against `app/apps/felix/` and tracks the
stream in `alembic_version_felix`.

## Revision Chains

Each migration points to its predecessor:

```python
revision = "003_add_priority"
down_revision = "002_add_category"
```

Alembic applies pending revisions in chain order. If two migrations share the
same `down_revision`, you have a branch and may need an Alembic merge revision.

## Creating A Migration

For global provider-wide changes:

```bash
docker compose exec app pdm run alembic revision -m "Add shared table"
```

For app-owned migrations, create the migration file under the selected app's
`migrations/versions/` folder and connect it to that app stream's revision
chain. Review the file before running it.

## Review Checklist

- Does the table or column belong to one product? Put it in the app migration
  stream.
- Does the migration mention Felix, rewards, Startlist, streaks, Sonnen, or
  product copy? Put it in the app migration stream.
- Does every SQL app need this schema? The global stream may be appropriate.
- Did you update `migration_version_locations` for a new app migration folder?
- Did you test startup or run the targeted migration smoke test?
- Did every migration helper include a docstring?

## Manual Commands

```bash
# Apply pending migrations in the running container.
docker compose exec app pdm run alembic upgrade head

# Show the current global migration revision.
docker compose exec app pdm run alembic current

# Show global migration history.
docker compose exec app pdm run alembic history
```

App migration streams are normally run by the project migration runner during
startup because it knows which backend app is selected.
