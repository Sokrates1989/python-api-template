"""Create Felix access-readiness SQL table.

Revision ID: felix_004_access_readiness
Revises: felix_003_checkin_metadata
Create Date: 2026-07-04 00:00:00.000000

Access readiness stores setup completion, legal acceptance, and setupPayload
feature switches globally for authenticated Felix users so PWA, Flutter web,
and mobile clients can share the same setup state.
"""

from alembic import op
import sqlalchemy as sa


revision = "felix_004_access_readiness"
down_revision = "felix_003_checkin_metadata"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    """Return whether a table already exists.

    Args:
        table_name (str): Database table name to inspect.

    Returns:
        bool: True when the table is already present.

    Side Effects:
        Reads database metadata through the Alembic bind.
    """
    return sa.inspect(op.get_bind()).has_table(table_name)


def _index_exists(table_name: str, index_name: str) -> bool:
    """Return whether a named index already exists on a table.

    Args:
        table_name (str): Database table name to inspect.
        index_name (str): Index name to find.

    Returns:
        bool: True when the index exists.

    Side Effects:
        Reads database index metadata through the Alembic bind.
    """
    indexes = sa.inspect(op.get_bind()).get_indexes(table_name)
    return any(index.get("name") == index_name for index in indexes)


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str]) -> None:
    """Create an index when local legacy data is missing it.

    Args:
        index_name (str): Name of the index to create.
        table_name (str): Table receiving the index.
        columns (list[str]): Ordered table columns included in the index.

    Returns:
        None.

    Side Effects:
        Creates an index when it does not already exist.
    """
    if not _index_exists(table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=False)


def upgrade() -> None:
    """Create the Felix-owned access-readiness table.

    Args:
        None.

    Returns:
        None.

    Side Effects:
        Adds ``felix_access_readiness`` and its user lookup index.
    """
    if not _table_exists("felix_access_readiness"):
        op.create_table(
            "felix_access_readiness",
            sa.Column("pk", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.String(length=255), nullable=False),
            sa.Column("setup_completed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("setup_completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("legal_accepted_version", sa.String(length=128), nullable=True),
            sa.Column("legal_accepted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("setup_payload", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("pk"),
            sa.UniqueConstraint("user_id", name="uq_felix_access_readiness_user_id"),
        )
    _create_index_if_missing(
        "ix_felix_access_readiness_user_id",
        "felix_access_readiness",
        ["user_id"],
    )


def downgrade() -> None:
    """Drop the Felix-owned access-readiness table.

    Args:
        None.

    Returns:
        None.

    Side Effects:
        Removes ``felix_access_readiness`` and its indexes.
    """
    if _table_exists("felix_access_readiness"):
        if _index_exists("felix_access_readiness", "ix_felix_access_readiness_user_id"):
            op.drop_index("ix_felix_access_readiness_user_id", table_name="felix_access_readiness")
        op.drop_table("felix_access_readiness")
