"""Database lock middleware to prevent writes during restore operations."""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from api.settings import settings


async def block_writes_during_restore(request: Request, call_next):
    """
    Block write operations (POST, PUT, PATCH, DELETE) during database restore.
    
    This prevents data corruption by ensuring no data modifications occur while
    the database is being restored by an external backup-restore service.
    Read operations (GET) are allowed to continue.
    
    Exempted endpoints:
    - /database/* (database lock management endpoints)
    - /health (health check)
    - /version (version info)
    - /cache/* (Redis operations for testing)
    """
    # Allow database lock endpoints to proceed (they manage the lock)
    if request.url.path.startswith("/database/"):
        return await call_next(request)
    
    # Allow health, version, and cache endpoints
    if request.url.path in ["/health", "/version", "/"]:
        return await call_next(request)
    
    if request.url.path.startswith("/cache/"):
        return await call_next(request)
    
    # Check if database is locked for write operations
    if request.method in ["POST", "PUT", "PATCH", "DELETE"]:
        try:
            # Check lock status using the database_lock module
            from api.routes.database_lock import _check_lock
            lock_operation = _check_lock()
            
            if lock_operation:
                return JSONResponse(
                    status_code=503,
                    content={
                        "error": "Service temporarily unavailable",
                        "detail": f"Database is locked for {lock_operation} operation. Write operations are blocked to prevent data corruption.",
                        "operation_in_progress": lock_operation,
                        "database_type": settings.DB_TYPE,
                        "retry_after": "Poll GET /database/lock-status to check lock status"
                    }
                )
        except Exception as e:
            # If we can't check the lock, allow the request (fail open)
            print(f"Warning: Failed to check database lock: {e}")
    
    return await call_next(request)


def setup_database_lock_middleware(app: FastAPI) -> None:
    """
    Configure database lock middleware for the FastAPI application.
    
    Args:
        app: The FastAPI application instance
    """
    app.middleware("http")(block_writes_during_restore)
