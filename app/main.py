# Entry point for the FastAPI app
import logging

import uvicorn
import redis
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from api.settings import settings
from api.shared_dependencies.security import verify_admin_key
from api.shared_routes import test, files, packages, database_lock, users, examples
from api.middleware import setup_middleware
from api.config import setup_openapi, create_lifespan_handler
from backend.adapters.provider_capability_factory import normalize_provider_db_type
from backend.observability import log_event
from backend.shared_services.backup_service import BackupService

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

# Initialize backup services
class DatabaseStats(BaseModel):
    database_type: str
    stats: dict

# Include core routers (work with any database)
app.include_router(test.router)
app.include_router(files.router)
app.include_router(packages.router)
app.include_router(database_lock.router)
app.include_router(users.router)
app.include_router(examples.router)

registered_routers = ["/users", "/database/*", "/examples"]
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
)


# Setup middleware
setup_middleware(app)

# Initialize Redis connection
log_event(logger, logging.INFO, "redis.client.initialize", redis_url=settings.REDIS_URL)
r = redis.Redis.from_url(settings.REDIS_URL)


# Redis test Endpoints.
@app.get("/")
def read_root():
    visits = r.incr("visits")
    return {"message": f"Hello from FastAPI! This page has been visited {visits} times."}


@app.get("/cache/{key}")
def get_cache(key: str):
    value = r.get(key)
    if value is None:
        raise HTTPException(status_code=404, detail="Key not found")
    return {"key": key, "value": value.decode()}


@app.post("/cache/{key}")
def set_cache(key: str, value: str):
    r.set(key, value)
    return {"message": f"Stored key '{key}' with value '{value}'"}


# Health check endpoint.
@app.get("/health")
def check_health():
    database_type = getattr(app.state, "database_type", settings.normalized_db_type())
    startup_probe = getattr(app.state, "startup_probe", None)
    wellness_route_prefix = selected_backend_app.find_route_prefix("wellness")
    return {
        "status": "OK",
        "app_profile": app_profile,
        "backend_app": selected_backend_app.display_name,
        "backend_data_profile": selected_backend_app.backend_data_profile,
        "database_type": database_type,
        "provider_profile": normalize_provider_db_type(database_type),
        "wellness_route_prefix": wellness_route_prefix,
        "sync_routes_enabled": selected_backend_app.exposes_sync_routes,
        "startup_probe_status": (
            startup_probe.get("status", "unknown")
            if isinstance(startup_probe, dict)
            else "unknown"
        ),
    }


# Get Image version.
@app.get("/version")
def get_version():
    return {"IMAGE_TAG": f"{settings.IMAGE_TAG}"}


# # Test endpoint for hot-reloading demonstration
# @app.get("/hot-reload-test")
# def hot_reload_test():
#     return {"message": "This endpoint was added while the container was running!", "timestamp": "2024-01-01"}


@app.get("/stats", response_model=DatabaseStats)
async def get_database_stats(_: str = Depends(verify_admin_key)):
    backup_service = BackupService()
    try:
        stats = await backup_service.get_database_stats()
        return DatabaseStats(database_type=backup_service.db_type, stats=stats)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to get database stats: {str(exc)}")

