"""Reconcile organization labels with canonical public company names.

Revision ID: booking_service_006
Revises: booking_service_005
Create Date: 2026-08-03
"""

from __future__ import annotations

from alembic import op


revision = "booking_service_006"
down_revision = "booking_service_005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Repair labels that drifted before company-name synchronization.

    Returns:
        None: Matching organizations receive the canonical public name and one
        optimistic-revision increment inside Alembic's transaction.
    """
    op.execute(
        """
        UPDATE booking_organizations AS organization
        SET display_name = settings.public_name,
            revision = organization.revision + 1,
            updated_at = CURRENT_TIMESTAMP
        FROM booking_company_settings AS settings
        WHERE settings.organization_id = organization.id
          AND organization.display_name <> settings.public_name
        """
    )


def downgrade() -> None:
    """Retain reconciled labels because the discarded stale value is unknown.

    Returns:
        None: Schema downgrade remains safe and intentionally leaves the
        canonical user-visible value in place.

    Note:
        Restoring a known-stale label would recreate the defect and no prior
        value was retained. Application rollback remains compatible because
        both columns already existed before this data repair.
    """
