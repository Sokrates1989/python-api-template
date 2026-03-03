import unittest
from unittest import mock

from backend.adapters import user_repository_factory as factory_module


class DummyRepository:
    async def create_user(self, *args, **kwargs):  # pragma: no cover - not used in these tests
        return {}

    async def get_user(self, *args, **kwargs):  # pragma: no cover - not used in these tests
        return {}

    async def update_user(self, *args, **kwargs):  # pragma: no cover - not used in these tests
        return {}

    async def update_username(self, *args, **kwargs):  # pragma: no cover - not used in these tests
        return {}


class UserRepositoryFactoryTests(unittest.TestCase):
    def test_normalize_repository_db_type(self):
        self.assertEqual(factory_module.normalize_repository_db_type("postgresql"), "sql")
        self.assertEqual(factory_module.normalize_repository_db_type("POSTGRES"), "sql")
        self.assertEqual(factory_module.normalize_repository_db_type("mysql"), "sql")
        self.assertEqual(factory_module.normalize_repository_db_type("sqlite"), "sql")
        self.assertEqual(factory_module.normalize_repository_db_type("mongo"), "mongodb")
        self.assertEqual(factory_module.normalize_repository_db_type("neo4j"), "neo4j")

    def test_create_user_repository_uses_normalized_alias(self):
        with mock.patch.dict(
            factory_module.USER_REPOSITORY_ADAPTERS,
            {"sql": DummyRepository},
            clear=False,
        ):
            repository = factory_module.create_user_repository("postgresql")

        self.assertIsInstance(repository, DummyRepository)

    def test_create_user_repository_rejects_unsupported_backend(self):
        with self.assertRaisesRegex(ValueError, "Unsupported database type for user repository"):
            factory_module.create_user_repository("oracle")
