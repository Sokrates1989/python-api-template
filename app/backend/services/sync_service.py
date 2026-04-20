"""Backend-aware sync service facade."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from api.schemas.sync.requests import SyncConflictResolveRequest, SyncOperationRequest
from api.settings import settings
from backend.services.mongodb.sync_service import SyncService as MongoSyncService
from backend.services.neo4j.sync_service import SyncService as Neo4jSyncService
from backend.services.sql.sync_service import SyncService as SQLSyncService


class SyncService:
    """Dispatch sync requests to the active backend-specific implementation."""

    USER_PROFILE_ENTITY = SQLSyncService.USER_PROFILE_ENTITY

    def __init__(self) -> None:
        """Bind the facade to the active backend-specific sync service."""
        normalized_db_type = settings.normalized_db_type()
        if settings.is_sql_database():
            self._delegate = SQLSyncService()
        elif normalized_db_type == "neo4j":
            self._delegate = Neo4jSyncService()
        else:
            self._delegate = MongoSyncService()

    async def push_operations(
        self,
        *,
        user_id: str,
        operations: List[SyncOperationRequest],
    ) -> List[Dict[str, Any]]:
        """Replay a batch of offline sync operations.

        Args:
            user_id (str): Authenticated user identifier.
            operations (List[SyncOperationRequest]): Operations to replay.

        Returns:
            List[Dict[str, Any]]: Backend-specific sync result payloads.
        """
        return await self._delegate.push_operations(user_id=user_id, operations=operations)

    async def pull_changes(
        self,
        *,
        user_id: str,
        cursor: Optional[str],
        limit: int,
        entity_type: Optional[str],
    ) -> Dict[str, Any]:
        """Load incremental sync changes from the active backend.

        Args:
            user_id (str): Authenticated user identifier.
            cursor (Optional[str]): Incremental sync cursor.
            limit (int): Maximum number of changes to return.
            entity_type (Optional[str]): Optional entity type filter.

        Returns:
            Dict[str, Any]: Incremental sync payload.
        """
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
        """Resolve one sync conflict through the active backend implementation.

        Args:
            user_id (str): Authenticated user identifier.
            request (SyncConflictResolveRequest): Conflict resolution request.

        Returns:
            Dict[str, Any]: Backend-specific conflict resolution payload.
        """
        return await self._delegate.resolve_conflict(user_id=user_id, request=request)
