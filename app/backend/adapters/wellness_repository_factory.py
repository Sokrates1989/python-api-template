"""Provider adapters and factory for wellness repository implementations."""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from backend.ports.wellness_repository import WellnessRepository


class _WellnessRepositoryAdapterBase:
    """Delegate wellness repository calls to one backend-specific service."""

    def __init__(self, service_factory: Callable[[], WellnessRepository]) -> None:
        """Instantiate the backend-specific wellness service.

        Args:
            service_factory (Callable[[], WellnessRepository]): Factory that builds
                the backend wellness service implementation.
        """
        self._service = service_factory()

    async def get_dashboard(self, user_id: str):
        """Return the dashboard payload for one user.

        Args:
            user_id (str): Authenticated user identifier.

        Returns:
            Any: Backend-specific dashboard response.
        """
        return await self._service.get_dashboard(user_id=user_id)

    async def list_activities(self, user_id: str):
        """Return the activity catalog for one user.

        Args:
            user_id (str): Authenticated user identifier.

        Returns:
            Any: Backend-specific activity list response.
        """
        return await self._service.list_activities(user_id=user_id)

    async def get_sync_bootstrap(self, user_id: str, diary_limit: int = 50, checkin_limit: int = 50):
        """Return the initial sync bootstrap payload.

        Args:
            user_id (str): Authenticated user identifier.
            diary_limit (int): Maximum diary entries to include.
            checkin_limit (int): Maximum check-ins to include.

        Returns:
            Any: Backend-specific sync bootstrap response.
        """
        return await self._service.get_sync_bootstrap(user_id=user_id, diary_limit=diary_limit, checkin_limit=checkin_limit)

    async def get_sync_changes(self, user_id: str, cursor: Optional[str] = None, limit: int = 100, entity_type: Optional[str] = None):
        """Return incremental sync changes for one user.

        Args:
            user_id (str): Authenticated user identifier.
            cursor (Optional[str]): Incremental sync cursor.
            limit (int): Maximum number of changes to return.
            entity_type (Optional[str]): Optional entity type filter.

        Returns:
            Any: Backend-specific sync changes response.
        """
        return await self._service.get_sync_changes(user_id=user_id, cursor=cursor, limit=limit, entity_type=entity_type)

    async def update_activity(self, user_id: str, activity_id: str, favorite: Optional[bool] = None):
        """Update one activity record for the user.

        Args:
            user_id (str): Authenticated user identifier.
            activity_id (str): Activity identifier.
            favorite (Optional[bool]): Updated favorite state.

        Returns:
            Any: Backend-specific activity update response.
        """
        return await self._service.update_activity(user_id=user_id, activity_id=activity_id, favorite=favorite)

    async def list_diary_entries(self, user_id: str, limit: int = 20):
        """Return diary entries for one user.

        Args:
            user_id (str): Authenticated user identifier.
            limit (int): Maximum number of diary entries to return.

        Returns:
            Any: Backend-specific diary list response.
        """
        return await self._service.list_diary_entries(user_id=user_id, limit=limit)

    async def create_diary_entry(self, user_id: str, title: str, summary: str, mood_score: int, tag_keys: List[str], related_activity_id: Optional[str] = None):
        """Create a diary entry for one user.

        Args:
            user_id (str): Authenticated user identifier.
            title (str): Diary entry title.
            summary (str): Diary entry summary.
            mood_score (int): Mood score linked to the entry.
            tag_keys (List[str]): Tag keys for the entry.
            related_activity_id (Optional[str]): Optional related activity identifier.

        Returns:
            Any: Backend-specific diary creation response.
        """
        return await self._service.create_diary_entry(user_id=user_id, title=title, summary=summary, mood_score=mood_score, tag_keys=tag_keys, related_activity_id=related_activity_id)

    async def create_checkin(
        self,
        user_id: str,
        mood_score: int,
        stress_score: int,
        energy_score: int,
        note: Optional[str] = None,
        recorded_at: Optional[str] = None,
        tag_keys: Optional[List[str]] = None,
        metrics: Optional[Dict[str, int]] = None,
        activity_id: Optional[str] = None,
    ):
        """Create a check-in for one user.

        Args:
            user_id (str): Authenticated user identifier.
            mood_score (int): Mood score to record.
            stress_score (int): Stress score to record.
            energy_score (int): Energy score to record.
            note (Optional[str]): Optional note.
            recorded_at (Optional[str]): Optional ISO occurrence timestamp.
            tag_keys (Optional[List[str]]): Semantic tags for the check-in.
            metrics (Optional[Dict[str, int]]): Captured flexible metrics.
            activity_id (Optional[str]): Optional linked activity id.

        Returns:
            Any: Backend-specific check-in creation response.
        """
        return await self._service.create_checkin(
            user_id=user_id,
            mood_score=mood_score,
            stress_score=stress_score,
            energy_score=energy_score,
            note=note,
            recorded_at=recorded_at,
            tag_keys=tag_keys,
            metrics=metrics,
            activity_id=activity_id,
        )

    async def reset_user_data(self, user_id: str, *, keep_activity_catalog: bool = True):
        """Reset wellness data for one user.

        Args:
            user_id (str): Authenticated user identifier.
            keep_activity_catalog (bool): Whether starter activities should be restored.

        Returns:
            Any: Backend-specific reset response.
        """
        return await self._service.reset_user_data(user_id=user_id, keep_activity_catalog=keep_activity_catalog)


