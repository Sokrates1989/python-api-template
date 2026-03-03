import asyncio
import unittest
from pathlib import Path
from unittest import mock

from backend.ports.backup_capability import ProviderCapabilities
from backend.services import backup_service as facade_module


class BackupServiceFacadeTests(unittest.TestCase):
    def test_backup_service_facade_dispatches_sql(self):
        class DummyHandler:
            db_type = "sql"

        class DummyCapability:
            db_type = "sql"
            capabilities = ProviderCapabilities(
                supports_backup_download=True,
                supports_restore_upload=True,
                supports_restore_status=True,
                supports_stats=True,
            )

            def create_backup_to_temp(self, compress: bool = True):
                return "backup.sql", Path("backup.sql")

            def check_operation_lock(self):
                return None

            def get_restore_status(self):
                return {"status": "none"}

            def restore_backup(self, backup_file: Path):
                return {"success": True}

            async def get_database_stats(self):
                return {"table_count": 1}

        factory_mock = mock.Mock(return_value=DummyCapability())
        with mock.patch.object(
            facade_module,
            "get_database_handler",
            lambda: DummyHandler(),
        ), mock.patch.object(
            facade_module,
            "create_backup_capability",
            factory_mock,
        ):
            service = facade_module.BackupService()
            stats = asyncio.run(service.get_database_stats())

        factory_mock.assert_called_once_with("sql")
        self.assertEqual(service.db_type, "sql")
        self.assertTrue(service.capabilities.supports_backup_download)
        self.assertEqual(stats["table_count"], 1)

    def test_backup_service_facade_rejects_unsupported_database(self):
        class DummyHandler:
            db_type = "oracle"

        def raising_factory(_db_type: str):
            raise ValueError("Unsupported database type for backup capability: oracle")

        with mock.patch.object(
            facade_module,
            "get_database_handler",
            lambda: DummyHandler(),
        ), mock.patch.object(
            facade_module,
            "create_backup_capability",
            raising_factory,
        ):
            with self.assertRaisesRegex(ValueError, "Unsupported database type for backup capability"):
                facade_module.BackupService()
