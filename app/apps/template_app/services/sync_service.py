"""Sync service entry point owned by the template backend app."""
from backend.shared_services.sync_service import SyncService as SharedSyncService


class TemplateAppSyncService(SharedSyncService):
    """Template app sync service facade."""
