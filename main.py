# Entry point for the FastAPI app
from fastapi import FastAPI, Request
import uvicorn
from api.settings import settings

app = FastAPI()

@app.get('/')
def read_root():
    return {'message': 'Hello from FastAPI Template!'}

# Health check endpoint.
@app.get("/health")
def check_health():
    return {"status": "OK"}