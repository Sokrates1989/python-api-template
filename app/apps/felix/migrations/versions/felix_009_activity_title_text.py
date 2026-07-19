"""Store Felix activity titles as unrestricted text.

Revision ID: felix_009_activity_title_text
Revises: felix_008_web_push_dispatch
Create Date: 2026-07-19 00:00:00.000000

The previous 255-character database column prevented Felix from restoring one
of its own curated activities and unnecessarily limited user-authored titles.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "felix_009_activity_title_text"
down_revision = "felix_008_web_push_dispatch"
branch_labels = None
depends_on = None


def _activity_title_type() -> sa.types.TypeEngine | None:
    """Return the current activity-title SQL type when the table exists.

    Returns:
        sa.types.TypeEngine | None: Reflected title-column type, or ``None``
        when the activity table or title column does not exist.

    Side Effects:
        Reads database metadata through the active Alembic connection.
    """
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("wellness_activities"):
        return None
    return next(
        (
            column["type"]
            for column in inspector.get_columns("wellness_activities")
            if column.get("name") == "title"
        ),
        None,
    )


def upgrade() -> None:
    """Widen the persisted Felix activity title to unrestricted text.

    Returns:
        None.

    Side Effects:
        Alters ``wellness_activities.title`` when that column exists.
    """
    existing_type = _activity_title_type()
    if existing_type is None or isinstance(existing_type, sa.Text):
        return
    op.alter_column(
        "wellness_activities",
        "title",
        existing_type=existing_type,
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    """Restore the historical 255-character activity-title column.

    Returns:
        None.

    Side Effects:
        Alters ``wellness_activities.title`` when that column exists. Existing
        titles longer than 255 characters must be shortened before downgrade.
    """
    existing_type = _activity_title_type()
    if existing_type is None or not isinstance(existing_type, sa.Text):
        return
    op.alter_column(
        "wellness_activities",
        "title",
        existing_type=existing_type,
        type_=sa.String(length=255),
        existing_nullable=True,
    )
