"""
Compatibility wrapper for the legacy backup router.

Built-in backup routes are not mounted by current app definitions. Prefer the
external backup-restore service documented in ``docs/DATABASE_BACKUP.md``.
"""

from ..backup import router

__all__ = ["router"]
