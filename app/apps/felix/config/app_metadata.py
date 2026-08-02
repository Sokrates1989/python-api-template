"""Static non-secret product and route metadata for the Felix backend app."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FelixAppConfig:
    """Describe static metadata for the Felix backend app.

    Attributes:
        app_id (str): Stable backend app identifier.
        display_name (str): Human-readable name shown by backend tooling.
        description (str): Product description shown by OpenAPI tooling.
        backend_data_profile (str): Preferred persistence profile for Felix.
        felix_mount_prefix (str): External FastAPI mount prefix for app routes.
        felix_public_prefix (str): Public root for app-domain endpoints.
        sync_public_prefix (str): Public root for generic sync endpoints.
        exposes_sync_routes (bool): Whether the app contributes sync routes.
    """

    app_id: str = "felix"
    display_name: str = "Felix API"
    description: str = (
        "Production API for the Felix wellness app, including account, "
        "wellness, synchronization, notifications, and optional AI chat services."
    )
    backend_data_profile: str = "postgresql"
    felix_mount_prefix: str = "/felix"
    felix_public_prefix: str = "/felix/v1"
    sync_public_prefix: str = "/v1/sync"
    exposes_sync_routes: bool = True


FELIX_APP_CONFIG = FelixAppConfig()

# Standard selected-app metadata export consumed by generic API composition.
BACKEND_APP_CONFIG = FELIX_APP_CONFIG
