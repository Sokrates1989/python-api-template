"""Metadata for the Felix backend app."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FelixAppConfig:
    """Describe static metadata for the Felix backend app.

    Attributes:
        app_id (str): Stable backend app identifier.
        display_name (str): Human-readable name shown by backend tooling.
        backend_data_profile (str): Preferred persistence profile for Felix.
        felix_mount_prefix (str): External FastAPI mount prefix for app routes.
        felix_public_prefix (str): Public root for app-domain endpoints.
        sync_public_prefix (str): Public root for generic sync endpoints.
        exposes_sync_routes (bool): Whether the app contributes sync routes.
    """

    app_id: str = "felix"
    display_name: str = "Felix"
    backend_data_profile: str = "postgresql"
    felix_mount_prefix: str = "/felix"
    felix_public_prefix: str = "/felix/v1"
    sync_public_prefix: str = "/v1/sync"
    exposes_sync_routes: bool = True


FELIX_APP_CONFIG = FelixAppConfig()
