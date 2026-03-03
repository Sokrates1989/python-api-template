import asyncio
import unittest
from unittest import mock

from backend.services import user_service as facade_module


class UserServiceFacadeTests(unittest.TestCase):
    def test_user_service_facade_dispatches_sql(self):
        class DummyHandler:
            db_type = "sql"

        class DummyRepository:
            async def get_user(self, user_id: str):
                return {"status": "success", "message": "ok", "data": {"id": user_id}}

            async def create_user(self, **kwargs):
                return {"status": "success", "message": "ok", "data": kwargs}

            async def update_user(self, **kwargs):
                return {"status": "success", "message": "ok", "data": kwargs}

            async def update_username(self, **kwargs):
                return {"status": "success", "message": "ok", "data": kwargs}

        factory_mock = mock.Mock(return_value=DummyRepository())
        with mock.patch.object(
            facade_module,
            "get_database_handler",
            lambda: DummyHandler(),
        ), mock.patch.object(
            facade_module,
            "create_user_repository",
            factory_mock,
        ):
            facade = facade_module.UserService()
            result = asyncio.run(facade.get_user("user-1"))

        factory_mock.assert_called_once_with("sql")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"]["id"], "user-1")

    def test_user_service_facade_dispatches_mongodb(self):
        class DummyHandler:
            db_type = "mongodb"

        class DummyRepository:
            async def get_user(self, user_id: str):
                return {"status": "success", "message": "ok", "data": {"id": user_id}}

            async def create_user(self, **kwargs):
                return {"status": "success", "message": "ok", "data": kwargs}

            async def update_user(self, **kwargs):
                return {"status": "success", "message": "ok", "data": kwargs}

            async def update_username(self, **kwargs):
                return {"status": "success", "message": "ok", "data": kwargs}

        factory_mock = mock.Mock(return_value=DummyRepository())
        with mock.patch.object(
            facade_module,
            "get_database_handler",
            lambda: DummyHandler(),
        ), mock.patch.object(
            facade_module,
            "create_user_repository",
            factory_mock,
        ):
            facade = facade_module.UserService()
            result = asyncio.run(facade.get_user("mongo-user"))

        factory_mock.assert_called_once_with("mongodb")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"]["id"], "mongo-user")

    def test_user_service_facade_rejects_unsupported_database(self):
        class DummyHandler:
            db_type = "oracle"

        def raising_factory(_db_type: str):
            raise ValueError("Unsupported database type for user repository: oracle")

        with mock.patch.object(
            facade_module,
            "get_database_handler",
            lambda: DummyHandler(),
        ), mock.patch.object(
            facade_module,
            "create_user_repository",
            raising_factory,
        ):
            with self.assertRaisesRegex(ValueError, "Unsupported database type for user repository"):
                facade_module.UserService()
