# Entry point for the FastAPI app
import uvicorn
import redis
from fastapi import FastAPI, HTTPException, Depends
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from api.settings import settings
from api.routes import test, files, packages, database_lock
from api.security import verify_admin_key
from api.middleware import setup_middleware
from api.config import setup_openapi, setup_lifecycle_events
from backend.services.sql.backup_service import BackupService
from backend.services.neo4j.backup_service import Neo4jBackupService

# Initialize FastAPI application
app = FastAPI(
    title="Python API Template",
    description="A flexible API template with SQL and Neo4j support, including database backup/restore",
    version=settings.IMAGE_TAG
)

# Configure OpenAPI and lifecycle events
setup_openapi(app)
setup_lifecycle_events(app)

# Initialize backup services
class DatabaseStats(BaseModel):
    database_type: str
    stats: dict

sql_backup_service = BackupService()
neo4j_backup_service = Neo4jBackupService()

# Include core routers (work with any database)
app.include_router(test.router)
app.include_router(files.router)
app.include_router(packages.router)
app.include_router(database_lock.router)

# Conditionally include database-specific routers
if settings.DB_TYPE in ["postgresql", "postgres", "mysql", "sqlite"]:
    # SQL-specific routes - uses relational database tables
    from api.routes.sql import examples, users
    app.include_router(examples.router)
    app.include_router(users.router)
    print(f"✅ Registered SQL-specific routes (/examples/, /users/) for {settings.DB_TYPE}")
elif settings.DB_TYPE == "neo4j":
    # Neo4j-specific routes - uses graph database nodes
    from api.routes.neo4j import examples, users
    app.include_router(examples.router)
    app.include_router(users.router)
    print(f"✅ Registered Neo4j-specific routes (/example-nodes/, /users/) for {settings.DB_TYPE}")
else:
    print(f"ℹ️  No database-specific example routes registered - DB_TYPE={settings.DB_TYPE}")


# Setup middleware
setup_middleware(app)

# Initialize Redis connection
print(f"🔧 Connecting to Redis at: {settings.REDIS_URL}")
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
    return {"status": "OK"}

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
    db_type = settings.DB_TYPE.lower()
    try:
        if db_type in ["postgresql", "postgres", "mysql", "sqlite"]:
            stats = await run_in_threadpool(sql_backup_service.get_database_stats)
        elif db_type == "neo4j":
            stats = await run_in_threadpool(neo4j_backup_service.get_database_stats)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported DB_TYPE for stats: {settings.DB_TYPE}")
        return DatabaseStats(database_type=db_type, stats=stats)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get database stats: {str(e)}")