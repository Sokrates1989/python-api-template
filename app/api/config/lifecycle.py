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
from backend.shared_services.background_service import BackgroundService

logger = logging.getLogger("api.lifecycle")


async def _start_background_services(selected_app: object) -> list[BackgroundService]:
    """Create and start every service declared by the selected backend app.

    Args:
        selected_app (object): App definition exposing deferred service
            factories.

    Returns:
        list[BackgroundService]: Started services in declaration order.

    Raises:
        Exception: Propagates factory/start failures after stopping services
            that already started.

    Side Effects:
        Starts selected-app background tasks and emits safe lifecycle events.
    """
    started: list[BackgroundService] = []
    factories = getattr(selected_app, "background_service_factories", ())
    try:
        for factory in factories:
            service = factory()
            await service.start()
            started.append(service)
            log_event(
                logger,
                logging.INFO,
                "startup.background_service_started",
                service=service.name,
            )
    except Exception:
        await _stop_background_services(started)
        raise
    return started


async def _stop_background_services(
    services: list[BackgroundService],
) -> None:
    """Stop selected-app services in reverse declaration order.

    Args:
        services (list[BackgroundService]): Services that started successfully.

    Returns:
        None.

    Side Effects:
        Stops background tasks and logs failures without skipping later stops.
    """
    for service in reversed(services):
        try:
            await service.stop()
            log_event(
                logger,
                logging.INFO,
                "shutdown.background_service_stopped",
                service=service.name,
            )
        except Exception as exc:
            log_event(
                logger,
                logging.ERROR,
                "shutdown.background_service_failed",
                service=service.name,
                error_code=type(exc).__name__,
            )


def create_lifespan_handler():
    """Create FastAPI lifespan context for startup and shutdown orchestration.

    Returns:
        Callable: FastAPI-compatible asynchronous lifespan handler.

    Side Effects:
        None until FastAPI enters the returned context manager.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Own selected-app infrastructure for one application lifetime.

        Args:
            app (FastAPI): Running application whose state receives provider
                and background-service diagnostics.

        Yields:
            None: Control to FastAPI while infrastructure remains available.

        Raises:
            RuntimeError: When database initialization, startup probing, or
                migrations fail.
            Exception: Propagates selected-app background-service start errors.

        Side Effects:
            Initializes and closes provider resources, starts and stops
            selected-app services, and records privacy-safe runtime state.
        """
        # Resolve selected backend app to determine infrastructure requirements.
        selected_app = get_backend_app_definition(settings.APP_PROFILE)
        background_services: list[BackgroundService] = []

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
                raise RuntimeError(
                    f"Database initialization failed: {result.get('message')}"
                )

            handler = get_database_handler()
            startup_probe = await run_provider_startup_probe(handler)
            app.state.startup_probe = startup_probe
            app.state.database_type = getattr(
                handler, "db_type", settings.normalized_db_type()
            )

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

        try:
            background_services = await _start_background_services(selected_app)
            app.state.background_services = background_services
            log_event(
                logger,
                logging.INFO,
                "startup.complete",
                db_type=settings.normalized_db_type(),
                app_profile=settings.APP_PROFILE,
            )
            yield
        finally:
            log_event(logger, logging.INFO, "shutdown.begin")
            await _stop_background_services(background_services)
            if selected_app.requires_database:
                await close_database()
            log_event(logger, logging.INFO, "shutdown.complete")

    return lifespan
