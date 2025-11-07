# Entry point for the FastAPI app
from fastapi import FastAPI, Request, HTTPException
import uvicorn
import redis
from api.settings import settings
from api.routes import test, files
from backend.database import initialize_database, close_database

app = FastAPI()

# Application lifecycle events
@app.on_event("startup")
async def startup_event():
    """Initialize database connection on startup."""
    await initialize_database()

@app.on_event("shutdown")
async def shutdown_event():
    """Close database connection on shutdown."""
    await close_database()

app.include_router(test.router)
app.include_router(files.router)


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