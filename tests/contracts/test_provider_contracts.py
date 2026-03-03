import unittest
import uuid

from api.settings import settings
from backend.adapters.example_repository_factory import supports_example_repository
from backend.database import close_database, initialize_database
from backend.services.backup_service import BackupService
from backend.services.example_service import ExampleService
from backend.services.user_service import UserService


class ProviderContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        result = await initialize_database()
        self.assertEqual(result.get("status"), "success")

    async def asyncTearDown(self):
        await close_database()

    async def test_user_service_contract(self):
        service = UserService()
        user_id = f"contract-{uuid.uuid4()}"
        username = f"user_{uuid.uuid4().hex[:8]}"
        email = f"{user_id}@example.com"

        created = await service.create_user(
            user_id=user_id,
            email=email,
            username=username,
            first_name="Contract",
            last_name="Test",
        )
        self.assertEqual(created.get("status"), "success")

        fetched = await service.get_user(user_id)
        self.assertEqual(fetched.get("status"), "success")
        self.assertEqual(fetched["data"]["id"], user_id)

        updated = await service.update_user(user_id=user_id, first_name="Updated")
        self.assertEqual(updated.get("status"), "success")

        renamed = await service.update_username(
            user_id=user_id,
            username=f"user_{uuid.uuid4().hex[:8]}",
        )
        self.assertEqual(renamed.get("status"), "success")

    async def test_example_service_contract_for_supported_backends(self):
        db_type = settings.normalized_db_type()
        if not supports_example_repository(db_type):
            self.skipTest(f"Example contract not supported for DB_TYPE={db_type}")

        service = ExampleService()
        name = f"contract-{uuid.uuid4().hex[:10]}"
        description = "provider-contract"

        created = await service.create_example(name=name, description=description)
        self.assertEqual(created.get("status"), "success")
        self.assertIn("data", created)

        example_id = created["data"]["id"]
        fetched = await service.get_example(example_id)
        self.assertEqual(fetched.get("status"), "success")
        self.assertEqual(fetched["data"]["id"], example_id)

        listed = await service.list_examples(
            limit=200,
            offset=0,
            name=name if db_type == "neo4j" else None,
        )
        self.assertEqual(listed.get("status"), "success")
        records = listed.get("data", [])
        self.assertTrue(any(item.get("id") == example_id for item in records))

        updated = await service.update_example(
            example_id=example_id,
            description="provider-contract-updated",
        )
        self.assertEqual(updated.get("status"), "success")

        deleted = await service.delete_example(example_id)
        self.assertEqual(deleted.get("status"), "success")

    async def test_backup_capability_contract(self):
        service = BackupService()
        stats = await service.get_database_stats()
        self.assertIsInstance(stats, dict)

        db_type = settings.normalized_db_type()
        if db_type == "mongodb":
            self.assertFalse(service.capabilities.supports_backup_download)
            with self.assertRaises(NotImplementedError):
                service.create_backup_to_temp(compress=True)
        else:
            self.assertTrue(service.capabilities.supports_backup_download)
