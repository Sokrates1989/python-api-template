"""Create Felix-owned SQL wellness tables.

Revision ID: felix_001_wellness_tables
Revises: None
Create Date: 2026-06-30 00:00:00.000000

Felix uses the shared wellness runtime, but the SQL schema is owned by the
selected Felix app migration stream so other app databases are not changed by
Felix-specific startup. The migration tolerates local databases where the same
tables were created by an older global revision before the ownership boundary
was corrected.
"""

from alembic import op
import sqlalchemy as sa


revision = "felix_001_wellness_tables"
down_revision = None
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    """Return whether a Felix wellness table already exists.

    Args:
        table_name (str): Database table name to inspect.

    Returns:
        bool: True when the table is already present.

    Side Effects:
        Reads database metadata through the Alembic bind.
    """
    return sa.inspect(op.get_bind()).has_table(table_name)


def _index_exists(table_name: str, index_name: str) -> bool:
    """Return whether a named index already exists on a table.

    Args:
        table_name (str): Database table name to inspect.
        index_name (str): Index name to find.

    Returns:
        bool: True when the index exists.

    Side Effects:
        Reads database index metadata through the Alembic bind.
    """
    indexes = sa.inspect(op.get_bind()).get_indexes(table_name)
    return any(index.get("name") == index_name for index in indexes)


def _create_index_if_missing(
    index_name: str,
    table_name: str,
    columns: list[str],
) -> None:
    """Create a Felix wellness index when local legacy data is missing it.

    Args:
        index_name (str): Name of the index to create.
        table_name (str): Table receiving the index.
        columns (list[str]): Ordered table columns included in the index.

    Returns:
        None.

    Side Effects:
        Creates an index when it does not already exist.
    """
    if not _index_exists(table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=False)


def upgrade() -> None:
    """Create wellness tables for the Felix SQL app profile.

    Args:
        None.

    Returns:
        None.

    Side Effects:
        Adds the activity, diary, and check-in tables consumed by the shared
        wellness runtime when Felix is the selected backend app. Existing
        tables from the legacy global migration are reused and stamped into the
        app stream.
    """
    if not _table_exists("wellness_activities"):
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
    _create_index_if_missing(
        "ix_wellness_activities_user_id",
        "wellness_activities",
        ["user_id"],
    )
    _create_index_if_missing(
        "ix_wellness_activities_user_favorite",
        "wellness_activities",
        ["user_id", "favorite"],
    )

    if not _table_exists("wellness_diary_entries"):
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
    _create_index_if_missing(
        "ix_wellness_diary_entries_user_id",
        "wellness_diary_entries",
        ["user_id"],
    )
    _create_index_if_missing(
        "ix_wellness_diary_entries_user_created_at",
        "wellness_diary_entries",
        ["user_id", "created_at"],
    )

    if not _table_exists("wellness_checkins"):
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
    _create_index_if_missing("ix_wellness_checkins_user_id", "wellness_checkins", ["user_id"])
    _create_index_if_missing(
        "ix_wellness_checkins_user_recorded_at",
        "wellness_checkins",
        ["user_id", "recorded_at"],
    )


def downgrade() -> None:
    """Drop Felix-owned wellness tables.

    Args:
        None.

    Returns:
        None.

    Side Effects:
        Removes the activity, diary, and check-in tables from the selected
        Felix SQL app profile.
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
