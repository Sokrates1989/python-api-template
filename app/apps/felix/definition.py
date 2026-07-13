"""
Felix backend definition.

This module declares the route families owned by the Felix backend
slice. Felix mounts app-domain endpoints under the /felix prefix and
exposes sync endpoints for offline-first support.
"""

from __future__ import annotations

from apps.contracts import BackendAppDefinition, RouteRegistration
from apps.felix.config import FELIX_APP_CONFIG
from apps.felix.routes import ai_chat, sync, web_push, wellness
from backend.shared_services.background_service import BackgroundService


def _create_web_push_dispatch_service() -> BackgroundService:
    """Create Felix's explicitly configured durable Web Push worker.

    Returns:
        BackgroundService: Disabled metadata service or enabled dispatch loop.

    Side Effects:
        Imports runtime worker policy after app discovery. Secret/provider
        resolution remains deferred to enabled lifecycle startup.
    """
    from apps.felix.services.web_push_dispatch_service import (
        create_felix_web_push_background_service,
    )

    return create_felix_web_push_background_service()


FELIX_APP_DEFINITION = BackendAppDefinition(
    app_id=FELIX_APP_CONFIG.app_id,
    display_name=FELIX_APP_CONFIG.display_name,
    backend_data_profile=FELIX_APP_CONFIG.backend_data_profile,
    route_registrations=(
        RouteRegistration(
            router=wellness.router,
            external_prefix=FELIX_APP_CONFIG.felix_mount_prefix,
            public_prefix=FELIX_APP_CONFIG.felix_public_prefix,
        ),
        RouteRegistration(
            router=ai_chat.router,
            external_prefix=FELIX_APP_CONFIG.felix_mount_prefix,
            public_prefix=f"{FELIX_APP_CONFIG.felix_public_prefix}/ai-chat",
        ),
        RouteRegistration(
            router=sync.router,
            external_prefix="",
            public_prefix=FELIX_APP_CONFIG.sync_public_prefix,
        ),
        RouteRegistration(
            router=web_push.router,
            external_prefix=FELIX_APP_CONFIG.felix_mount_prefix,
            public_prefix=(
                f"{FELIX_APP_CONFIG.felix_public_prefix}/notifications/web-push"
            ),
        ),
    ),
    migration_version_locations=("migrations/versions",),
    exposes_sync_routes=FELIX_APP_CONFIG.exposes_sync_routes,
    shared_route_groups=("cache", "users"),
    background_service_factories=(_create_web_push_dispatch_service,),
)
