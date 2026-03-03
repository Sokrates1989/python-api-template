import asyncio
import unittest
from unittest import mock

from backend.adapters import backup_capability_factory as factory_module


class DummyCollection:
    def __init__(self, count: int):
        self._count = count

    async def count_documents(self, _filter):
        return self._count


class DummyDatabase:
    def __init__(self):
        self._collections = {
            "users": DummyCollection(3),
            "events": DummyCollection(7),
        }

    async def list_collection_names(self):
        return list(self._collections.keys())

    def __getitem__(self, name: str):
        return self._collections[name]


class DummyHandler:
    db_type = "mongodb"
    database = DummyDatabase()


class MongoDBBackupCapabilityAdapterTests(unittest.TestCase):
    def test_get_database_stats(self):
        adapter = factory_module.MongoDBBackupCapabilityAdapter()
        with mock.patch.object(factory_module, "get_database_handler", lambda: DummyHandler()):
            stats = asyncio.run(adapter.get_database_stats())

        self.assertEqual(stats["collection_count"], 2)
        self.assertEqual(stats["total_documents"], 10)

    def test_unsupported_backup_operations_raise(self):
        adapter = factory_module.MongoDBBackupCapabilityAdapter()
        with self.assertRaisesRegex(NotImplementedError, "Backup download is not supported"):
            adapter.create_backup_to_temp()
        with self.assertRaisesRegex(NotImplementedError, "Restore upload is not supported"):
            adapter.restore_backup(None)  # type: ignore[arg-type]
