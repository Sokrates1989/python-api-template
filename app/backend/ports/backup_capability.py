"""Backup/restore capability contracts."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Protocol, runtime_checkable

from .provider_capabilities import ProviderCapabilities


@runtime_checkable
class BackupCapability(Protocol):
    """Contract for backup/restore/statistics provider adapters."""

    db_type: str
    capabilities: ProviderCapabilities

    def create_backup_to_temp(self, compress: bool = True) -> tuple[str, Path]:
        ...

    def check_operation_lock(self) -> Optional[str]:
        ...

    def get_restore_status(self) -> Optional[Dict[str, Any]]:
        ...

    def restore_backup(self, backup_file: Path) -> Any:
        ...

    async def get_database_stats(self) -> Dict[str, Any]:
        ...
