"""
MongoDB Template app backend definition.

This module declares app-owned route registrations and explicitly selects the
shared route groups that should remain available for the template profile.
"""
from __future__ import annotations

from apps.contracts import BackendAppDefinition, RouteRegistration
from apps.mongodb_template.config import MONGODB_TEMPLATE_APP_CONFIG
from apps.mongodb_template.routes import wellness


MONGODB_TEMPLATE_APP_DEFINITION = BackendAppDefinition(
    app_id=MONGODB_TEMPLATE_APP_CONFIG.app_id,
    display_name=MONGODB_TEMPLATE_APP_CONFIG.display_name,
    backend_data_profile=MONGODB_TEMPLATE_APP_CONFIG.backend_data_profile,
    route_registrations=(
        RouteRegistration(
            router=wellness.router,
            external_prefix=MONGODB_TEMPLATE_APP_CONFIG.wellness_mount_prefix,
            public_prefix=MONGODB_TEMPLATE_APP_CONFIG.wellness_public_prefix,
        ),
    ),
    exposes_sync_routes=MONGODB_TEMPLATE_APP_CONFIG.exposes_sync_routes,
    shared_route_groups=(
        "cache",
        "test",
        "files",
        "packages",
        "database_lock",
        "users",
        "examples",
    ),
)
