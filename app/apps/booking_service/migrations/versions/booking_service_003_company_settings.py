"""Add tenant-owned company settings and reversible locations.

Revision ID: booking_service_003
Revises: booking_service_002
Create Date: 2026-08-02
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "booking_service_003"
down_revision = "booking_service_002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create, constrain, and backfill company settings and locations.

    Returns:
        None: Alembic applies the complete tenant schema transactionally.
    """
    _create_company_settings_table()
    _create_locations_table()
    _backfill_existing_organizations()


def _create_company_settings_table() -> None:
    """Create one optimistic company-profile row per organization.

    Returns:
        None: The table is created through Alembic operations.
    """
    op.create_table(
        "booking_company_settings",
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("public_name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("contact_email", sa.String(length=254), nullable=True),
        sa.Column("contact_phone", sa.String(length=40), nullable=True),
        sa.Column("website_url", sa.String(length=500), nullable=True),
        sa.Column("default_timezone", sa.String(length=64), nullable=False),
        sa.Column("default_locale", sa.String(length=16), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("booking_horizon_days", sa.Integer(), nullable=False),
        sa.Column("minimum_notice_minutes", sa.Integer(), nullable=False),
        sa.Column("cancellation_notice_minutes", sa.Integer(), nullable=False),
        sa.Column("reschedule_notice_minutes", sa.Integer(), nullable=False),
        sa.Column("worker_selection_mode", sa.String(length=40), nullable=False),
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
            "booking_horizon_days BETWEEN 1 AND 730",
            name="ck_booking_company_horizon",
        ),
        sa.CheckConstraint(
            "minimum_notice_minutes BETWEEN 0 AND 43200",
            name="ck_booking_company_minimum_notice",
        ),
        sa.CheckConstraint(
            "cancellation_notice_minutes BETWEEN 0 AND 43200",
            name="ck_booking_company_cancellation_notice",
        ),
        sa.CheckConstraint(
            "reschedule_notice_minutes BETWEEN 0 AND 43200",
            name="ck_booking_company_reschedule_notice",
        ),
        sa.CheckConstraint(
            "worker_selection_mode IN "
            "('next_available_only', 'specific_worker_only', "
            "'next_available_or_specific')",
            name="ck_booking_company_worker_selection",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["booking_organizations.id"],
        ),
        sa.PrimaryKeyConstraint("organization_id"),
    )


def _create_locations_table() -> None:
    """Create tenant-scoped locations with a reversible lifecycle.

    Returns:
        None: The table and scoped lookup index are created.
    """
    op.create_table(
        "booking_locations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("address_line_1", sa.String(length=200), nullable=True),
        sa.Column("address_line_2", sa.String(length=200), nullable=True),
        sa.Column("postal_code", sa.String(length=32), nullable=True),
        sa.Column("locality", sa.String(length=120), nullable=True),
        sa.Column("region", sa.String(length=120), nullable=True),
        sa.Column("country_code", sa.String(length=2), nullable=True),
        sa.Column("contact_email", sa.String(length=254), nullable=True),
        sa.Column("contact_phone", sa.String(length=40), nullable=True),
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
            "status IN ('active', 'archived')",
            name="ck_booking_location_status",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["booking_organizations.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "id",
            name="uq_booking_location_org_id",
        ),
    )
    op.create_index(
        "ix_booking_location_org_status_name",
        "booking_locations",
        ["organization_id", "status", "display_name"],
    )


def _backfill_existing_organizations() -> None:
    """Give every pre-existing tenant valid neutral defaults and one location.

    Returns:
        None: Rows are inserted only for organizations present at migration time.

    Note:
        The organization UUID is reused as the first location UUID. The two
        identifier spaces are separate tables, making the deterministic value
        collision-free while avoiding database-specific UUID extensions.
    """
    op.execute(
        sa.text(
            """
            INSERT INTO booking_company_settings (
                organization_id, public_name, default_timezone, default_locale,
                currency, booking_horizon_days, minimum_notice_minutes,
                cancellation_notice_minutes, reschedule_notice_minutes,
                worker_selection_mode, revision
            )
            SELECT id, display_name, 'Europe/Berlin', 'de', 'EUR', 90, 120,
                   1440, 1440, 'next_available_or_specific', 1
            FROM booking_organizations
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO booking_locations (
                id, organization_id, display_name, timezone, status, revision
            )
            SELECT id, id, 'Primary location', 'Europe/Berlin', 'active', 1
            FROM booking_organizations
            """
        )
    )


def downgrade() -> None:
    """Remove only the BKG-200 company-settings persistence boundary.

    Returns:
        None: Alembic drops the location index and both new tables.
    """
    op.drop_index(
        "ix_booking_location_org_status_name",
        table_name="booking_locations",
    )
    op.drop_table("booking_locations")
    op.drop_table("booking_company_settings")
