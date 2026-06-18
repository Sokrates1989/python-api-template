"""Postgres Template app backend definition."""
from __future__ import annotations

from apps.contracts import (
    BackendAppDefinition,
    OpenApiSecurityScheme,
    RouteRegistration,
    RouteSecurityRequirement,
)
from apps.postgres_template.config import POSTGRES_TEMPLATE_APP_CONFIG
from apps.postgres_template.routes import sync, wellness

# Wellness and sync route prefix roots used for OpenAPI security matching.
_WELLNESS_PREFIX = POSTGRES_TEMPLATE_APP_CONFIG.wellness_mount_prefix + "/v1/wellness"
_SYNC_PREFIX = POSTGRES_TEMPLATE_APP_CONFIG.sync_mount_prefix + "/v1/sync"

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
    openapi_security_schemes=(
        OpenApiSecurityScheme(
            name="UserBearerAuth",
            scheme={
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": (
                    "JWT access token issued by the configured auth provider "
                    "(Keycloak or Cognito). In local dev with AUTH_PROVIDER=none "
                    "any non-empty string is accepted — enter 'dev-token' to test."
                ),
            },
        ),
    ),
    openapi_route_security=(
        RouteSecurityRequirement(
            path_prefix=_WELLNESS_PREFIX,
            requirement={"UserBearerAuth": []},
        ),
        RouteSecurityRequirement(
            path_prefix=_SYNC_PREFIX,
            requirement={"UserBearerAuth": []},
        ),
    ),
)
