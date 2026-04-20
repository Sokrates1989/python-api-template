"""Database backup and restore service for SQL databases."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from .backup_dump_helpers import create_backup_to_temp
from .backup_restore_helpers import restore_backup
from .backup_state import BackupStateTracker
from .backup_stats_helpers import get_database_stats


class BackupService:
    """Facade for SQL backup creation, restore, and progress inspection."""

    LOCK_TIMEOUT = 7200

    def __init__(self) -> None:
        """Initialize file-based tracking for backup and restore operations."""
        self._state = BackupStateTracker.create(lock_timeout=self.LOCK_TIMEOUT)

    def get_restore_status(self) -> Optional[Dict]:
        """Return the current restore status, if one has been recorded."""
        return self._state.get_restore_status()

    def check_operation_lock(self) -> Optional[str]:
        """Return the active operation lock name, if any."""
        return self._state.check_operation_lock()

    def create_backup_to_temp(self, compress: bool = True) -> tuple[str, Path]:
        """Create a temporary database backup file for the configured backend."""
        return create_backup_to_temp(self._state, compress=compress)

    def get_database_stats(self) -> Dict:
        """Collect high-level statistics for the configured database."""
        return get_database_stats()

    def restore_backup(self, backup_file: Path) -> dict:
        """Restore the database from a temporary backup file."""
        return restore_backup(self._state, backup_file)
