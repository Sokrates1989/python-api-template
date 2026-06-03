"""Shared database-agnostic backup capability facade."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from backend.adapters.backup_capability_factory import create_backup_capability
from backend.database import get_database_handler
from backend.ports.backup_capability import BackupCapability, ProviderCapabilities


class BackupService:
    """Dispatch backup and stats operations to provider capability adapters."""

    def __init__(self) -> None:
        """
        Bind the service to the active provider-specific backup capability.

        Args:
            None.

        Returns:
            None.

        Side Effects:
            Resolves the active database handler and backup capability adapter.
        """
        handler = get_database_handler()
        db_type = getattr(handler, "db_type", "").strip().lower()
        self._capability: BackupCapability = create_backup_capability(db_type)
        self._db_type = db_type

    @property
    def db_type(self) -> str:
        """
        Return the active backend type.

        Args:
            None.

        Returns:
            str: Active provider identifier.

        Side Effects:
            None.
        """
        return self._db_type

    @property
    def capabilities(self) -> ProviderCapabilities:
        """
        Return provider backup capability metadata.

        Args:
            None.

        Returns:
            ProviderCapabilities: Active provider capability flags.

        Side Effects:
            None.
        """
        return self._capability.capabilities

    def create_backup_to_temp(self, compress: bool = True) -> tuple[str, Path]:
        """
        Create a temporary backup file.

        Args:
            compress (bool): Whether the backup should be compressed.

        Returns:
            tuple[str, Path]: Backup identifier and generated file path.

        Side Effects:
            Creates a temporary backup artifact on disk.
        """
        return self._capability.create_backup_to_temp(compress=compress)

    def check_operation_lock(self) -> Optional[str]:
        """
        Return the current backup/restore lock operation, if any.

        Args:
            None.

        Returns:
            Optional[str]: Active lock operation name.

        Side Effects:
            Reads provider lock state.
        """
        return self._capability.check_operation_lock()

    def get_restore_status(self) -> Optional[Dict[str, Any]]:
        """
        Return restore progress metadata when supported.

        Args:
            None.

        Returns:
            Optional[Dict[str, Any]]: Restore progress payload when available.

        Side Effects:
            Reads provider restore state.
        """
        return self._capability.get_restore_status()

    def restore_backup(self, backup_file: Path) -> Any:
        """
        Restore a backup file through the active provider.

        Args:
            backup_file (Path): Backup artifact to restore.

        Returns:
            Any: Provider-specific restore result.

        Side Effects:
            Mutates backend data by restoring the supplied backup.
        """
        return self._capability.restore_backup(backup_file)

    async def get_database_stats(self) -> Dict[str, Any]:
        """
        Return database statistics from the active provider.

        Args:
            None.

        Returns:
            Dict[str, Any]: Provider-specific statistics payload.

        Side Effects:
            Reads database metadata through the active provider.
        """
        return await self._capability.get_database_stats()
