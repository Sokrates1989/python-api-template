"""Add flexible Felix check-in metadata columns.

Revision ID: felix_003_checkin_metadata
Revises: felix_002_rewards_state
Create Date: 2026-07-02 00:00:00.000000

Felix activity executions are stored as check-in rows with semantic tags and a
flexible metric map. The table remains app-owned even though the runtime model
is shared, so this migration lives in the Felix migration stream.
"""

from alembic import op
import sqlalchemy as sa


revision = "felix_003_checkin_metadata"
down_revision = "felix_002_rewards_state"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    """Return whether a table already has a named column.

    Args:
        table_name (str): Database table name to inspect.
        column_name (str): Column name to find.

    Returns:
        bool: True when the column exists on the table.

    Side Effects:
        Reads database column metadata through the Alembic bind.
    """
    columns = sa.inspect(op.get_bind()).get_columns(table_name)
    return any(column.get("name") == column_name for column in columns)


def upgrade() -> None:
    """Add flexible metadata columns to Felix-owned check-ins.

    Args:
        None.

    Returns:
        None.

    Side Effects:
        Adds tag, metric, and linked activity storage used by activity
        execution diary rows.
    """
    if not _column_exists("wellness_checkins", "tag_keys"):
        op.add_column(
            "wellness_checkins",
            sa.Column("tag_keys", sa.Text(), nullable=False, server_default="[]"),
        )
    if not _column_exists("wellness_checkins", "metrics"):
        op.add_column(
            "wellness_checkins",
            sa.Column("metrics", sa.Text(), nullable=False, server_default="{}"),
        )
    if not _column_exists("wellness_checkins", "activity_id"):
        op.add_column(
            "wellness_checkins",
            sa.Column("activity_id", sa.String(length=128), nullable=True),
        )


def downgrade() -> None:
    """Remove flexible metadata columns from Felix-owned check-ins.

    Args:
        None.

    Returns:
        None.

    Side Effects:
        Drops activity execution metadata from ``wellness_checkins``.
    """
    op.drop_column("wellness_checkins", "activity_id")
    op.drop_column("wellness_checkins", "metrics")
    op.drop_column("wellness_checkins", "tag_keys")
