"""
Entry point for the selected FastAPI backend app.

The module composes product-owned route registrations from `app/apps/<app_id>`
with explicitly selected shared route groups. Shared infrastructure stays here,
while app-specific routes, schemas, services, and migrations stay in their
own app slices.
"""
import logging

import uvicorn
from fastapi import APIRouter, Depends, FastAPI, HTTPException
from pydantic import BaseModel
from api.settings import settings
from api.middleware import setup_middleware
from api.config import setup_openapi, create_lifespan_handler
from backend.adapters.provider_capability_factory import normalize_provider_db_type
from backend.logging_config import setup_logging
from backend.observability import log_event

setup_logging(log_dir=settings.LOG_DIR)

logger = logging.getLogger("app.main")
app_profile = settings.normalized_app_profile()
selected_backend_app = settings.get_backend_app_definition()

# Initialize FastAPI application with app-specific branding
app = FastAPI(
    title=settings.APP_NAME,
    description=settings.APP_DESCRIPTION,
    version=settings.IMAGE_TAG,
    lifespan=create_lifespan_handler(),
)

# Configure OpenAPI and lifecycle events
setup_openapi(app)


def _available_shared_route_groups() -> dict[str, APIRouter]:
    """
    Return shared route groups that apps may explicitly opt into.

    Args:
        None.

    Returns:
        dict[str, APIRouter]: Mapping from route group name to router instance.

    Side Effects:
        Imports shared route modules lazily so apps that disable shared routes
        do not import unused route handlers.
    """
    from api.shared_routes import database_lock, examples, files, packages, test, users

    return {
        "test": test.router,
        "files": files.router,
        "packages": packages.router,
        "database_lock": database_lock.router,
        "users": users.router,
        "examples": examples.router,
    }


def _include_selected_shared_routes(fastapi_app: FastAPI) -> tuple[str, ...]:
    """
    Mount only the shared route groups selected by the active backend app.

    Args:
        fastapi_app (FastAPI): Application instance receiving shared routers.

    Returns:
        tuple[str, ...]: Public route prefixes mounted from shared route groups.

    Side Effects:
        Mutates the FastAPI app by including selected APIRouter instances.
        Logs a warning for unknown route group names.
    """
    if not selected_backend_app.include_shared_routes:
        return ()

    route_groups = _available_shared_route_groups()
    mounted_prefixes: list[str] = []
    for group_name in selected_backend_app.shared_route_groups:
        router = route_groups.get(group_name)
        if router is None:
            log_event(
                logger,
                logging.WARNING,
                "app.shared_route_group.unknown",
                group=group_name,
                app_id=selected_backend_app.app_id,
            )
            continue

        fastapi_app.include_router(router)
        prefix = getattr(router, "prefix", "") or "/"
        mounted_prefixes.append(f"{prefix}/*")

    return tuple(mounted_prefixes)


# Include selected shared route groups before app-owned routes.
registered_routers: list[str] = list(_include_selected_shared_routes(app))

# Mount app-owned route registrations
for route_registration in selected_backend_app.route_registrations:
    app.include_router(
        route_registration.router,
        prefix=route_registration.external_prefix,
    )
    registered_routers.append(f"{route_registration.resolved_public_prefix()}/*")

log_event(
    logger,
    logging.INFO,
    "app.routers.registered",
    routers=registered_routers,
    db_type=settings.DB_TYPE,
    app_profile=app_profile,
    shared_routes=selected_backend_app.include_shared_routes,
    shared_route_groups=selected_backend_app.shared_route_groups,
)


# Setup middleware
setup_middleware(app)

# Initialize Redis only when the app definition requires it.
r = None
if selected_backend_app.requires_redis:
    import redis

    log_event(logger, logging.INFO, "redis.client.initialize", redis_url=settings.REDIS_URL)
    r = redis.Redis.from_url(settings.REDIS_URL)


# Redis test Endpoints (only available when Redis is enabled).
@app.get("/")
def read_root():
    """
    Return a minimal root response for the selected backend app.

    Args:
        None.

    Returns:
        dict: Greeting payload, including Redis-backed visit count only when
        Redis is enabled for the selected app.

    Side Effects:
        Increments the Redis `visits` key when Redis is configured.
    """
    if r is None:
        return {"message": "Hello from FastAPI!"}
    visits = r.incr("visits")
    return {"message": f"Hello from FastAPI! This page has been visited {visits} times."}


