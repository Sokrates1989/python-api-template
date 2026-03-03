from unittest import mock

import pytest

from backend.database import factory


def test_factory_creates_mongodb_handler() -> None:
    captured: dict[str, str] = {}

    class DummyMongoHandler:
        def __init__(self, url: str, database: str):
            captured["url"] = url
            captured["database"] = database
            self.db_type = "mongodb"

    with mock.patch.object(factory, "MongoDBHandler", DummyMongoHandler):
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
    captured: dict[str, object] = {}

    class DummySQLHandler:
        def __init__(self, database_url: str, echo: bool):
            captured["database_url"] = database_url
            captured["echo"] = echo
            self.db_type = "sql"

    with mock.patch.object(factory, "SQLHandler", DummySQLHandler):
        handler = factory.DatabaseFactory.create_handler(
            "postgres",
            database_url="postgresql://user:pass@localhost:5432/apidb",
            echo=True,
        )

    assert isinstance(handler, DummySQLHandler)
    assert str(captured["database_url"]).startswith("postgresql://")
    assert captured["echo"] is True


def test_factory_rejects_unknown_database_type() -> None:
    with pytest.raises(ValueError, match="Unsupported database type"):
        factory.DatabaseFactory.create_handler("oracle")
