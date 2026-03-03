import unittest

from backend.adapters import provider_capability_factory as factory_module


class ProviderCapabilityFactoryTests(unittest.TestCase):
    def test_normalize_provider_db_type(self):
        self.assertEqual(factory_module.normalize_provider_db_type("postgresql"), "sql")
        self.assertEqual(factory_module.normalize_provider_db_type("POSTGRES"), "sql")
        self.assertEqual(factory_module.normalize_provider_db_type("mysql"), "sql")
        self.assertEqual(factory_module.normalize_provider_db_type("sqlite"), "sql")
        self.assertEqual(factory_module.normalize_provider_db_type("mongo"), "mongodb")
        self.assertEqual(factory_module.normalize_provider_db_type("neo4j"), "neo4j")

    def test_sql_profile_capabilities(self):
        caps = factory_module.get_provider_capabilities_for_db_type("postgresql")
        self.assertTrue(caps.supports_transactions)
        self.assertTrue(caps.supports_migrations)
        self.assertTrue(caps.supports_optimistic_locking)
        self.assertTrue(caps.supports_sync_api)
        self.assertTrue(caps.supports_example_repository)
        self.assertTrue(caps.supports_backup_download)
        self.assertTrue(caps.supports_restore_upload)

    def test_neo4j_profile_capabilities(self):
        caps = factory_module.get_provider_capabilities_for_db_type("neo4j")
        self.assertTrue(caps.supports_transactions)
        self.assertFalse(caps.supports_migrations)
        self.assertFalse(caps.supports_optimistic_locking)
        self.assertFalse(caps.supports_sync_api)
        self.assertTrue(caps.supports_example_repository)
        self.assertTrue(caps.supports_backup_download)

    def test_mongodb_profile_capabilities(self):
        caps = factory_module.get_provider_capabilities_for_db_type("mongodb")
        self.assertFalse(caps.supports_transactions)
        self.assertFalse(caps.supports_migrations)
        self.assertTrue(caps.supports_optimistic_locking)
        self.assertFalse(caps.supports_sync_api)
        self.assertTrue(caps.supports_example_repository)
        self.assertFalse(caps.supports_backup_download)
        self.assertFalse(caps.supports_restore_upload)

    def test_reject_unsupported_backend(self):
        with self.assertRaisesRegex(ValueError, "Unsupported database type for capability profile"):
            factory_module.get_provider_capabilities_for_db_type("oracle")
