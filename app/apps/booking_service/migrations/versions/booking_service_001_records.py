"""Create the generated subject-owned records table.

Revision ID: booking_service_001_records
Revises: None
Create Date: 2026-07-19 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "booking_service_001_records"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the records table and subject pagination index.

    Returns:
        Nothing.

    Side Effects:
        Creates the generated app-owned PostgreSQL table and index.
    """

    op.create_table(
        "booking_service_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_subject", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_booking_service_owner",
        "booking_service_records",
        ["owner_subject", "updated_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    """Remove the generated records table safely.

    Returns:
        Nothing.

    Side Effects:
        Drops the app-owned index and table.
    """

    op.drop_index("ix_booking_service_owner", table_name="booking_service_records")
    op.drop_table("booking_service_records")
