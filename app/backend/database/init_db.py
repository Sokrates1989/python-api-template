"""
Database initialization and lifecycle management.
"""

from __future__ import annotations

import logging

from api.settings import settings
from backend.observability import log_event
from .factory import DatabaseFactory

logger = logging.getLogger("backend.database.init")


async def initialize_database():
    """
    Initialize database handler based on configuration.
    Retries connection with exponential backoff to handle DNS propagation delays.

    Returns:
        dict: Result of connection test with status and message
    """
    import asyncio
    import re

    db_type = settings.normalized_db_type()
    log_event(logger, logging.INFO, "database.initialize.begin", db_type=db_type)
    if settings.is_legacy_sql_database():
        log_event(
            logger,
            logging.WARNING,
            "database.initialize.legacy_sql_mode",
            db_type=db_type,
            support_matrix="postgresql/postgres, neo4j, mongodb",
        )

    if db_type == "neo4j":
        handler = DatabaseFactory.create_handler(
            db_type="neo4j",
            url=settings.get_neo4j_uri(),
            user=settings.DB_USER,
            password=settings.get_db_password(),
        )
    elif db_type == "mongodb":
        handler = DatabaseFactory.create_handler(
            db_type="mongodb",
            url=settings.get_mongodb_url(),
            database=settings.MONGODB_DB_NAME,
        )
    elif settings.is_sql_database():
        database_url = settings.get_database_url()
        if settings.DEBUG:
            log_event(
                logger,
                logging.DEBUG,
                "database.initialize.debug_sql_env",
                db_host=settings.DB_HOST,
                db_user=settings.DB_USER,
                db_name=settings.DB_NAME,
                db_port=settings.DB_PORT,
                db_password_file=settings.DB_PASSWORD_FILE,
                database_url_env=settings.DATABASE_URL,
            )

            masked_url = (
                re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", database_url)
                if database_url
                else "<EMPTY>"
            )
            log_event(
                logger,
                logging.DEBUG,
                "database.initialize.debug_sql_url",
                database_url=masked_url,
            )

        handler = DatabaseFactory.create_handler(
            db_type=db_type,
            database_url=database_url,
            echo=settings.is_sql_echo_enabled(),
        )
    else:
        raise ValueError(f"Unsupported DB_TYPE: {settings.DB_TYPE}")

    DatabaseFactory.set_instance(handler)

    max_retries = 8
    retry_delay = 1
    result = {"status": "error", "message": "Database initialization failed"}
    for attempt in range(1, max_retries + 1):
        result = await handler.test_connection()
        if result.get("status") == "success":
            result["attempt"] = attempt
            result["max_retries"] = max_retries
            result["db_type"] = db_type
            if attempt > 1:
                log_event(
                    logger,
                    logging.INFO,
                    "database.initialize.connection_ok_after_retry",
                    message=result.get("message"),
                    attempt=attempt,
                    max_retries=max_retries,
                )
            else:
                log_event(
                    logger,
                    logging.INFO,
                    "database.initialize.connection_ok",
                    message=result.get("message"),
                    attempt=attempt,
                )
            return result

        if attempt < max_retries:
            log_event(
                logger,
                logging.WARNING,
                "database.initialize.connection_retry",
                attempt=attempt,
                max_retries=max_retries,
                retry_delay_seconds=retry_delay,
                message=result.get("message"),
            )
            await asyncio.sleep(retry_delay)
            retry_delay *= 2
        else:
            result["attempt"] = attempt
            result["max_retries"] = max_retries
            result["db_type"] = db_type
            log_event(
                logger,
                logging.ERROR,
                "database.initialize.connection_failed",
                message=result.get("message"),
                attempt=attempt,
                max_retries=max_retries,
            )

    return result


async def close_database():
    """Close database connection."""
    log_event(logger, logging.INFO, "database.close.begin")
    DatabaseFactory.close_instance()
    log_event(logger, logging.INFO, "database.close.complete")
