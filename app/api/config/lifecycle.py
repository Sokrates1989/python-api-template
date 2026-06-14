"""Application lifecycle handling via FastAPI lifespan context."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.settings import settings
from apps.registry import get_backend_app_definition
from backend.database import close_database, get_database_handler, initialize_database
from backend.database.startup_probe import run_provider_startup_probe
from backend.observability import log_event

logger = logging.getLogger("api.lifecycle")


def create_lifespan_handler():
    """Create FastAPI lifespan context for startup and shutdown orchestration."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Resolve selected backend app to determine infrastructure requirements.
        selected_app = get_backend_app_definition(settings.APP_PROFILE)

        log_event(
            logger,
            logging.INFO,
            "startup.begin",
            db_type=settings.normalized_db_type(),
            db_mode=settings.DB_MODE,
            app_profile=settings.APP_PROFILE,
            requires_database=selected_app.requires_database,
            requires_redis=selected_app.requires_redis,
        )

        # Initialize database only when required by the app definition.
        if selected_app.requires_database:
            result = await initialize_database()
            if result.get("status") != "success":
                log_event(
                    logger,
                    logging.ERROR,
                    "startup.database_init_failed",
                    db_type=settings.normalized_db_type(),
                    details=result,
                )
                raise RuntimeError(f"Database initialization failed: {result.get('message')}")

            handler = get_database_handler()
            startup_probe = await run_provider_startup_probe(handler)
            app.state.startup_probe = startup_probe
            app.state.database_type = getattr(handler, "db_type", settings.normalized_db_type())

            if startup_probe.get("status") != "success":
                log_event(
                    logger,
                    logging.ERROR,
                    "startup.provider_probe_failed",
                    probe=startup_probe,
                )
                raise RuntimeError(
                    f"Provider startup probe failed: {startup_probe.get('message', 'unknown error')}"
                )

            log_event(
                logger,
                logging.INFO,
                "startup.provider_probe_ok",
                probe=startup_probe,
            )

            if settings.is_sql_database():
                from backend.database.migrations import run_migrations
                run_migrations(fail_on_error=True)
                log_event(
                    logger,
                    logging.INFO,
                    "startup.migrations_ok",
                    db_type=settings.normalized_db_type(),
                )
        else:
            # For no-database apps, mark startup probe as skipped.
            app.state.startup_probe = {"status": "skipped"}
            app.state.database_type = "none"
            log_event(
                logger,
                logging.INFO,
                "startup.database_skipped",
                app_profile=settings.APP_PROFILE,
            )

        log_event(
            logger,
            logging.INFO,
            "startup.complete",
            db_type=settings.normalized_db_type(),
            app_profile=settings.APP_PROFILE,
        )

        try:
            yield
        finally:
            log_event(logger, logging.INFO, "shutdown.begin")
            if selected_app.requires_database:
                await close_database()
            log_event(logger, logging.INFO, "shutdown.complete")

    return lifespan
