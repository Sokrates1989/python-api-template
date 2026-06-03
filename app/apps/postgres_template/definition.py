"""Postgres Template app backend definition."""
from __future__ import annotations

from apps.contracts import BackendAppDefinition, RouteRegistration
from apps.postgres_template.config import POSTGRES_TEMPLATE_APP_CONFIG
from apps.postgres_template.routes import sync, wellness


POSTGRES_TEMPLATE_APP_DEFINITION = BackendAppDefinition(
    app_id=POSTGRES_TEMPLATE_APP_CONFIG.app_id,
    display_name=POSTGRES_TEMPLATE_APP_CONFIG.display_name,
    backend_data_profile=POSTGRES_TEMPLATE_APP_CONFIG.backend_data_profile,
    route_registrations=(
        RouteRegistration(
            router=wellness.router,
            external_prefix=POSTGRES_TEMPLATE_APP_CONFIG.wellness_mount_prefix,
            public_prefix=POSTGRES_TEMPLATE_APP_CONFIG.wellness_public_prefix,
        ),
        RouteRegistration(
            router=sync.router,
            external_prefix=POSTGRES_TEMPLATE_APP_CONFIG.sync_mount_prefix,
            public_prefix=POSTGRES_TEMPLATE_APP_CONFIG.sync_public_prefix,
        ),
    ),
    exposes_sync_routes=POSTGRES_TEMPLATE_APP_CONFIG.exposes_sync_routes,
)
