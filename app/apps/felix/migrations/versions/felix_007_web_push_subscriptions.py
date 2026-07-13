"""Create Felix account-owned Web Push subscription storage.

Revision ID: felix_007_web_push_subscriptions
Revises: felix_006_version_width
Create Date: 2026-07-13 00:00:00.000000

The SQL table stores browser delivery material for authenticated Felix users.
A fixed-width endpoint digest provides an index-safe idempotency key while the
full opaque endpoint remains available for later delivery and revocation.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "felix_007_web_push_subscriptions"
down_revision = "felix_006_version_width"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    """Return whether a SQL table already exists.

    Args:
        table_name (str): Database table name to inspect.

    Returns:
        bool: True when the current database owns the table.

    Side Effects:
        Reads database metadata through the Alembic bind.
    """
    return sa.inspect(op.get_bind()).has_table(table_name)


def _index_exists(table_name: str, index_name: str) -> bool:
    """Return whether an existing table owns a named index.

    Args:
        table_name (str): Existing database table name.
        index_name (str): Index name to find.

    Returns:
        bool: True when the named index exists.

    Side Effects:
        Reads database index metadata through the Alembic bind.
    """
    if not _table_exists(table_name):
        return False
    indexes = sa.inspect(op.get_bind()).get_indexes(table_name)
    return any(index.get("name") == index_name for index in indexes)


def upgrade() -> None:
    """Create the Felix Web Push subscription table and owner index.

    Args:
        None.

    Returns:
        None.

    Side Effects:
        Creates ``felix_web_push_subscriptions`` when missing.
    """
    table_name = "felix_web_push_subscriptions"
    if not _table_exists(table_name):
        op.create_table(
            table_name,
            sa.Column("pk", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.String(length=255), nullable=False),
            sa.Column("endpoint", sa.Text(), nullable=False),
            sa.Column("endpoint_hash", sa.String(length=64), nullable=False),
            sa.Column("expiration_time", sa.BigInteger(), nullable=True),
            sa.Column("p256dh", sa.Text(), nullable=False),
            sa.Column("auth", sa.Text(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.ForeignKeyConstraint(
                ["user_id"],
                ["users.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("pk"),
            sa.UniqueConstraint(
                "user_id",
                "endpoint_hash",
                name="uq_felix_web_push_owner_endpoint",
            ),
        )
    index_name = "ix_felix_web_push_subscriptions_user_id"
    if not _index_exists(table_name, index_name):
        op.create_index(index_name, table_name, ["user_id"], unique=False)


def downgrade() -> None:
    """Remove Felix SQL Web Push subscription storage.

    Args:
        None.

    Returns:
        None.

    Side Effects:
        Drops the Felix Web Push table and all contained subscriptions.
    """
    table_name = "felix_web_push_subscriptions"
    if _table_exists(table_name):
        op.drop_table(table_name)
