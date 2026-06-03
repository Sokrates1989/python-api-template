"""Metadata for the MongoDB Template backend app."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MongoDBTemplateAppConfig:
    """Describe static metadata for the MongoDB Template backend app."""

    app_id: str = "mongodb_template"
    display_name: str = "MongoDB Template"
    backend_data_profile: str = "mongodb"
    wellness_mount_prefix: str = "/mongodb-template"
    wellness_public_prefix: str = "/mongodb-template/v1/wellness"
    exposes_sync_routes: bool = False


MONGODB_TEMPLATE_APP_CONFIG = MongoDBTemplateAppConfig()
