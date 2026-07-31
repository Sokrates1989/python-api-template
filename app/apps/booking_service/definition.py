"""Generated authenticated PostgreSQL definition for booking_service."""

from __future__ import annotations

from apps.booking_service.config import BACKEND_APP_CONFIG
from apps.booking_service.routes import records
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
    route_registrations=(RouteRegistration(router=records.router),),
    migration_version_locations=("migrations/versions",),
    exposes_sync_routes=False,
    requires_database=True,
    requires_redis=True,
    include_shared_routes=False,
    shared_route_groups=(),
    openapi_security_schemes=(
        OpenApiSecurityScheme(
            name="UserBearerAuth",
            scheme={"type": "http", "scheme": "bearer", "bearerFormat": "JWT"},
        ),
    ),
    openapi_route_security=(
        RouteSecurityRequirement(
            path_prefix="/records",
            requirement={"UserBearerAuth": []},
        ),
    ),
)
