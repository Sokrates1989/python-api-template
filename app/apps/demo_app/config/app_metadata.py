"""Metadata for the demo backend app."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DemoAppConfig:
    """Describe static metadata for the demo backend app."""

    app_id: str = "demo_app"
    display_name: str = "Demo App"
    backend_data_profile: str = "mongodb"
    wellness_public_prefix: str = "/v1/wellness"
    exposes_sync_routes: bool = False


DEMO_APP_CONFIG = DemoAppConfig()
