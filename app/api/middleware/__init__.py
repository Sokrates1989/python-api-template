"""
Middleware configuration for the FastAPI application.

Registers all middleware layers in the correct order. FastAPI (Starlette)
applies middleware in reverse registration order, so the last one added
wraps the outermost layer. CORS must be registered last here so it executes
first and handles preflight OPTIONS requests before any other logic.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.settings import settings
from .database_lock import setup_database_lock_middleware
from .logging import setup_logging_middleware


def setup_cors_middleware(app: FastAPI) -> None:
    """
    Register CORS middleware using origins from settings.

    Allows browsers running Flutter web or other local front-ends on the
    origins listed in CORS_ORIGINS to make cross-origin XHR/fetch requests.
    All HTTP methods and headers are permitted so preflight OPTIONS calls
    succeed without additional configuration.

    Args:
        app (FastAPI): The FastAPI application instance.

    Returns:
        None: Middleware is added as a side effect.

    Side Effects:
        Adds CORSMiddleware to the application middleware stack.
    """
    origins = settings.get_cors_origins()
    if not origins:
        return
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def setup_middleware(app: FastAPI) -> None:
    """
    Configure all middleware for the FastAPI application.

    Middleware are applied in the order they are called:
    1. Database lock middleware (blocks writes during restore)
    2. Logging middleware (explicit opt-in debug logging)
    3. CORS middleware (outermost layer — handles browser preflight first)

    Args:
        app (FastAPI): The FastAPI application instance.

    Returns:
        None: Middleware is added as a side effect.
    """
    setup_database_lock_middleware(app)
    setup_logging_middleware(app)
    setup_cors_middleware(app)
