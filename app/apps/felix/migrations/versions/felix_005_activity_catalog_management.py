"""Persist Felix activity catalogue categories and management fields.

Revision ID: felix_005_activity_catalog
Revises: felix_004_access_readiness
Create Date: 2026-07-11 00:00:00.000000

The migration is defensive because local developer databases may contain a
subset of the historical Felix schema. It adds the provider-shared activity
fields and creates first-class user-owned categories for catalogue management.
"""

from alembic import op
import sqlalchemy as sa


revision = "felix_005_activity_catalog"
down_revision = "felix_004_access_readiness"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    """Return whether the current database contains a table."""
    return sa.inspect(op.get_bind()).has_table(table_name)


def _column_names(table_name: str) -> set[str]:
    """Return column names for an existing table."""
    if not _table_exists(table_name):
        return set()
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _index_exists(table_name: str, index_name: str) -> bool:
    """Return whether an existing table owns the named index."""
    if not _table_exists(table_name):
        return False
    return any(index.get("name") == index_name for index in sa.inspect(op.get_bind()).get_indexes(table_name))


def _widen_version_column() -> None:
    """Allow future Felix revision identifiers longer than 32 characters.

    Alembic updates the version row only after ``upgrade`` completes, so this
    transition revision deliberately keeps a short id and widens the column
    before that update occurs.
    """
    table_name = "alembic_version_felix"
    if not _table_exists(table_name):
        return
    version_column = next(
        (
            column
            for column in sa.inspect(op.get_bind()).get_columns(table_name)
            if column.get("name") == "version_num"
        ),
        None,
    )
    current_length = getattr(version_column.get("type"), "length", None) if version_column else None
    if current_length is not None and current_length >= 128:
        return
    op.alter_column(
        table_name,
        "version_num",
        existing_type=sa.String(length=current_length or 32),
        type_=sa.String(length=128),
        existing_nullable=False,
    )


def upgrade() -> None:
    """Add activity management fields and persisted categories."""
    _widen_version_column()
    activity_columns = _column_names("wellness_activities")
    additions = {
        "activity_reminder": sa.Column("activity_reminder", sa.Text(), nullable=True),
        "harmful": sa.Column("harmful", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        "sort_order": sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        "tags": sa.Column("tags", sa.Text(), nullable=False, server_default="[]"),
    }
    for name, column in additions.items():
        if name not in activity_columns:
            op.add_column("wellness_activities", column)

    if not _table_exists("wellness_activity_categories"):
        op.create_table(
            "wellness_activity_categories",
            sa.Column("pk", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.String(length=255), nullable=False),
            sa.Column("key", sa.String(length=128), nullable=False),
            sa.Column("title_key", sa.String(length=255), nullable=True),
            sa.Column("title", sa.String(length=255), nullable=True),
            sa.Column("description_key", sa.String(length=255), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("icon_key", sa.String(length=64), nullable=False, server_default="category"),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("pk"),
            sa.UniqueConstraint("user_id", "key", name="uq_wellness_activity_categories_user_key"),
        )
    if not _index_exists("wellness_activity_categories", "ix_wellness_activity_categories_user_id"):
        op.create_index("ix_wellness_activity_categories_user_id", "wellness_activity_categories", ["user_id"])
    if not _index_exists("wellness_activity_categories", "ix_wellness_activity_categories_user_order"):
        op.create_index("ix_wellness_activity_categories_user_order", "wellness_activity_categories", ["user_id", "sort_order"])
    if not _table_exists("wellness_sync_tombstones"):
        op.create_table(
            "wellness_sync_tombstones",
            sa.Column("pk", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.String(length=255), nullable=False),
            sa.Column("entity_type", sa.String(length=64), nullable=False),
            sa.Column("entity_id", sa.String(length=128), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("pk"),
            sa.UniqueConstraint("user_id", "entity_type", "entity_id", name="uq_wellness_sync_tombstones_entity"),
        )
    if not _index_exists("wellness_sync_tombstones", "ix_wellness_sync_tombstones_user_id"):
        op.create_index("ix_wellness_sync_tombstones_user_id", "wellness_sync_tombstones", ["user_id"])
    if not _index_exists("wellness_sync_tombstones", "ix_wellness_sync_tombstones_user_deleted"):
        op.create_index("ix_wellness_sync_tombstones_user_deleted", "wellness_sync_tombstones", ["user_id", "deleted_at"])


def downgrade() -> None:
    """Remove persisted categories and activity management fields."""
    if _table_exists("wellness_sync_tombstones"):
        op.drop_table("wellness_sync_tombstones")
    if _table_exists("wellness_activity_categories"):
        op.drop_table("wellness_activity_categories")
    activity_columns = _column_names("wellness_activities")
    for name in ("tags", "sort_order", "harmful", "activity_reminder"):
        if name in activity_columns:
            op.drop_column("wellness_activities", name)
