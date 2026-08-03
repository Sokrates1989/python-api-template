"""Add tenant-owned versioned service offerings and location assignments.

Revision ID: booking_service_004
Revises: booking_service_003
Create Date: 2026-08-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "booking_service_004"
down_revision = "booking_service_003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create service offerings and tenant-enforced location assignments.

    Returns:
        None: Alembic applies the complete catalog schema transactionally.
    """
    _create_service_offerings()
    _create_service_locations()


def _create_service_offerings() -> None:
    """Create the optimistic timed-service aggregate root.

    Returns:
        None: The table and visibility index are created.
    """
    op.create_table(
        "booking_service_offerings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=120), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("setup_buffer_minutes", sa.Integer(), nullable=False),
        sa.Column("cleanup_buffer_minutes", sa.Integer(), nullable=False),
        sa.Column("slot_step_minutes", sa.Integer(), nullable=False),
        sa.Column("price_minor_units", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("is_published", sa.Boolean(), nullable=False),
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
            "duration_minutes BETWEEN 5 AND 1440",
            name="ck_booking_service_duration",
        ),
        sa.CheckConstraint(
            "setup_buffer_minutes BETWEEN 0 AND 1440",
            name="ck_booking_service_setup_buffer",
        ),
        sa.CheckConstraint(
            "cleanup_buffer_minutes BETWEEN 0 AND 1440",
            name="ck_booking_service_cleanup_buffer",
        ),
        sa.CheckConstraint(
            "slot_step_minutes BETWEEN 5 AND 60 AND slot_step_minutes % 5 = 0",
            name="ck_booking_service_slot_step",
        ),
        sa.CheckConstraint(
            "price_minor_units BETWEEN 0 AND 1000000000",
            name="ck_booking_service_price",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'archived')",
            name="ck_booking_service_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["booking_organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "id",
            name="uq_booking_service_org_id",
        ),
    )
    op.create_index(
        "ix_booking_service_org_visibility_name",
        "booking_service_offerings",
        ["organization_id", "status", "is_published", "name"],
    )


def _create_service_locations() -> None:
    """Create explicit same-tenant service/location assignments.

    Returns:
        None: The association table and location lookup index are created.
    """
    op.create_table(
        "booking_service_location_offerings",
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("service_offering_id", sa.String(length=36), nullable=False),
        sa.Column("location_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "service_offering_id"],
            [
                "booking_service_offerings.organization_id",
                "booking_service_offerings.id",
            ],
            name="fk_booking_service_location_service_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "location_id"],
            ["booking_locations.organization_id", "booking_locations.id"],
            name="fk_booking_service_location_location_tenant",
        ),
        sa.PrimaryKeyConstraint(
            "organization_id",
            "service_offering_id",
            "location_id",
        ),
    )
    op.create_index(
        "ix_booking_service_location_location",
        "booking_service_location_offerings",
        ["organization_id", "location_id"],
    )


def downgrade() -> None:
    """Remove only the BKG-201 service-catalog persistence boundary.

    Returns:
        None: Alembic drops catalog associations and offerings.
    """
    op.drop_index(
        "ix_booking_service_location_location",
        table_name="booking_service_location_offerings",
    )
    op.drop_table("booking_service_location_offerings")
    op.drop_index(
        "ix_booking_service_org_visibility_name",
        table_name="booking_service_offerings",
    )
    op.drop_table("booking_service_offerings")
