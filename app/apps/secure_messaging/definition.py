"""
Backend app definition for secure messaging.

This app provides an internal-only notification API that does not require
a database, Redis, or shared routes.
"""
from apps.contracts import BackendAppDefinition, RouteRegistration
from apps.contracts import OpenApiSecurityScheme, RouteSecurityRequirement
from apps.secure_messaging.config.app_metadata import SecureMessagingAppConfig
from apps.secure_messaging.routes import notifications

# Create app metadata instance
APP_METADATA = SecureMessagingAppConfig()

# Backend app definition exported for registry discovery
BACKEND_APP_DEFINITION = BackendAppDefinition(
    app_id=APP_METADATA.app_id,
    display_name=APP_METADATA.display_name,
    backend_data_profile=APP_METADATA.backend_data_profile,
    route_registrations=(
        RouteRegistration(
            router=notifications.router,
            external_prefix=APP_METADATA.notify_mount_prefix,
            public_prefix=APP_METADATA.notify_public_prefix,
        ),
    ),
    exposes_sync_routes=APP_METADATA.exposes_sync_routes,
    requires_database=APP_METADATA.requires_database,
    requires_redis=APP_METADATA.requires_redis,
    include_shared_routes=APP_METADATA.include_shared_routes,
    openapi_security_schemes=(
        OpenApiSecurityScheme(
            name="SecureMessagingBearer",
            scheme={
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "API token",
                "description": (
                    "Use Authorization: Bearer <token>. The token is configured "
                    "with SECURE_MESSAGING_AUTH_TOKEN or "
                    "SECURE_MESSAGING_AUTH_TOKEN_FILE."
                ),
            },
        ),
    ),
    openapi_route_security=(
        RouteSecurityRequirement(
            path_prefix="/v1/notify",
            requirement={"SecureMessagingBearer": []},
            methods=("post",),
            exact_path=True,
        ),
    ),
)
