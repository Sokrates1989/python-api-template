"""Add sync support for hybrid offline/online user profile synchronization.

Revision ID: 009_add_sync_support
Revises: 008_create_users_table
Create Date: 2026-02-26 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "009_add_sync_support"
down_revision = "008_create_users_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add versioning fields and idempotent sync operation log table."""

    # Add optimistic sync version column to users
    op.add_column(
        "users",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.execute("UPDATE users SET version = 1 WHERE version IS NULL")
    op.alter_column("users", "version", server_default=None)

    # Ensure updated_at is always populated for cursor ordering
    op.execute("UPDATE users SET updated_at = created_at WHERE updated_at IS NULL")
    op.alter_column(
        "users",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )

    # Persist sync results per op_id for idempotent replay
    op.create_table(
        "sync_operation_log",
        sa.Column("op_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("op_id"),
    )
    op.create_index(
        "ix_sync_operation_log_user_created",
        "sync_operation_log",
        ["user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Remove sync operation log and users versioning fields."""

    op.drop_index("ix_sync_operation_log_user_created", table_name="sync_operation_log")
    op.drop_table("sync_operation_log")

    op.alter_column(
        "users",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
        server_default=None,
    )
    op.drop_column("users", "version")
