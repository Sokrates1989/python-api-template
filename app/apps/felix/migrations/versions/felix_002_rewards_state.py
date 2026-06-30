"""Create Felix rewards-state SQL table.

Revision ID: felix_002_rewards_state
Revises: felix_001_wellness_tables
Create Date: 2026-06-30 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "felix_002_rewards_state"
down_revision = "felix_001_wellness_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the Felix-owned rewards-state table.

    Args:
        None.

    Returns:
        None.

    Side Effects:
        Adds ``felix_rewards_state`` and its user lookup index.
    """
    op.create_table(
        "felix_rewards_state",
        sa.Column("pk", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("purchases", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("spent_suns", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_seen_earned_suns", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_celebrated_earned_suns", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("streak_savers_available", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("streak_savers_max", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("streak_saver_used_day_keys", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("last_streak_saver_grant_day_key", sa.String(length=32), nullable=True),
        sa.Column("media_preferences", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("pk"),
        sa.UniqueConstraint("user_id", name="uq_felix_rewards_state_user_id"),
    )
    op.create_index("ix_felix_rewards_state_user_id", "felix_rewards_state", ["user_id"], unique=False)


def downgrade() -> None:
    """Drop the Felix-owned rewards-state table.

    Args:
        None.

    Returns:
        None.

    Side Effects:
        Removes ``felix_rewards_state`` and its indexes.
    """
    op.drop_index("ix_felix_rewards_state_user_id", table_name="felix_rewards_state")
    op.drop_table("felix_rewards_state")
