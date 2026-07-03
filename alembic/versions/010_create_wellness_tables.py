"""Preserve the legacy global Felix wellness revision marker.

Revision ID: 010_create_wellness_tables
Revises: 009_add_sync_support
Create Date: 2026-07-02 00:00:00.000000

Earlier local Felix databases can have this revision stored in the global
``alembic_version`` table because wellness tables briefly lived in the shared
migration stream. The tables are now app-owned, so this compatibility migration
does not create product schema. It only lets Alembic advance from the legacy
marker to the current shared sync-conflict migration.
"""

revision = "010_create_wellness_tables"
down_revision = "009_add_sync_support"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Advance past the legacy Felix wellness global marker.

    Args:
        None.

    Returns:
        None.

    Side Effects:
        None. Product-owned wellness tables are managed by the Felix app
        migration stream instead of this global compatibility marker.
    """


def downgrade() -> None:
    """Revert the no-op compatibility marker.

    Args:
        None.

    Returns:
        None.

    Side Effects:
        None. The marker has no schema effects to undo.
    """
