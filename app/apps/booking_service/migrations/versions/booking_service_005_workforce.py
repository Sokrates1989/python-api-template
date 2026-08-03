"""Add service selection policy and tenant-owned worker eligibility.

Revision ID: booking_service_005
Revises: booking_service_004
Create Date: 2026-08-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "booking_service_005"
down_revision = "booking_service_004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the complete BKG-202 worker and selection-policy boundary."""
    _add_service_selection_mode()
    _create_worker_profiles()
    _create_worker_locations()
    _create_worker_qualifications()


def _add_service_selection_mode() -> None:
    """Backfill each existing service from its tenant's company default."""
    op.add_column(
        "booking_service_offerings",
        sa.Column(
            "worker_selection_mode",
            sa.String(length=32),
            server_default="specific_or_auto",
            nullable=False,
        ),
    )
    op.execute(
        """
        UPDATE booking_service_offerings AS service
        SET worker_selection_mode = CASE settings.worker_selection_mode
            WHEN 'next_available_only' THEN 'auto_only'
            WHEN 'specific_worker_only' THEN 'specific_only'
            ELSE 'specific_or_auto'
        END
        FROM booking_company_settings AS settings
        WHERE settings.organization_id = service.organization_id
        """
    )
    op.create_check_constraint(
        "ck_booking_service_worker_selection",
        "booking_service_offerings",
        "worker_selection_mode IN ('auto_only', 'specific_only', 'specific_or_auto')",
    )
    op.alter_column(
        "booking_service_offerings",
        "worker_selection_mode",
        server_default=None,
    )


def _create_worker_profiles() -> None:
    """Create one optimistic profile per tenant membership."""
    op.create_table(
        "booking_worker_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("membership_id", sa.String(length=36), nullable=False),
        sa.Column("public_name", sa.String(length=160), nullable=True),
        sa.Column("public_description", sa.Text(), nullable=True),
        sa.Column("is_publicly_bookable", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
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
            "status IN ('active', 'inactive')",
            name="ck_booking_worker_status",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "membership_id"],
            [
                "booking_organization_memberships.organization_id",
                "booking_organization_memberships.id",
            ],
            name="fk_booking_worker_membership_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "id",
            name="uq_booking_worker_org_id",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "membership_id",
            name="uq_booking_worker_org_membership",
        ),
    )
    op.create_index(
        "ix_booking_worker_org_visibility",
        "booking_worker_profiles",
        ["organization_id", "status", "is_publicly_bookable", "public_name"],
    )


def _create_worker_locations() -> None:
    """Create explicit same-tenant worker/location assignments."""
    op.create_table(
        "booking_worker_location_assignments",
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("worker_profile_id", sa.String(length=36), nullable=False),
        sa.Column("location_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "worker_profile_id"],
            ["booking_worker_profiles.organization_id", "booking_worker_profiles.id"],
            name="fk_booking_worker_location_worker_scope",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "location_id"],
            ["booking_locations.organization_id", "booking_locations.id"],
            name="fk_booking_worker_location_location_scope",
        ),
        sa.PrimaryKeyConstraint("organization_id", "worker_profile_id", "location_id"),
    )
    op.create_index(
        "ix_booking_worker_location_location",
        "booking_worker_location_assignments",
        ["organization_id", "location_id"],
    )


def _create_worker_qualifications() -> None:
    """Create explicit same-tenant service qualification and auto policy."""
    op.create_table(
        "booking_worker_service_qualifications",
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("worker_profile_id", sa.String(length=36), nullable=False),
        sa.Column("service_offering_id", sa.String(length=36), nullable=False),
        sa.Column("auto_eligible", sa.Boolean(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "worker_profile_id"],
            ["booking_worker_profiles.organization_id", "booking_worker_profiles.id"],
            name="fk_booking_worker_qualification_worker_scope",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "service_offering_id"],
            [
                "booking_service_offerings.organization_id",
                "booking_service_offerings.id",
            ],
            name="fk_booking_worker_qualification_service_scope",
        ),
        sa.CheckConstraint(
            "priority BETWEEN 0 AND 1000",
            name="ck_booking_worker_qualification_priority",
        ),
        sa.PrimaryKeyConstraint(
            "organization_id",
            "worker_profile_id",
            "service_offering_id",
        ),
    )
    op.create_index(
        "ix_booking_worker_qualification_service",
        "booking_worker_service_qualifications",
        ["organization_id", "service_offering_id"],
    )


def downgrade() -> None:
    """Remove only BKG-202 worker state and service selection policy."""
    op.drop_index(
        "ix_booking_worker_qualification_service",
        table_name="booking_worker_service_qualifications",
    )
    op.drop_table("booking_worker_service_qualifications")
    op.drop_index(
        "ix_booking_worker_location_location",
        table_name="booking_worker_location_assignments",
    )
    op.drop_table("booking_worker_location_assignments")
    op.drop_index(
        "ix_booking_worker_org_visibility",
        table_name="booking_worker_profiles",
    )
    op.drop_table("booking_worker_profiles")
    op.drop_constraint(
        "ck_booking_service_worker_selection",
        "booking_service_offerings",
        type_="check",
    )
    op.drop_column("booking_service_offerings", "worker_selection_mode")