@app.get("/cache/{key}")
def get_cache(key: str):
    """
    Read a Redis cache value when the selected app enables Redis.

    Args:
        key (str): Redis key to read.

    Returns:
        dict: Cache key and decoded value.

    Raises:
        HTTPException: HTTP 503 when Redis is disabled and HTTP 404 when the
        key does not exist.
    """
    if r is None:
        raise HTTPException(status_code=503, detail="Redis not available")
    value = r.get(key)
    if value is None:
        raise HTTPException(status_code=404, detail="Key not found")
    return {"key": key, "value": value.decode()}


@app.post("/cache/{key}")
def set_cache(key: str, value: str):
    """
    Write a Redis cache value when the selected app enables Redis.

    Args:
        key (str): Redis key to write.
        value (str): Value to store.

    Returns:
        dict: Confirmation message.

    Raises:
        HTTPException: HTTP 503 when Redis is disabled for the selected app.
    """
    if r is None:
        raise HTTPException(status_code=503, detail="Redis not available")
    r.set(key, value)
    return {"message": f"Stored key '{key}' with value '{value}'"}


# Health check endpoint.
@app.get("/health")
def check_health():
    """
    Return feature-neutral runtime diagnostics for the selected backend app.

    Args:
        None.

    Returns:
        dict: App, database, provider, route, and startup-probe diagnostics.

    Side Effects:
        Reads FastAPI application state populated during startup.
    """
    database_type = getattr(app.state, "database_type", settings.normalized_db_type())
    startup_probe = getattr(app.state, "startup_probe", None)

    # Report startup probe status, handling "skipped" for no-db apps.
    probe_status = "unknown"
    if isinstance(startup_probe, dict):
        probe_status = startup_probe.get("status", "unknown")
    elif not selected_backend_app.requires_database:
        probe_status = "skipped"

    return {
        "status": "OK",
        "app_profile": app_profile,
        "backend_app": selected_backend_app.display_name,
        "backend_data_profile": selected_backend_app.backend_data_profile,
        "database_type": database_type,
        "provider_profile": normalize_provider_db_type(database_type),
        "registered_route_prefixes": list(selected_backend_app.registered_route_prefixes()),
        "shared_route_groups": list(selected_backend_app.shared_route_groups)
        if selected_backend_app.include_shared_routes
        else [],
        "sync_routes_enabled": selected_backend_app.exposes_sync_routes,
        "requires_database": selected_backend_app.requires_database,
        "requires_redis": selected_backend_app.requires_redis,
        "include_shared_routes": selected_backend_app.include_shared_routes,
        "startup_probe_status": probe_status,
    }


# Get Image version.
@app.get("/version")
def get_version():
    """
    Return the runtime image tag.

    Args:
        None.

    Returns:
        dict: `IMAGE_TAG` value from settings.

    Side Effects:
        None.
    """
    return {"IMAGE_TAG": f"{settings.IMAGE_TAG}"}


# # Test endpoint for hot-reloading demonstration
# @app.get("/hot-reload-test")
# def hot_reload_test():
#     return {"message": "This endpoint was added while the container was running!", "timestamp": "2024-01-01"}


if selected_backend_app.requires_database:
    from api.shared_dependencies.security import verify_admin_key
    from backend.shared_services.backup_service import BackupService

    class DatabaseStats(BaseModel):
        """
        Response model for database statistics.

        Attributes:
            database_type (str): Active database provider reported by the
                backup/statistics service.
            stats (dict): Provider-specific database statistics.

        Returns:
            None: Pydantic model used for response serialization.

        Side Effects:
            None.
        """

        database_type: str
        stats: dict

    @app.get("/stats", response_model=DatabaseStats)
    async def get_database_stats(_: str = Depends(verify_admin_key)):
        """
        Return database statistics for database-backed apps.

        Args:
            _ (str): Validated admin credential from `verify_admin_key`.

        Returns:
            DatabaseStats: Active database type and provider-specific stats.

        Raises:
            HTTPException: Propagates backup service HTTP errors or returns
                HTTP 500 when statistics collection fails unexpectedly.
        """
        backup_service = BackupService()
        try:
            stats = await backup_service.get_database_stats()
            return DatabaseStats(database_type=backup_service.db_type, stats=stats)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to get database stats: {str(exc)}",
            ) from exc
