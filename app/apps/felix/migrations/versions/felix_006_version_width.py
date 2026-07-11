"""Widen the Felix Alembic version column for descriptive revision ids.

Revision ID: felix_006_version_width
Revises: felix_005_activity_catalog
Create Date: 2026-07-11 00:00:00.000000

Revision 005 performs the same widening for fresh databases. This follow-up is
required for databases that applied the shortened 005 revision while the API
was recovering from the original VARCHAR(32) startup failure.
"""

from alembic import op
import sqlalchemy as sa


revision = "felix_006_version_width"
down_revision = "felix_005_activity_catalog"
branch_labels = None
depends_on = None


def _version_column_length() -> int | None:
    """Return the configured Felix version-column length when available."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("alembic_version_felix"):
        return None
    column = next(
        (
            item
            for item in inspector.get_columns("alembic_version_felix")
            if item.get("name") == "version_num"
        ),
        None,
    )
    return getattr(column.get("type"), "length", None) if column else None


def upgrade() -> None:
    """Widen the app-scoped Alembic revision column to 128 characters."""
    current_length = _version_column_length()
    if current_length is None or current_length >= 128:
        return
    op.alter_column(
        "alembic_version_felix",
        "version_num",
        existing_type=sa.String(length=current_length),
        type_=sa.String(length=128),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Restore the legacy 32-character version-column width."""
    current_length = _version_column_length()
    if current_length is None or current_length <= 32:
        return
    op.alter_column(
        "alembic_version_felix",
        "version_num",
        existing_type=sa.String(length=current_length),
        type_=sa.String(length=32),
        existing_nullable=False,
    )
