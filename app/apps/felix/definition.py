"""
Felix backend definition.

This module declares the route families owned by the Felix backend
slice. Felix mounts wellness under the /felix prefix and exposes
sync endpoints for offline-first support.
"""
from __future__ import annotations

from apps.contracts import BackendAppDefinition, RouteRegistration
from apps.felix.config import FELIX_APP_CONFIG
from apps.felix.routes import sync, wellness


FELIX_APP_DEFINITION = BackendAppDefinition(
    app_id=FELIX_APP_CONFIG.app_id,
    display_name=FELIX_APP_CONFIG.display_name,
    backend_data_profile=FELIX_APP_CONFIG.backend_data_profile,
    route_registrations=(
        RouteRegistration(
            router=wellness.router,
            external_prefix=FELIX_APP_CONFIG.wellness_mount_prefix,
            public_prefix=FELIX_APP_CONFIG.wellness_public_prefix,
        ),
        RouteRegistration(
            router=sync.router,
            external_prefix="",
            public_prefix=FELIX_APP_CONFIG.sync_public_prefix,
        ),
    ),
    migration_version_locations=("migrations/versions",),
    exposes_sync_routes=FELIX_APP_CONFIG.exposes_sync_routes,
    shared_route_groups=("users",),
)
