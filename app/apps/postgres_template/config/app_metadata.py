"""Metadata for the Postgres Template backend app."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PostgresTemplateAppConfig:
    """Describe static metadata for the Postgres Template backend app."""

    app_id: str = "postgres_template"
    display_name: str = "Postgres Template"
    backend_data_profile: str = "postgresql"
    wellness_mount_prefix: str = "/postgres-template"
    wellness_public_prefix: str = "/postgres-template/v1/wellness"
    sync_mount_prefix: str = "/postgres-template"
    sync_public_prefix: str = "/postgres-template/v1/sync"
    exposes_sync_routes: bool = True


POSTGRES_TEMPLATE_APP_CONFIG = PostgresTemplateAppConfig()
