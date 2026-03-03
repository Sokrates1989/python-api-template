"""Database-agnostic backup capability facade."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from backend.adapters.backup_capability_factory import create_backup_capability
from backend.database import get_database_handler
from backend.ports.backup_capability import BackupCapability, ProviderCapabilities


class BackupService:
    """Dispatch backup/stat operations to provider capability adapters."""

    def __init__(self):
        handler = get_database_handler()
        db_type = getattr(handler, "db_type", "").strip().lower()
        self._capability: BackupCapability = create_backup_capability(db_type)
        self._db_type = db_type

    @property
    def db_type(self) -> str:
        return self._db_type

    @property
    def capabilities(self) -> ProviderCapabilities:
        return self._capability.capabilities

    def create_backup_to_temp(self, compress: bool = True) -> tuple[str, Path]:
        return self._capability.create_backup_to_temp(compress=compress)

    def check_operation_lock(self) -> Optional[str]:
        return self._capability.check_operation_lock()

    def get_restore_status(self) -> Optional[Dict[str, Any]]:
        return self._capability.get_restore_status()

    def restore_backup(self, backup_file: Path) -> Any:
        return self._capability.restore_backup(backup_file)

    async def get_database_stats(self) -> Dict[str, Any]:
        return await self._capability.get_database_stats()
