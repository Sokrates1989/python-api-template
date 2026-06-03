"""Shared backend-aware sync service facade."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from api.schemas.sync.requests import SyncConflictResolveRequest, SyncOperationRequest
from api.settings import settings


class SyncService:
    """Dispatch sync requests to the active backend-specific implementation."""

    USER_PROFILE_ENTITY = "user_profile"

    def __init__(self) -> None:
        """
        Bind the service to the active provider-specific sync implementation.

        Args:
            None.

        Returns:
            None.

        Side Effects:
            Resolves the active sync delegate from the configured provider.
        """
        normalized_db_type = settings.normalized_db_type()
        if settings.is_sql_database():
            from backend.services.sql.sync_service import SyncService as SQLSyncService

            self._delegate = SQLSyncService()
        elif normalized_db_type == "neo4j":
            from backend.services.neo4j.sync_service import SyncService as Neo4jSyncService

            self._delegate = Neo4jSyncService()
        else:
            from backend.services.mongodb.sync_service import SyncService as MongoSyncService

            self._delegate = MongoSyncService()

    async def push_operations(
        self,
        *,
        user_id: str,
        operations: List[SyncOperationRequest],
    ) -> List[Dict[str, Any]]:
        """Replay a batch of offline sync operations."""
        return await self._delegate.push_operations(user_id=user_id, operations=operations)

    async def pull_changes(
        self,
        *,
        user_id: str,
        cursor: Optional[str],
        limit: int,
        entity_type: Optional[str],
    ) -> Dict[str, Any]:
        """Load incremental sync changes from the active backend."""
        return await self._delegate.pull_changes(
            user_id=user_id,
            cursor=cursor,
            limit=limit,
            entity_type=entity_type,
        )

    async def resolve_conflict(
        self,
        *,
        user_id: str,
        request: SyncConflictResolveRequest,
    ) -> Dict[str, Any]:
        """Resolve one sync conflict through the active backend implementation."""
        return await self._delegate.resolve_conflict(user_id=user_id, request=request)
