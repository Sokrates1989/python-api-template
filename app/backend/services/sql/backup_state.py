"""Locking and progress tracking for SQL backup operations."""
from __future__ import annotations

import json
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class BackupStateTracker:
    """Persist lock and restore progress state for backup operations."""

    data_dir: Path
    lock_file: Path
    status_file: Path
    warnings_file: Path
    lock_timeout: int

    @classmethod
    def create(cls, *, namespace: str = "sql_backup", lock_timeout: int = 7200) -> "BackupStateTracker":
        """Create the tracker using a temp-directory namespace."""
        data_dir = Path(tempfile.gettempdir()) / namespace
        data_dir.mkdir(exist_ok=True)
        return cls(
            data_dir=data_dir,
            lock_file=data_dir / "operation.lock",
            status_file=data_dir / "restore_status.json",
            warnings_file=data_dir / "restore_warnings.json",
            lock_timeout=lock_timeout,
        )

    def acquire_lock(self, operation: str) -> bool:
        """Acquire an operation lock unless an active one already exists."""
        try:
            if self.lock_file.exists():
                lock_data = json.loads(self.lock_file.read_text())
                lock_time = lock_data.get("timestamp", 0)
                if time.time() - lock_time < self.lock_timeout:
                    return False
            lock_data = {"operation": operation, "timestamp": time.time()}
            self.lock_file.write_text(json.dumps(lock_data))
            return True
        except Exception as exc:  # pragma: no cover - defensive fallback
            print(f"Warning: Failed to acquire lock: {exc}")
            return True

    def release_lock(self) -> None:
        """Release the current operation lock if one exists."""
        try:
            if self.lock_file.exists():
                self.lock_file.unlink()
        except Exception as exc:  # pragma: no cover - defensive fallback
            print(f"Warning: Failed to release lock: {exc}")

    def update_restore_progress(
        self,
        *,
        status: str,
        current: int = 0,
        total: int = 0,
        message: str = "",
        warnings: Optional[list] = None,
    ) -> None:
        """Write restore progress and warnings to disk."""
        try:
            progress_data = {
                "status": status,
                "current": current,
                "total": total,
                "message": message,
                "warnings_count": len(warnings) if warnings else 0,
                "timestamp": datetime.now().isoformat(),
            }
            self.status_file.write_text(json.dumps(progress_data, indent=2))
            if warnings:
                self.warnings_file.write_text(json.dumps(warnings, indent=2))
            elif self.warnings_file.exists():
                self.warnings_file.unlink()
        except Exception as exc:  # pragma: no cover - defensive fallback
            print(f"Warning: Failed to update progress: {exc}")

    def get_restore_status(self) -> Optional[dict]:
        """Load current restore progress, including warnings and lock state."""
        try:
            if not self.status_file.exists():
                return None
            status_data = json.loads(self.status_file.read_text())
            if self.warnings_file.exists():
                status_data["warnings"] = json.loads(self.warnings_file.read_text())
            lock_operation = self.check_operation_lock()
            status_data["is_locked"] = bool(lock_operation)
            status_data["lock_operation"] = lock_operation
            return status_data
        except Exception as exc:  # pragma: no cover - defensive fallback
            print(f"Warning: Failed to get restore status: {exc}")
            return None

    def check_operation_lock(self) -> Optional[str]:
        """Return the active operation name if the lock is still valid."""
        try:
            if not self.lock_file.exists():
                return None
            lock_data = json.loads(self.lock_file.read_text())
            lock_time = lock_data.get("timestamp", 0)
            if time.time() - lock_time >= self.lock_timeout:
                self.lock_file.unlink()
                return None
            return lock_data.get("operation")
        except Exception as exc:  # pragma: no cover - defensive fallback
            print(f"Warning: Failed to check lock: {exc}")
            return None
