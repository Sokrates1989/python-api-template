"""Application lifecycle handling via FastAPI lifespan context."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.settings import settings
from backend.database import close_database, get_database_handler, initialize_database
from backend.database.migrations import run_migrations
from backend.database.startup_probe import run_provider_startup_probe
from backend.observability import log_event

logger = logging.getLogger("api.lifecycle")


def create_lifespan_handler():
    """Create FastAPI lifespan context for startup and shutdown orchestration."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        log_event(
            logger,
            logging.INFO,
            "startup.begin",
            db_type=settings.normalized_db_type(),
            db_mode=settings.DB_MODE,
        )

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
            run_migrations(fail_on_error=True)
            log_event(
                logger,
                logging.INFO,
                "startup.migrations_ok",
                db_type=settings.normalized_db_type(),
            )

        log_event(
            logger,
            logging.INFO,
            "startup.complete",
            db_type=settings.normalized_db_type(),
        )

        try:
            yield
        finally:
            log_event(logger, logging.INFO, "shutdown.begin")
            await close_database()
            log_event(logger, logging.INFO, "shutdown.complete")

    return lifespan
