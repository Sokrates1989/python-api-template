"""Sync service entry point owned by the Postgres Template backend app."""
from backend.shared_services.sync_service import SyncService as SharedSyncService


class PostgresTemplateSyncService(SharedSyncService):
    """Postgres Template sync service facade."""
