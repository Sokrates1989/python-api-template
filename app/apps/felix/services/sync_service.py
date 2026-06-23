"""Sync service facade owned by the Felix backend app."""
from backend.shared_services.sync_service import SyncService as SharedSyncService


class FelixSyncService(SharedSyncService):
    """Felix sync service facade."""
