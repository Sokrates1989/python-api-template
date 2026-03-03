import asyncio
import unittest
from unittest import mock

from backend.services import example_service as facade_module


class ExampleServiceFacadeTests(unittest.TestCase):
    def test_example_service_facade_dispatches_sql(self):
        class DummyHandler:
            db_type = "sql"

        class DummyRepository:
            async def get_example(self, example_id: str):
                return {"status": "success", "data": {"id": example_id}}

            async def create_example(self, **kwargs):
                return {"status": "success", "data": kwargs}

            async def list_examples(self, **kwargs):
                return {"status": "success", "data": [], "pagination": kwargs}

            async def update_example(self, **kwargs):
                return {"status": "success", "data": kwargs}

            async def delete_example(self, **kwargs):
                return {"status": "success", "message": "ok"}

            async def delete_all_examples(self):
                return {"status": "error", "message": "unsupported"}

        factory_mock = mock.Mock(return_value=DummyRepository())
        with mock.patch.object(
            facade_module,
            "get_database_handler",
            lambda: DummyHandler(),
        ), mock.patch.object(
            facade_module,
            "create_example_repository",
            factory_mock,
        ):
            facade = facade_module.ExampleService()
            result = asyncio.run(facade.get_example("example-1"))

        factory_mock.assert_called_once_with("sql")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"]["id"], "example-1")

    def test_example_service_facade_dispatches_neo4j(self):
        class DummyHandler:
            db_type = "neo4j"

        class DummyRepository:
            async def get_example(self, example_id: str):
                return {"status": "success", "data": {"id": example_id}}

            async def create_example(self, **kwargs):
                return {"status": "success", "data": kwargs}

            async def list_examples(self, **kwargs):
                return {"status": "success", "data": [], "pagination": kwargs}

            async def update_example(self, **kwargs):
                return {"status": "success", "data": kwargs}

            async def delete_example(self, **kwargs):
                return {"status": "success", "message": "ok"}

            async def delete_all_examples(self):
                return {"status": "success", "deleted_count": 0}

        factory_mock = mock.Mock(return_value=DummyRepository())
        with mock.patch.object(
            facade_module,
            "get_database_handler",
            lambda: DummyHandler(),
        ), mock.patch.object(
            facade_module,
            "create_example_repository",
            factory_mock,
        ):
            facade = facade_module.ExampleService()
            result = asyncio.run(facade.get_example("node-1"))

        factory_mock.assert_called_once_with("neo4j")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"]["id"], "node-1")

    def test_example_service_facade_dispatches_mongodb(self):
        class DummyHandler:
            db_type = "mongodb"

        class DummyRepository:
            async def get_example(self, example_id: str):
                return {"status": "success", "data": {"id": example_id}}

            async def create_example(self, **kwargs):
                return {"status": "success", "data": kwargs}

            async def list_examples(self, **kwargs):
                return {"status": "success", "data": [], "pagination": kwargs}

            async def update_example(self, **kwargs):
                return {"status": "success", "data": kwargs}

            async def delete_example(self, **kwargs):
                return {"status": "success", "message": "ok"}

            async def delete_all_examples(self):
                return {"status": "success", "deleted_count": 0}

        factory_mock = mock.Mock(return_value=DummyRepository())
        with mock.patch.object(
            facade_module,
            "get_database_handler",
            lambda: DummyHandler(),
        ), mock.patch.object(
            facade_module,
            "create_example_repository",
            factory_mock,
        ):
            facade = facade_module.ExampleService()
            result = asyncio.run(facade.get_example("doc-1"))

        factory_mock.assert_called_once_with("mongodb")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"]["id"], "doc-1")

    def test_example_service_facade_rejects_unsupported_database(self):
        class DummyHandler:
            db_type = "oracle"

        def raising_factory(_db_type: str):
            raise ValueError("Unsupported database type for example repository: oracle")

        with mock.patch.object(
            facade_module,
            "get_database_handler",
            lambda: DummyHandler(),
        ), mock.patch.object(
            facade_module,
            "create_example_repository",
            raising_factory,
        ):
            with self.assertRaisesRegex(ValueError, "Unsupported database type for example repository"):
                facade_module.ExampleService()
