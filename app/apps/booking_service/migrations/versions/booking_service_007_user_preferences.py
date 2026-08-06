"""Add subject-scoped Booking Service user preferences.

Revision ID: booking_service_007
Revises: booking_service_006
Create Date: 2026-08-07
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "booking_service_007"
down_revision = "booking_service_006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the revisioned per-subject preference boundary.

    Returns:
        None: Alembic creates the constrained table transactionally. Rows are
        initialized lazily when each authenticated account first reads them.
    """

    op.create_table(
        "booking_user_preferences",
        sa.Column("subject_id", sa.String(length=255), nullable=False),
        sa.Column("preferred_locale", sa.String(length=16), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "preferred_locale IN ('de', 'en')",
            name="ck_booking_user_preferences_locale",
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"],
            ["booking_subjects.subject_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("subject_id"),
    )


def downgrade() -> None:
    """Remove the app-owned user preference boundary.

    Returns:
        None: Alembic drops only the BKG-200 remediation table.
    """

    op.drop_table("booking_user_preferences")
