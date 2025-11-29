"""Application lifecycle event handlers."""
from fastapi import FastAPI
from backend.database import initialize_database, close_database
from backend.database.migrations import run_migrations


def setup_lifecycle_events(app: FastAPI) -> None:
    """
    Configure application lifecycle events (startup and shutdown).
    
    Args:
        app: The FastAPI application instance
    """
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
