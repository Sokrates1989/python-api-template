"""Metadata for the Felix backend app."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FelixAppConfig:
    """Describe static metadata for the Felix backend app."""

    app_id: str = "felix"
    display_name: str = "Felix"
    backend_data_profile: str = "postgresql"
    wellness_mount_prefix: str = "/felix"
    wellness_public_prefix: str = "/felix/v1/wellness"
    sync_public_prefix: str = "/v1/sync"
    exposes_sync_routes: bool = True


FELIX_APP_CONFIG = FelixAppConfig()
