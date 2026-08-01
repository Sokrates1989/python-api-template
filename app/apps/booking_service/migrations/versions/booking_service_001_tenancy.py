"""Create Booking Service organization-tenancy primitives.

Revision ID: booking_service_001
Revises: None
Create Date: 2026-08-01
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "booking_service_001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create subjects, organizations, memberships, roles, and audit tables.

    Returns:
        None: Alembic applies the schema changes in the current transaction.
    """
    _create_subject_tables()
    _create_organization_tables()
    _create_audit_table()


def _create_subject_tables() -> None:
    """Create subject lifecycle and platform-access tables.

    Returns:
        None: Tables are created through Alembic operations.
    """
    op.create_table(
        "booking_subjects",
        sa.Column("subject_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'suspended', 'deletion_pending')",
            name="ck_booking_subject_status",
        ),
        sa.PrimaryKeyConstraint("subject_id"),
    )
    op.create_table(
        "booking_platform_access",
        sa.Column("subject_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("approved_by_subject_id", sa.String(length=255), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'revoked')",
            name="ck_booking_platform_access_status",
        ),
        sa.ForeignKeyConstraint(["subject_id"], ["booking_subjects.subject_id"]),
        sa.PrimaryKeyConstraint("subject_id"),
    )


def _create_organization_tables() -> None:
    """Create tenant, membership, and membership-role tables.

    Returns:
        None: Tables are created through Alembic operations.
    """
    op.create_table(
        "booking_organizations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'suspended')",
            name="ck_booking_organization_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "booking_organization_memberships",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("subject_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('invited', 'active', 'suspended', 'revoked')",
            name="ck_booking_membership_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["booking_organizations.id"]),
        sa.ForeignKeyConstraint(["subject_id"], ["booking_subjects.subject_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_booking_membership_org_id"
        ),
        sa.UniqueConstraint(
            "organization_id", "subject_id", name="uq_booking_membership_org_subject"
        ),
    )
    op.create_index(
        "ix_booking_membership_subject_status",
        "booking_organization_memberships",
        ["subject_id", "status"],
    )
    op.create_table(
        "booking_organization_membership_roles",
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("membership_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "role IN ('organization_admin', 'worker', 'customer')",
            name="ck_booking_membership_role",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "membership_id"],
            [
                "booking_organization_memberships.organization_id",
                "booking_organization_memberships.id",
            ],
            name="fk_booking_role_membership_scope",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("organization_id", "membership_id", "role"),
    )


def _create_audit_table() -> None:
    """Create the immutable lifecycle audit-event table.

    Returns:
        None: The table and lookup index are created through Alembic.
    """
    op.create_table(
        "booking_audit_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("actor_subject_id", sa.String(length=255), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("resource_type", sa.String(length=80), nullable=False),
        sa.Column("resource_id", sa.String(length=255), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("before_state", sa.JSON(), nullable=True),
        sa.Column("after_state", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "outcome IN ('succeeded', 'denied')",
            name="ck_booking_audit_outcome",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_booking_audit_resource",
        "booking_audit_events",
        ["resource_type", "resource_id"],
    )


def downgrade() -> None:
    """Remove the BKG-101 schema in reverse dependency order.

    Returns:
        None: Alembic applies the destructive downgrade when explicitly run.
    """
    op.drop_index("ix_booking_audit_resource", table_name="booking_audit_events")
    op.drop_table("booking_audit_events")
    op.drop_table("booking_organization_membership_roles")
    op.drop_index(
        "ix_booking_membership_subject_status",
        table_name="booking_organization_memberships",
    )
    op.drop_table("booking_organization_memberships")
    op.drop_table("booking_organizations")
    op.drop_table("booking_platform_access")
    op.drop_table("booking_subjects")
