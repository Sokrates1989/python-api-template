"""Regression tests for resilient SQLAlchemy engine construction.

The API keeps pooled SQL connections between requests. Both synchronous and
asynchronous engines must validate a pooled connection before checkout so an
ordinary database restart does not leave generated applications returning 500.
"""

from unittest import TestCase, mock

from backend.database import sql_handler as sql_handler_module


class SQLHandlerEngineOptionsTests(TestCase):
    """Verify restart-safe options on the shared SQL handler engines."""

    @mock.patch.object(sql_handler_module, "sessionmaker")
    @mock.patch.object(sql_handler_module, "create_async_engine")
    @mock.patch.object(sql_handler_module, "create_engine")
    def test_engines_pre_ping_pooled_connections(
        self,
        create_engine: mock.Mock,
        create_async_engine: mock.Mock,
        sessionmaker: mock.Mock,
    ) -> None:
        """Enable pre-ping for migration and request engines.

        Args:
            create_engine: Patched synchronous SQLAlchemy engine factory.
            create_async_engine: Patched asynchronous engine factory.
            sessionmaker: Patched session factory constructor.

        Returns:
            None after asserting both engine factory calls.
        """

        database_url = "postgresql://user:password@database:5432/application"

        sql_handler_module.SQLHandler(database_url)

        create_engine.assert_called_once_with(
            database_url,
            echo=False,
            pool_pre_ping=True,
        )
        create_async_engine.assert_called_once_with(
            "postgresql+asyncpg://user:password@database:5432/application",
            echo=False,
            pool_pre_ping=True,
        )
        self.assertEqual(sessionmaker.call_count, 2)
