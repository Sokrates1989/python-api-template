"""Selected-app definition for the Booking Service backend foundation.

The phase-zero profile intentionally exposes no product routes. It retains the
PostgreSQL, Redis, and app-owned migration boundaries required by later booking
domain slices while preventing the detached neutral records starter from
leaking into the product API.
"""

from __future__ import annotations

from apps.booking_service.config import BACKEND_APP_CONFIG
from apps.contracts import BackendAppDefinition


BACKEND_APP_DEFINITION = BackendAppDefinition(
    app_id=BACKEND_APP_CONFIG.app_id,
    display_name=BACKEND_APP_CONFIG.display_name,
    backend_data_profile=BACKEND_APP_CONFIG.backend_data_profile,
    route_registrations=(),
    migration_version_locations=("migrations/versions",),
    exposes_sync_routes=False,
    requires_database=True,
    requires_redis=True,
    include_shared_routes=False,
    shared_route_groups=(),
    openapi_security_schemes=(),
    openapi_route_security=(),
)
