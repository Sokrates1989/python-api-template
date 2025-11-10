# Entry point for the FastAPI app
from fastapi import FastAPI, Request, HTTPException
import uvicorn
import redis
from api.settings import settings
from api.routes import test, files, packages
from backend.database import initialize_database, close_database
from backend.database.migrations import run_migrations

app = FastAPI()

# Application lifecycle events
@app.on_event("startup")
async def startup_event():
    """Initialize database connection and run migrations on startup."""
    try:
        await initialize_database()
        # Run database migrations automatically
        print("🔄 About to run migrations...")
        run_migrations()
        print("🔄 Migrations completed (or skipped)")
    except Exception as e:
        print(f"❌ Error during startup: {e}")
        import traceback
        traceback.print_exc()

@app.on_event("shutdown")
async def shutdown_event():
    """Close database connection on shutdown."""
    await close_database()

# Include core routers (work with any database)
app.include_router(test.router)
app.include_router(files.router)
app.include_router(packages.router)

# Conditionally include database-specific routers
if settings.DB_TYPE in ["postgresql", "postgres", "mysql", "sqlite"]:
    # SQL-specific routes - uses SQLAlchemy models
    from api.routes.sql import examples
    app.include_router(examples.router)
    print(f"✅ Registered SQL-specific routes (/examples/) for {settings.DB_TYPE}")
elif settings.DB_TYPE == "neo4j":
    # Neo4j-specific routes - uses graph database nodes
    from api.routes.neo4j import example_nodes
    app.include_router(example_nodes.router)
    print(f"✅ Registered Neo4j-specific routes (/example-nodes/) for {settings.DB_TYPE}")
else:
    print(f"ℹ️  No database-specific example routes registered - DB_TYPE={settings.DB_TYPE}")


print(f"🔧 Connecting to Redis at: {settings.REDIS_URL}")
r = redis.Redis.from_url(settings.REDIS_URL)

# Middleware to log request headers, if Debug is enabled in env variables.
if settings.DEBUG:
    @app.middleware("http")
    async def log_request_headers(request: Request, call_next):

        # Output basic request info.
        print(f"🔹 Received request: {request.method} {request.url}")

        # Read and log the request headers.
        headers = request.headers
        print(f"🔹 Received request with headers: {headers}")

        # Read and log the request body
        body = await request.body()
        print(f"🔹 Body: {body.decode('utf-8') if body else 'No Body'}")

        response = await call_next(request)
        return response


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

# Test endpoint for hot-reloading demonstration
@app.get("/hot-reload-test")
def hot_reload_test():
    return {"message": "This endpoint was added while the container was running!", "timestamp": "2024-01-01"}