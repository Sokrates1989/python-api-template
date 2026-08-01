"""Selected-app definition for the Booking Service backend.

The profile retains PostgreSQL, Redis, and app-owned migration boundaries and
registers only approved product routers. BKG-103 adds scoped membership
administration beneath the existing organization route family while the
detached neutral records starter and all later booking routes remain absent.
"""

from __future__ import annotations

from apps.booking_service.config import BACKEND_APP_CONFIG
from apps.booking_service.routes import me_router, organization_router, platform_router
from apps.contracts import (
    BackendAppDefinition,
    OpenApiSecurityScheme,
    RouteRegistration,
    RouteSecurityRequirement,
)


BACKEND_APP_DEFINITION = BackendAppDefinition(
    app_id=BACKEND_APP_CONFIG.app_id,
    display_name=BACKEND_APP_CONFIG.display_name,
    backend_data_profile=BACKEND_APP_CONFIG.backend_data_profile,
    route_registrations=(
        RouteRegistration(router=me_router, public_prefix="/v1/me"),
        RouteRegistration(
            router=platform_router,
            public_prefix="/v1/platform/organizations",
        ),
        RouteRegistration(
            router=organization_router,
            public_prefix="/v1/organizations",
        ),
    ),
    migration_version_locations=("migrations/versions",),
    exposes_sync_routes=False,
    requires_database=True,
    requires_redis=True,
    include_shared_routes=False,
    shared_route_groups=(),
    openapi_security_schemes=(
        OpenApiSecurityScheme(
            name="BookingBearer",
            scheme={
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": (
                    "Keycloak access token for the configured Booking API "
                    "client. Roles are read only from that client."
                ),
            },
        ),
    ),
    openapi_route_security=(
        RouteSecurityRequirement(
            path_prefix="/v1/me/identity",
            requirement={"BookingBearer": []},
            methods=("get",),
            exact_path=True,
        ),
        RouteSecurityRequirement(
            path_prefix="/v1/me/context",
            requirement={"BookingBearer": []},
            methods=("get",),
            exact_path=True,
        ),
        RouteSecurityRequirement(
            path_prefix="/v1/platform/organizations",
            requirement={"BookingBearer": []},
            methods=("get", "post"),
        ),
        RouteSecurityRequirement(
            path_prefix="/v1/organizations",
            requirement={"BookingBearer": []},
            methods=("get", "post", "put"),
        ),
    ),
)
