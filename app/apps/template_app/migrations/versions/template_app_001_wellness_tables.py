"""Create Template App-owned SQL wellness tables.

Revision ID: template_app_001_wellness_tables
Revises: None
Create Date: 2026-06-30 00:00:00.000000

The Template App uses the shared wellness runtime as an example feature, but
its SQL tables are owned by the selected app migration stream.
"""

from alembic import op
import sqlalchemy as sa


revision = "template_app_001_wellness_tables"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create wellness tables for the Template App SQL profile.

    Args:
        None.

    Returns:
        None.

    Side Effects:
        Adds the activity, diary, and check-in tables consumed by the shared
        wellness runtime when Template App is selected.
    """
    op.create_table(
        "wellness_activities",
        sa.Column("pk", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("icon_key", sa.String(length=64), nullable=False),
        sa.Column("title_key", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("summary_key", sa.String(length=255), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("favorite", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("category_keys", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("energy_impact", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("pk"),
        sa.UniqueConstraint("user_id", "id", name="uq_wellness_activities_user_id_id"),
    )
    op.create_index("ix_wellness_activities_user_id", "wellness_activities", ["user_id"], unique=False)
    op.create_index(
        "ix_wellness_activities_user_favorite",
        "wellness_activities",
        ["user_id", "favorite"],
        unique=False,
    )

    op.create_table(
        "wellness_diary_entries",
        sa.Column("pk", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("title_key", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("summary_key", sa.String(length=255), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("mood_state_key", sa.String(length=64), nullable=False),
        sa.Column("mood_score", sa.Integer(), nullable=False),
        sa.Column("tag_keys", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("related_activity_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("pk"),
        sa.UniqueConstraint("user_id", "id", name="uq_wellness_diary_entries_user_id_id"),
    )
    op.create_index("ix_wellness_diary_entries_user_id", "wellness_diary_entries", ["user_id"], unique=False)
    op.create_index(
        "ix_wellness_diary_entries_user_created_at",
        "wellness_diary_entries",
        ["user_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "wellness_checkins",
        sa.Column("pk", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("mood_score", sa.Integer(), nullable=False),
        sa.Column("stress_score", sa.Integer(), nullable=False),
        sa.Column("energy_score", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("pk"),
        sa.UniqueConstraint("user_id", "id", name="uq_wellness_checkins_user_id_id"),
    )
    op.create_index("ix_wellness_checkins_user_id", "wellness_checkins", ["user_id"], unique=False)
    op.create_index(
        "ix_wellness_checkins_user_recorded_at",
        "wellness_checkins",
        ["user_id", "recorded_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop Template App-owned wellness tables.

    Args:
        None.

    Returns:
        None.

    Side Effects:
        Removes the activity, diary, and check-in tables from the selected
        Template App SQL profile.
    """
    op.drop_index("ix_wellness_checkins_user_recorded_at", table_name="wellness_checkins")
    op.drop_index("ix_wellness_checkins_user_id", table_name="wellness_checkins")
    op.drop_table("wellness_checkins")
    op.drop_index("ix_wellness_diary_entries_user_created_at", table_name="wellness_diary_entries")
    op.drop_index("ix_wellness_diary_entries_user_id", table_name="wellness_diary_entries")
    op.drop_table("wellness_diary_entries")
    op.drop_index("ix_wellness_activities_user_favorite", table_name="wellness_activities")
    op.drop_index("ix_wellness_activities_user_id", table_name="wellness_activities")
    op.drop_table("wellness_activities")
