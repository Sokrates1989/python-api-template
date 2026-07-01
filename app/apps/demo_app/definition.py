"""
Demo app backend definition.

This module declares the route families owned by the demo app backend slice.
Shared route implementations are composed here so the monorepo can evolve
app-by-app without centralizing every decision in `main.py`.
"""
from __future__ import annotations

from apps.contracts import BackendAppDefinition, RouteRegistration
from apps.demo_app.config import DEMO_APP_CONFIG
from apps.demo_app.routes import wellness


DEMO_APP_DEFINITION = BackendAppDefinition(
    app_id=DEMO_APP_CONFIG.app_id,
    display_name=DEMO_APP_CONFIG.display_name,
    backend_data_profile=DEMO_APP_CONFIG.backend_data_profile,
    route_registrations=(
        RouteRegistration(
            router=wellness.router,
            external_prefix="",
            public_prefix=DEMO_APP_CONFIG.wellness_public_prefix,
        ),
    ),
    exposes_sync_routes=DEMO_APP_CONFIG.exposes_sync_routes,
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
