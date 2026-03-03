"""Factory for backend provider capability profiles."""
from __future__ import annotations

from backend.database import get_database_handler
from backend.ports.provider_capabilities import ProviderCapabilities


_CAPABILITY_PROFILES: dict[str, ProviderCapabilities] = {
    "sql": ProviderCapabilities(
        supports_transactions=True,
        supports_migrations=True,
        supports_optimistic_locking=True,
        supports_sync_api=True,
        supports_user_repository=True,
        supports_example_repository=True,
        supports_backup_download=True,
        supports_restore_upload=True,
        supports_restore_status=True,
        supports_stats=True,
    ),
    "neo4j": ProviderCapabilities(
        supports_transactions=True,
        supports_migrations=False,
        supports_optimistic_locking=False,
        supports_sync_api=False,
        supports_user_repository=True,
        supports_example_repository=True,
        supports_backup_download=True,
        supports_restore_upload=True,
        supports_restore_status=True,
        supports_stats=True,
    ),
    "mongodb": ProviderCapabilities(
        supports_transactions=False,
        supports_migrations=False,
        supports_optimistic_locking=True,
        supports_sync_api=False,
        supports_user_repository=True,
        supports_example_repository=True,
        supports_backup_download=False,
        supports_restore_upload=False,
        supports_restore_status=False,
        supports_stats=True,
    ),
}


def normalize_provider_db_type(db_type: str) -> str:
    """Normalize DB type aliases to provider capability profile keys."""
    normalized = (db_type or "").strip().lower()
    if normalized in {"postgresql", "postgres", "mysql", "sqlite", "sql"}:
        return "sql"
    if normalized == "mongo":
        return "mongodb"
    return normalized


def get_provider_capabilities_for_db_type(db_type: str) -> ProviderCapabilities:
    """Return capability profile for a provided DB type."""
    normalized = normalize_provider_db_type(db_type)
    capabilities = _CAPABILITY_PROFILES.get(normalized)
    if capabilities is None:
        raise ValueError(
            f"Unsupported database type for capability profile: {db_type}. "
            "Supported: postgresql/postgres, neo4j, mongodb (legacy: mysql, sqlite)"
        )
    return capabilities


def get_current_provider_capabilities() -> ProviderCapabilities:
    """Resolve capability profile for the currently initialized handler."""
    handler = get_database_handler()
    db_type = getattr(handler, "db_type", "")
    return get_provider_capabilities_for_db_type(db_type)
