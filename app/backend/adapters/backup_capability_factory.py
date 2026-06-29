"""Provider adapters and factory for backup/restore capabilities."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from backend.database import get_database_handler
from backend.database.mongodb_handler import MongoDBHandler
from backend.ports.backup_capability import BackupCapability
from .provider_capability_factory import (
    get_provider_capabilities_for_db_type,
    normalize_provider_db_type,
)


class SQLBackupCapabilityAdapter:
    """Backup capability adapter for SQL backends."""

    db_type = "sql"
    capabilities = get_provider_capabilities_for_db_type("sql")

    def __init__(self) -> None:
        from backend.services.sql.backup_service import BackupService as SQLBackupService

        self._service = SQLBackupService()

    def create_backup_to_temp(self, compress: bool = True) -> tuple[str, Path]:
        return self._service.create_backup_to_temp(compress=compress)

    def check_operation_lock(self) -> Optional[str]:
        return self._service.check_operation_lock()

    def get_restore_status(self) -> Optional[Dict[str, Any]]:
        return self._service.get_restore_status()

    def restore_backup(self, backup_file: Path) -> Any:
        return self._service.restore_backup(backup_file)

    async def get_database_stats(self) -> Dict[str, Any]:
        return await asyncio.to_thread(self._service.get_database_stats)


class Neo4jBackupCapabilityAdapter:
    """Backup capability adapter for Neo4j backend."""

    db_type = "neo4j"
    capabilities = get_provider_capabilities_for_db_type("neo4j")

    def __init__(self) -> None:
        from backend.services.neo4j.backup_service import Neo4jBackupService

        self._service = Neo4jBackupService()

    def create_backup_to_temp(self, compress: bool = True) -> tuple[str, Path]:
        return self._service.create_backup_to_temp(compress=compress)

    def check_operation_lock(self) -> Optional[str]:
        return self._service.check_operation_lock()

    def get_restore_status(self) -> Optional[Dict[str, Any]]:
        return self._service.get_restore_status()

    def restore_backup(self, backup_file: Path) -> Any:
        return self._service.restore_backup(backup_file)

    async def get_database_stats(self) -> Dict[str, Any]:
        return await asyncio.to_thread(self._service.get_database_stats)


class MongoDBBackupCapabilityAdapter:
    """Capability adapter for MongoDB stats (no backup/restore yet)."""

    db_type = "mongodb"
    capabilities = get_provider_capabilities_for_db_type("mongodb")

    def create_backup_to_temp(self, compress: bool = True) -> tuple[str, Path]:
        raise NotImplementedError("Backup download is not supported for mongodb")

    def check_operation_lock(self) -> Optional[str]:
        return None

    def get_restore_status(self) -> Optional[Dict[str, Any]]:
        return None

    def restore_backup(self, backup_file: Path) -> Any:
        raise NotImplementedError("Restore upload is not supported for mongodb")

    async def get_database_stats(self) -> Dict[str, Any]:
        handler = get_database_handler()
        if not isinstance(handler, MongoDBHandler):
            raise ValueError("MongoDB stats requested but current handler is not MongoDB")

        collection_names = await handler.database.list_collection_names()
        collections = []
        total_documents = 0

        for name in sorted(collection_names):
            count = await handler.database[name].count_documents({})
            total_documents += count
            collections.append({"name": name, "document_count": count})

        return {
            "collection_count": len(collections),
            "total_documents": total_documents,
            "collections": collections,
        }


BACKUP_CAPABILITY_ADAPTERS: Dict[str, Callable[[], BackupCapability]] = {
    "sql": SQLBackupCapabilityAdapter,
    "postgresql": SQLBackupCapabilityAdapter,
    "postgres": SQLBackupCapabilityAdapter,
    "mysql": SQLBackupCapabilityAdapter,
    "sqlite": SQLBackupCapabilityAdapter,
    "neo4j": Neo4jBackupCapabilityAdapter,
    "mongodb": MongoDBBackupCapabilityAdapter,
    "mongo": MongoDBBackupCapabilityAdapter,
}


def normalize_capability_db_type(db_type: str) -> str:
    """Normalize DB type names for capability adapter lookup."""
    return normalize_provider_db_type(db_type)


def create_backup_capability(db_type: str) -> BackupCapability:
    """Create backup capability adapter for the provided backend type."""
    normalized = normalize_capability_db_type(db_type)
    adapter_cls = BACKUP_CAPABILITY_ADAPTERS.get(normalized)
    if adapter_cls is None:
        raise ValueError(
            f"Unsupported database type for backup capability: {db_type}. "
            "Supported: postgresql/postgres, neo4j, mongodb (legacy: mysql, sqlite)"
        )
    return adapter_cls()
