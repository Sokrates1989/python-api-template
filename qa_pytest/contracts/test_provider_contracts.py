import asyncio
import uuid

import pytest

from api.settings import settings
from backend.adapters.example_repository_factory import supports_example_repository
from backend.database import close_database, initialize_database
from backend.services.backup_service import BackupService
from backend.services.example_service import ExampleService
from backend.services.user_service import UserService


async def _run_with_initialized_database(test_coro):
    try:
        result = await initialize_database()
        assert result.get("status") == "success"
        await test_coro()
    finally:
        await close_database()


@pytest.mark.contract
def test_user_service_contract_pytest():
    async def _scenario():
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
        assert created.get("status") == "success", created

        fetched = await service.get_user(user_id)
        assert fetched.get("status") == "success"
        assert fetched["data"]["id"] == user_id

        updated = await service.update_user(user_id=user_id, first_name="Updated")
        assert updated.get("status") == "success", updated

        renamed = await service.update_username(
            user_id=user_id,
            username=f"user_{uuid.uuid4().hex[:8]}",
        )
        assert renamed.get("status") == "success", renamed

    asyncio.run(_run_with_initialized_database(_scenario))


@pytest.mark.contract
def test_example_service_contract_pytest():
    async def _scenario():
        db_type = settings.normalized_db_type()
        if not supports_example_repository(db_type):
            pytest.skip(f"Examples not supported for DB_TYPE={db_type}")

        service = ExampleService()
        name = f"contract-{uuid.uuid4().hex[:10]}"
        description = "provider-contract"

        created = await service.create_example(name=name, description=description)
        assert created.get("status") == "success", created

        example_id = created["data"]["id"]
        fetched = await service.get_example(example_id)
        assert fetched.get("status") == "success"
        assert fetched["data"]["id"] == example_id

        listed = await service.list_examples(
            limit=200,
            offset=0,
            name=name if db_type == "neo4j" else None,
        )
        assert listed.get("status") == "success", listed
        records = listed.get("data", [])
        assert any(item.get("id") == example_id for item in records)

        updated = await service.update_example(
            example_id=example_id,
            description="provider-contract-updated",
        )
        assert updated.get("status") == "success", updated

        deleted = await service.delete_example(example_id)
        assert deleted.get("status") == "success"

    asyncio.run(_run_with_initialized_database(_scenario))


@pytest.mark.contract
def test_backup_capability_contract_pytest():
    async def _scenario():
        service = BackupService()
        stats = await service.get_database_stats()
        assert isinstance(stats, dict)

        db_type = settings.normalized_db_type()
        if db_type == "mongodb":
            assert service.capabilities.supports_backup_download is False
            with pytest.raises(NotImplementedError):
                service.create_backup_to_temp(compress=True)
        else:
            assert service.capabilities.supports_backup_download is True

    asyncio.run(_run_with_initialized_database(_scenario))
