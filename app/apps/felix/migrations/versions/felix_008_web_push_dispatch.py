"""Create Felix durable scheduled Web Push dispatch storage.

Revision ID: felix_008_web_push_dispatch
Revises: felix_007_web_push_subscriptions
Create Date: 2026-07-13 00:00:00.000000

The table stores only fixed-kind app commands, schedule identity, delivery
times, leases, and bounded retry metadata. It never stores browser endpoint or
VAPID key material; those remain in the subscription/secret boundaries.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "felix_008_web_push_dispatch"
down_revision = "felix_007_web_push_subscriptions"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    """Return whether a SQL table already exists.

    Args:
        table_name (str): Database table name to inspect.

    Returns:
        bool: True when the table exists.

    Side Effects:
        Reads database metadata through the Alembic bind.
    """
    return sa.inspect(op.get_bind()).has_table(table_name)


def _index_exists(table_name: str, index_name: str) -> bool:
    """Return whether an existing table owns a named index.

    Args:
        table_name (str): Existing table name.
        index_name (str): Index identifier to find.

    Returns:
        bool: True when the named index exists.

    Side Effects:
        Reads database index metadata.
    """
    if not _table_exists(table_name):
        return False
    indexes = sa.inspect(op.get_bind()).get_indexes(table_name)
    return any(index.get("name") == index_name for index in indexes)


def upgrade() -> None:
    """Create Felix dispatch jobs and owner/due indexes.

    Returns:
        None.

    Side Effects:
        Creates ``felix_web_push_dispatch_jobs`` when missing.
    """
    table_name = "felix_web_push_dispatch_jobs"
    if not _table_exists(table_name):
        op.create_table(
            table_name,
            sa.Column("pk", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("job_id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.String(length=255), nullable=False),
            sa.Column("schedule_key", sa.String(length=200), nullable=False),
            sa.Column("payload", sa.Text(), nullable=False),
            sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column(
                "attempt_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "next_attempt_at",
                sa.DateTime(timezone=True),
                nullable=False,
            ),
            sa.Column("lease_token", sa.String(length=36), nullable=True),
            sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_failure_code", sa.String(length=64), nullable=True),
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
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("pk"),
            sa.UniqueConstraint("job_id", name="uq_felix_web_push_dispatch_job"),
            sa.UniqueConstraint(
                "user_id",
                "schedule_key",
                name="uq_felix_web_push_dispatch_owner_key",
            ),
        )

    # Owner replacement and due leasing use separate bounded indexes.
    owner_index = "ix_felix_web_push_dispatch_owner"
    if not _index_exists(table_name, owner_index):
        op.create_index(owner_index, table_name, ["user_id"], unique=False)
    due_index = "ix_felix_web_push_dispatch_due"
    if not _index_exists(table_name, due_index):
        op.create_index(
            due_index,
            table_name,
            ["next_attempt_at", "due_at", "lease_until"],
            unique=False,
        )


def downgrade() -> None:
    """Remove Felix durable Web Push dispatch storage.

    Returns:
        None.

    Side Effects:
        Drops all pending Felix Web Push dispatch jobs.
    """
    table_name = "felix_web_push_dispatch_jobs"
    if _table_exists(table_name):
        op.drop_table(table_name)
