"""Provider-level capability contract used across adapters/services."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderCapabilities:
    """Feature flags describing what a backend provider supports."""

    supports_transactions: bool = False
    supports_migrations: bool = False
    supports_optimistic_locking: bool = False
    supports_sync_api: bool = False
    supports_user_repository: bool = True
    supports_example_repository: bool = False
    supports_backup_download: bool = False
    supports_restore_upload: bool = False
    supports_restore_status: bool = False
    supports_stats: bool = True
