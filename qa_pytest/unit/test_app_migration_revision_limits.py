"""Tests Alembic revision identifiers against version-table storage limits."""

from apps.postgres_template.migrations.versions import (
    postgres_template_001_wellness_tables,
)


def test_postgres_template_initial_revision_fits_default_version_column() -> None:
    """Keep the first app revision within Alembic's default VARCHAR(32)."""

    revision = postgres_template_001_wellness_tables.revision

    assert revision == "postgres_tpl_001_wellness"
    assert len(revision) <= 32