class MongoDBWellnessRepositoryAdapter(_WellnessRepositoryAdapterBase):
    """Adapt the MongoDB wellness service to the repository protocol."""

    def __init__(self) -> None:
        """Bind the adapter to the MongoDB wellness service implementation."""
        from backend.services.mongodb.wellness_service import WellnessService as MongoWellnessService

        super().__init__(MongoWellnessService)


class Neo4jWellnessRepositoryAdapter(_WellnessRepositoryAdapterBase):
    """Adapt the Neo4j wellness service to the repository protocol."""

    def __init__(self) -> None:
        """Bind the adapter to the Neo4j wellness runtime implementation."""
        from backend.services.neo4j.wellness_runtime import WellnessService as Neo4jWellnessService

        super().__init__(Neo4jWellnessService)


class SQLWellnessRepositoryAdapter(_WellnessRepositoryAdapterBase):
    """Adapt the SQL wellness service to the repository protocol."""

    def __init__(self) -> None:
        """Bind the adapter to the SQL wellness service implementation."""
        from backend.services.sql.wellness_service import WellnessService as SQLWellnessService

        super().__init__(SQLWellnessService)


WELLNESS_REPOSITORY_ADAPTERS: Dict[str, Callable[[], WellnessRepository]] = {
    "mongodb": MongoDBWellnessRepositoryAdapter,
    "mongo": MongoDBWellnessRepositoryAdapter,
    "neo4j": Neo4jWellnessRepositoryAdapter,
    "sql": SQLWellnessRepositoryAdapter,
    "postgresql": SQLWellnessRepositoryAdapter,
    "postgres": SQLWellnessRepositoryAdapter,
    "mysql": SQLWellnessRepositoryAdapter,
    "sqlite": SQLWellnessRepositoryAdapter,
}


def normalize_repository_db_type(db_type: str) -> str:
    """Normalize incoming DB_TYPE values to the adapter registry keys."""

    normalized = (db_type or "").strip().lower()
    if normalized == "mongo":
        return "mongodb"
    if normalized in {"postgresql", "postgres", "mysql", "sqlite", "sql"}:
        return "sql"
    return normalized


def create_wellness_repository(db_type: str) -> WellnessRepository:
    """Instantiate the repository adapter for the active backend provider."""

    normalized = normalize_repository_db_type(db_type)
    adapter_cls = WELLNESS_REPOSITORY_ADAPTERS.get(normalized)
    if adapter_cls is None:
        raise ValueError(
            f"Unsupported database type for wellness repository: {db_type}. "
            "Supported: mongodb, neo4j, sql/postgresql/postgres"
        )
    return adapter_cls()


def supports_wellness_repository(db_type: str) -> bool:
    """Return True when the DB type has a wellness repository adapter."""

    normalized = normalize_repository_db_type(db_type)
    return normalized in WELLNESS_REPOSITORY_ADAPTERS
