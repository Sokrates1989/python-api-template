# Entry point for the FastAPI app
import logging

import uvicorn
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from api.settings import settings
from api.middleware import setup_middleware
from api.config import setup_openapi, create_lifespan_handler
from backend.adapters.provider_capability_factory import normalize_provider_db_type
from backend.observability import log_event

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

# Include shared routes only when the app definition allows it.
registered_routers: list[str] = []
if selected_backend_app.include_shared_routes:
    from api.shared_routes import test, files, packages, database_lock, users, examples

    app.include_router(test.router)
    app.include_router(files.router)
    app.include_router(packages.router)
    app.include_router(database_lock.router)
    app.include_router(users.router)
    app.include_router(examples.router)
    registered_routers.extend(["/users", "/database/*", "/examples"])

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
    if r is None:
        return {"message": "Hello from FastAPI!"}
    visits = r.incr("visits")
    return {"message": f"Hello from FastAPI! This page has been visited {visits} times."}


@app.get("/cache/{key}")
def get_cache(key: str):
    if r is None:
        raise HTTPException(status_code=503, detail="Redis not available")
    value = r.get(key)
    if value is None:
        raise HTTPException(status_code=404, detail="Key not found")
    return {"key": key, "value": value.decode()}


@app.post("/cache/{key}")
def set_cache(key: str, value: str):
    if r is None:
        raise HTTPException(status_code=503, detail="Redis not available")
    r.set(key, value)
    return {"message": f"Stored key '{key}' with value '{value}'"}


# Health check endpoint.
@app.get("/health")
def check_health():
    database_type = getattr(app.state, "database_type", settings.normalized_db_type())
    startup_probe = getattr(app.state, "startup_probe", None)
    wellness_route_prefix = selected_backend_app.find_route_prefix("wellness")

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
        "wellness_route_prefix": wellness_route_prefix,
        "sync_routes_enabled": selected_backend_app.exposes_sync_routes,
        "requires_database": selected_backend_app.requires_database,
        "requires_redis": selected_backend_app.requires_redis,
        "include_shared_routes": selected_backend_app.include_shared_routes,
        "startup_probe_status": probe_status,
    }


# Get Image version.
@app.get("/version")
def get_version():
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
