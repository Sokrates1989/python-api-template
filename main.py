# Entry point for the FastAPI app
from fastapi import FastAPI, Request
import uvicorn
from api.settings import settings
from api.test import router as test_router

app = FastAPI()
app.include_router(test_router)


# Middleware to log request headers
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

# Get Root endpoint.
@app.get('/')
def read_root():
    return {'message': 'Hello from FastAPI Template!'}

# Health check endpoint.
@app.get("/health")
def check_health():
    return {"status": "OK"}

# Get Image version.
@app.get("/version")
def get_version():
    return {"IMAGE_TAG": f"{settings.IMAGE_TAG}"}