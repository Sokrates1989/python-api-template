import asyncio

from backend.database.startup_probe import run_provider_startup_probe


class _AsyncListIndexes:
    def __init__(self, names):
        self._items = [{"name": name} for name in names]
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._items):
            raise StopAsyncIteration
        item = self._items[self._index]
        self._index += 1
        return item


class _FakeCollection:
    def __init__(self):
        self.indexes = {"_id_"}

    async def create_index(self, _field, unique=False, name=""):
        _ = unique
        self.indexes.add(name)
        return name

    def list_indexes(self):
        return _AsyncListIndexes(sorted(self.indexes))


class _FakeAdmin:
    async def command(self, cmd):
        assert cmd == "ping"
        return {"ok": 1}


class _FakeMongoClient:
    def __init__(self):
        self.admin = _FakeAdmin()


class _FakeMongoDatabase:
    def __init__(self):
        self._collections = {
            "users": _FakeCollection(),
            "examples": _FakeCollection(),
        }

    def __getitem__(self, name):
        return self._collections[name]


class _FakeMongoHandler:
    db_type = "mongodb"

    def __init__(self):
        self.client = _FakeMongoClient()
        self.database = _FakeMongoDatabase()


class _FakeSQLSession:
    async def execute(self, _query):
        return None


class _FakeSQLSessionContext:
    async def __aenter__(self):
        return _FakeSQLSession()

    async def __aexit__(self, exc_type, exc, tb):
        _ = (exc_type, exc, tb)
        return False


class _FakeSQLHandler:
    db_type = "postgresql"

    def __init__(self):
        self.engine = type("Engine", (), {"dialect": type("Dialect", (), {"name": "postgresql"})()})()
        self.Base = type("Base", (), {"metadata": type("Metadata", (), {"tables": {"a": 1, "b": 2}})()})()

    def AsyncSessionLocal(self):
        return _FakeSQLSessionContext()


def test_startup_probe_mongodb_ensures_required_indexes() -> None:
    result = asyncio.run(run_provider_startup_probe(_FakeMongoHandler()))

    assert result["status"] == "success"
    assert result["provider_profile"] == "mongodb"
    assert result["checks"]["missing_users_indexes"] == []
    assert result["checks"]["missing_examples_indexes"] == []


def test_startup_probe_sql_returns_dialect_and_model_count() -> None:
    result = asyncio.run(run_provider_startup_probe(_FakeSQLHandler()))

    assert result["status"] == "success"
    assert result["provider_profile"] == "sql"
    assert result["checks"]["dialect"] == "postgresql"
    assert result["checks"]["declared_sql_models"] == 2


def test_startup_probe_unsupported_provider_returns_error() -> None:
    handler = type("Handler", (), {"db_type": "unknown"})()
    result = asyncio.run(run_provider_startup_probe(handler))

    assert result["status"] == "error"
    assert result["provider_profile"] == "unknown"
    assert "Unsupported provider profile" in result["message"]
