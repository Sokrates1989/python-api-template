"""Tests provider information on the canonical shared database route."""

import asyncio
from unittest import mock

from api.shared_routes import database_lock


class _DummyHandler:
    """Expose only the provider type consumed by the shared route."""

    def __init__(self, db_type: str):
        """Initialize one provider stub.

        Args:
            db_type: Provider name returned to route capability resolution.
        """

        self.db_type = db_type


def test_provider_info_uses_active_handler_and_lock_state() -> None:
    """Prefer the active handler and include the current lock operation."""

    with (
        mock.patch.object(
            database_lock,
            "get_database_handler",
            return_value=_DummyHandler("mongo"),
        ),
        mock.patch.object(database_lock, "_check_lock", return_value="restore"),
    ):
        response = asyncio.run(database_lock.get_provider_info("admin-token"))

    assert response.database_type == "mongo"
    assert response.provider_profile == "mongodb"
    assert response.capabilities["supports_stats"] is True
    assert response.capabilities["supports_restore_upload"] is False
    assert response.is_locked is True
    assert response.lock_operation == "restore"


def test_provider_info_falls_back_to_settings_when_handler_unavailable() -> None:
    """Fall back to normalized settings before a handler is initialized."""

    with (
        mock.patch.object(
            database_lock,
            "get_database_handler",
            side_effect=RuntimeError("not ready"),
        ),
        mock.patch.object(
            type(database_lock.settings),
            "normalized_db_type",
            return_value="postgresql",
        ),
        mock.patch.object(database_lock, "_check_lock", return_value=None),
    ):
        response = asyncio.run(database_lock.get_provider_info("admin-token"))

    assert response.database_type == "postgresql"
    assert response.provider_profile == "sql"
    assert response.capabilities["supports_migrations"] is True
    assert response.is_locked is False
