"""Create the shared SQL sync conflict log.

Revision ID: 010_create_sync_conflicts_table
Revises: 010_create_wellness_tables
Create Date: 2026-04-14 12:00:00.000000

The table is global because sync conflict capture is provider-wide
infrastructure. Feature tables such as wellness content belong in selected-app
migration streams under ``app/apps/<app_id>/migrations/versions``.
"""

from alembic import op
import sqlalchemy as sa


revision = "010_create_sync_conflicts_table"
down_revision = "010_create_wellness_tables"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    """Return whether a table already exists in the active schema.

    Args:
        table_name (str): Database table name to inspect.

    Returns:
        bool: True when the table is already present.

    Side Effects:
        Reads database metadata through the Alembic bind.
    """
    return sa.inspect(op.get_bind()).has_table(table_name)


def _index_exists(table_name: str, index_name: str) -> bool:
    """Return whether a table already has a named index.

    Args:
        table_name (str): Database table name to inspect.
        index_name (str): Index name to find.

    Returns:
        bool: True when the index exists on the table.

    Side Effects:
        Reads index metadata through the Alembic bind.
    """
    indexes = sa.inspect(op.get_bind()).get_indexes(table_name)
    return any(index.get("name") == index_name for index in indexes)


def _create_index_if_missing(index_name: str, columns: list[str]) -> None:
    """Create a sync-conflict index when it is not already present.

    Args:
        index_name (str): Name of the index to create.
        columns (list[str]): Ordered table columns included in the index.

    Returns:
        None.

    Side Effects:
        Creates an index on ``sync_conflicts`` when local legacy databases
        already have the table but are missing an index.
    """
    if not _index_exists("sync_conflicts", index_name):
        op.create_index(index_name, "sync_conflicts", columns, unique=False)


def _create_sync_conflict_indexes() -> None:
    """Ensure all sync-conflict lookup indexes exist.

    Args:
        None.

    Returns:
        None.

    Side Effects:
        Creates missing indexes on ``sync_conflicts``.
    """
    _create_index_if_missing("ix_sync_conflicts_user_id", ["user_id"])
    _create_index_if_missing("ix_sync_conflicts_op_id", ["op_id"])
    _create_index_if_missing(
        "ix_sync_conflicts_user_detected_at",
        ["user_id", "detected_at"],
    )


def upgrade() -> None:
    """Create the shared sync conflict log table.

    Args:
        None.

    Returns:
        None.

    Side Effects:
        Adds ``sync_conflicts`` and lookup indexes used by shared sync
        services.
    """
    if _table_exists("sync_conflicts"):
        _create_sync_conflict_indexes()
        return

    op.create_table(
        "sync_conflicts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("op_id", sa.String(length=128), nullable=False),
        sa.Column("feature", sa.String(length=64), nullable=True),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=255), nullable=False),
        sa.Column(
            "detected_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("result_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    _create_sync_conflict_indexes()


def downgrade() -> None:
    """Drop the shared sync conflict log table.

    Args:
        None.

    Returns:
        None.

    Side Effects:
        Removes ``sync_conflicts`` and its indexes.
    """
    op.drop_index("ix_sync_conflicts_user_detected_at", table_name="sync_conflicts")
    op.drop_index("ix_sync_conflicts_op_id", table_name="sync_conflicts")
    op.drop_index("ix_sync_conflicts_user_id", table_name="sync_conflicts")
    op.drop_table("sync_conflicts")
