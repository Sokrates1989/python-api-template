"""Tests lazy database-handler selection without requiring every provider."""

import sys
import types
from unittest import mock

import pytest

from backend.database import factory


def test_factory_creates_mongodb_handler() -> None:
    """Create MongoDB through its lazily imported provider module."""

    captured: dict[str, str] = {}

    class DummyMongoHandler:
        """Capture MongoDB constructor arguments for the factory assertion."""

        def __init__(self, url: str, database: str):
            """Record the URL and database passed by the factory.

            Args:
                url: MongoDB connection URL.
                database: Selected MongoDB database name.
            """

            captured["url"] = url
            captured["database"] = database
            self.db_type = "mongodb"

    provider = types.ModuleType("backend.database.mongodb_handler")
    provider.MongoDBHandler = DummyMongoHandler
    with mock.patch.dict(sys.modules, {provider.__name__: provider}):
        handler = factory.DatabaseFactory.create_handler(
            "mongodb",
            url="mongodb://mongo:secret@mongodb:27017",
            database="apidb",
        )

    assert isinstance(handler, DummyMongoHandler)
    assert captured == {
        "url": "mongodb://mongo:secret@mongodb:27017",
        "database": "apidb",
    }


def test_factory_accepts_postgres_alias() -> None:
    """Map the PostgreSQL alias through the lazily imported SQL handler."""

    captured: dict[str, object] = {}

    class DummySQLHandler:
        """Capture SQL constructor arguments for the factory assertion."""

        def __init__(self, database_url: str, echo: bool):
            """Record the URL and logging flag passed by the factory.

            Args:
                database_url: SQLAlchemy connection URL.
                echo: Whether SQLAlchemy statement logging is enabled.
            """

            captured["database_url"] = database_url
            captured["echo"] = echo
            self.db_type = "sql"

    provider = types.ModuleType("backend.database.sql_handler")
    provider.SQLHandler = DummySQLHandler
    with mock.patch.dict(sys.modules, {provider.__name__: provider}):
        handler = factory.DatabaseFactory.create_handler(
            "postgres",
            database_url="postgresql://user:pass@localhost:5432/apidb",
            echo=True,
        )

    assert isinstance(handler, DummySQLHandler)
    assert str(captured["database_url"]).startswith("postgresql://")
    assert captured["echo"] is True


def test_factory_rejects_unknown_database_type() -> None:
    """Reject provider names outside the supported factory contract."""

    with pytest.raises(ValueError, match="Unsupported database type"):
        factory.DatabaseFactory.create_handler("oracle")
