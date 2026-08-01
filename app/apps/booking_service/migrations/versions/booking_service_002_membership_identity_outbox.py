"""Add durable membership identity-role synchronization intent.

Revision ID: booking_service_002
Revises: booking_service_001
Create Date: 2026-08-01
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "booking_service_002"
down_revision = "booking_service_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the opaque, retryable Keycloak role-sync outbox.

    Returns:
        None: Alembic applies the schema change transactionally.
    """
    op.create_table(
        "booking_identity_role_outbox",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("membership_id", sa.String(length=36), nullable=False),
        sa.Column("subject_id", sa.String(length=255), nullable=False),
        sa.Column("roles", sa.JSON(), nullable=False),
        sa.Column("membership_revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error_code", sa.String(length=80), nullable=True),
        sa.Column("retryable", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'succeeded', 'failed', 'cancelled')",
            name="ck_booking_identity_outbox_status",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "membership_id"],
            [
                "booking_organization_memberships.organization_id",
                "booking_organization_memberships.id",
            ],
            name="fk_booking_identity_outbox_membership_scope",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_booking_identity_outbox_status_created",
        "booking_identity_role_outbox",
        ["status", "created_at"],
    )


def downgrade() -> None:
    """Remove only the BKG-103 identity-role outbox.

    Returns:
        None: Alembic removes the index and table when explicitly requested.
    """
    op.drop_index(
        "ix_booking_identity_outbox_status_created",
        table_name="booking_identity_role_outbox",
    )
    op.drop_table("booking_identity_role_outbox")
