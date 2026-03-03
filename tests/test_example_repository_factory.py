import unittest
from unittest import mock

from backend.adapters import example_repository_factory as factory_module


class DummyRepository:
    async def create_example(self, *args, **kwargs):  # pragma: no cover - not used
        return {}

    async def get_example(self, *args, **kwargs):  # pragma: no cover - not used
        return {}

    async def list_examples(self, *args, **kwargs):  # pragma: no cover - not used
        return {}

    async def update_example(self, *args, **kwargs):  # pragma: no cover - not used
        return {}

    async def delete_example(self, *args, **kwargs):  # pragma: no cover - not used
        return {}

    async def delete_all_examples(self, *args, **kwargs):  # pragma: no cover - not used
        return {}


class ExampleRepositoryFactoryTests(unittest.TestCase):
    def test_normalize_repository_db_type(self):
        self.assertEqual(factory_module.normalize_repository_db_type("postgresql"), "sql")
        self.assertEqual(factory_module.normalize_repository_db_type("POSTGRES"), "sql")
        self.assertEqual(factory_module.normalize_repository_db_type("mysql"), "sql")
        self.assertEqual(factory_module.normalize_repository_db_type("sqlite"), "sql")
        self.assertEqual(factory_module.normalize_repository_db_type("mongo"), "mongodb")
        self.assertEqual(factory_module.normalize_repository_db_type("neo4j"), "neo4j")

    def test_create_example_repository_uses_normalized_alias(self):
        with mock.patch.dict(
            factory_module.EXAMPLE_REPOSITORY_ADAPTERS,
            {"sql": DummyRepository},
            clear=False,
        ):
            repository = factory_module.create_example_repository("postgresql")

        self.assertIsInstance(repository, DummyRepository)

    def test_create_example_repository_rejects_unsupported_backend(self):
        with self.assertRaisesRegex(ValueError, "Unsupported database type for example repository"):
            factory_module.create_example_repository("oracle")

    def test_supports_example_repository(self):
        self.assertTrue(factory_module.supports_example_repository("postgresql"))
        self.assertTrue(factory_module.supports_example_repository("neo4j"))
        self.assertTrue(factory_module.supports_example_repository("mongodb"))
