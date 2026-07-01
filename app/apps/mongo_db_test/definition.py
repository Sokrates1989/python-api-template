"""
Mongo DB Test backend definition.

This dynamically created app currently exposes only the shared core API
routers. App-specific routers can be added later by creating route modules and
registering them in `route_registrations`.
"""
from __future__ import annotations

from apps.contracts import BackendAppDefinition


BACKEND_APP_DEFINITION = BackendAppDefinition(
    app_id="mongo_db_test",
    display_name="Mongo DB Test",
    backend_data_profile="mongodb",
    route_registrations=(),
    exposes_sync_routes=False,
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
