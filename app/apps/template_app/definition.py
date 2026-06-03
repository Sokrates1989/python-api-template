"""
Template app backend definition.

This module declares the route families owned by the template app backend
slice. The template app currently mounts wellness under a namespaced prefix
and intentionally exposes sync endpoints.
"""
from __future__ import annotations

from apps.contracts import BackendAppDefinition, RouteRegistration
from apps.template_app.config import TEMPLATE_APP_CONFIG
from apps.template_app.routes import sync, wellness


TEMPLATE_APP_DEFINITION = BackendAppDefinition(
    app_id=TEMPLATE_APP_CONFIG.app_id,
    display_name=TEMPLATE_APP_CONFIG.display_name,
    backend_data_profile=TEMPLATE_APP_CONFIG.backend_data_profile,
    route_registrations=(
        RouteRegistration(
            router=wellness.router,
            external_prefix=TEMPLATE_APP_CONFIG.wellness_mount_prefix,
            public_prefix=TEMPLATE_APP_CONFIG.wellness_public_prefix,
        ),
        RouteRegistration(
            router=sync.router,
            external_prefix="",
            public_prefix=TEMPLATE_APP_CONFIG.sync_public_prefix,
        ),
    ),
    exposes_sync_routes=TEMPLATE_APP_CONFIG.exposes_sync_routes,
)
