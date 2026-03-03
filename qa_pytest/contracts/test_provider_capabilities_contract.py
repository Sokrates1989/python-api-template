import asyncio
from dataclasses import asdict

import pytest
from fastapi import HTTPException, status

from api.routes.sql.sync import ensure_sync_supported
from api.settings import settings
from backend.adapters.provider_capability_factory import (
    get_current_provider_capabilities,
    get_provider_capabilities_for_db_type,
    normalize_provider_db_type,
)
from backend.database import close_database, initialize_database


EXPECTED_CAPABILITIES_BY_PROFILE = {
    "sql": {
        "supports_transactions": True,
        "supports_migrations": True,
        "supports_optimistic_locking": True,
        "supports_sync_api": True,
        "supports_user_repository": True,
        "supports_example_repository": True,
        "supports_backup_download": True,
        "supports_restore_upload": True,
        "supports_restore_status": True,
        "supports_stats": True,
    },
    "neo4j": {
        "supports_transactions": True,
        "supports_migrations": False,
        "supports_optimistic_locking": False,
        "supports_sync_api": False,
        "supports_user_repository": True,
        "supports_example_repository": True,
        "supports_backup_download": True,
        "supports_restore_upload": True,
        "supports_restore_status": True,
        "supports_stats": True,
    },
    "mongodb": {
        "supports_transactions": False,
        "supports_migrations": False,
        "supports_optimistic_locking": True,
        "supports_sync_api": False,
        "supports_user_repository": True,
        "supports_example_repository": True,
        "supports_backup_download": False,
        "supports_restore_upload": False,
        "supports_restore_status": False,
        "supports_stats": True,
    },
}


async def _run_with_initialized_database(test_coro):
    try:
        result = await initialize_database()
        assert result.get("status") == "success"
        await test_coro()
    finally:
        await close_database()


@pytest.mark.contract
def test_capability_profile_matches_current_database():
    async def _scenario():
        configured_db_type = settings.normalized_db_type()
        profile_key = normalize_provider_db_type(configured_db_type)
        expected = EXPECTED_CAPABILITIES_BY_PROFILE[profile_key]

        current_capabilities = get_current_provider_capabilities()
        resolved_capabilities = get_provider_capabilities_for_db_type(configured_db_type)

        assert asdict(current_capabilities) == expected
        assert asdict(resolved_capabilities) == expected

    asyncio.run(_run_with_initialized_database(_scenario))


@pytest.mark.contract
def test_sync_route_guard_matches_capabilities():
    async def _scenario():
        capabilities = get_current_provider_capabilities()
        if capabilities.supports_sync_api:
            ensure_sync_supported()
            return

        with pytest.raises(HTTPException) as exc_info:
            ensure_sync_supported()
        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST

    asyncio.run(_run_with_initialized_database(_scenario))
