import unittest
from pathlib import Path
from unittest import mock

from backend.adapters import backup_capability_factory as factory_module
from backend.ports.backup_capability import ProviderCapabilities


class DummyCapability:
    db_type = "dummy"
    capabilities = ProviderCapabilities()

    def create_backup_to_temp(self, compress: bool = True):  # pragma: no cover
        return "backup.sql", Path("backup.sql")

    def check_operation_lock(self):  # pragma: no cover
        return None

    def get_restore_status(self):  # pragma: no cover
        return None

    def restore_backup(self, backup_file: Path):  # pragma: no cover
        return {"ok": True}

    async def get_database_stats(self):  # pragma: no cover
        return {}


class BackupCapabilityFactoryTests(unittest.TestCase):
    def test_normalize_capability_db_type(self):
        self.assertEqual(factory_module.normalize_capability_db_type("postgresql"), "sql")
        self.assertEqual(factory_module.normalize_capability_db_type("POSTGRES"), "sql")
        self.assertEqual(factory_module.normalize_capability_db_type("mysql"), "sql")
        self.assertEqual(factory_module.normalize_capability_db_type("sqlite"), "sql")
        self.assertEqual(factory_module.normalize_capability_db_type("mongo"), "mongodb")
        self.assertEqual(factory_module.normalize_capability_db_type("neo4j"), "neo4j")

    def test_create_backup_capability_uses_normalized_alias(self):
        with mock.patch.dict(
            factory_module.BACKUP_CAPABILITY_ADAPTERS,
            {"sql": DummyCapability},
            clear=False,
        ):
            capability = factory_module.create_backup_capability("postgresql")
        self.assertIsInstance(capability, DummyCapability)

    def test_create_backup_capability_rejects_unsupported_backend(self):
        with self.assertRaisesRegex(ValueError, "Unsupported database type for backup capability"):
            factory_module.create_backup_capability("oracle")
