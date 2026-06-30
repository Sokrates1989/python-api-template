"""Create the shared SQL sync conflict log.

Revision ID: 010_create_sync_conflicts_table
Revises: 009_add_sync_support
Create Date: 2026-04-14 12:00:00.000000

The table is global because sync conflict capture is provider-wide
infrastructure. Feature tables such as wellness content belong in selected-app
migration streams under ``app/apps/<app_id>/migrations/versions``.
"""

from alembic import op
import sqlalchemy as sa


revision = "010_create_sync_conflicts_table"
down_revision = "009_add_sync_support"
branch_labels = None
depends_on = None


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
    op.create_index(
        "ix_sync_conflicts_user_id",
        "sync_conflicts",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_sync_conflicts_op_id",
        "sync_conflicts",
        ["op_id"],
        unique=False,
    )
    op.create_index(
        "ix_sync_conflicts_user_detected_at",
        "sync_conflicts",
        ["user_id", "detected_at"],
        unique=False,
    )


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
