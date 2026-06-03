"""Metadata for the template backend app."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TemplateAppConfig:
    """Describe static metadata for the template backend app."""

    app_id: str = "template_app"
    display_name: str = "Template App"
    backend_data_profile: str = "postgresql"
    wellness_mount_prefix: str = "/template"
    wellness_public_prefix: str = "/template/v1/wellness"
    sync_public_prefix: str = "/v1/sync"
    exposes_sync_routes: bool = True


TEMPLATE_APP_CONFIG = TemplateAppConfig()
