"""Provider adapters and factory for wellness repository implementations."""
from __future__ import annotations

from typing import Callable, Dict, List, Optional

from backend.ports.wellness_repository import WellnessRepository


class MongoDBWellnessRepositoryAdapter:
    def __init__(self) -> None:
        from backend.services.mongodb.wellness_service import WellnessService as MongoWellnessService
        self._service = MongoWellnessService()

    async def get_dashboard(self, user_id: str):
        return await self._service.get_dashboard(user_id=user_id)

    async def list_activities(self, user_id: str):
        return await self._service.list_activities(user_id=user_id)

    async def get_sync_bootstrap(self, user_id: str, diary_limit: int = 50, checkin_limit: int = 50):
        return await self._service.get_sync_bootstrap(user_id=user_id, diary_limit=diary_limit, checkin_limit=checkin_limit)

    async def get_sync_changes(self, user_id: str, cursor: Optional[str] = None, limit: int = 100, entity_type: Optional[str] = None):
        return await self._service.get_sync_changes(user_id=user_id, cursor=cursor, limit=limit, entity_type=entity_type)

    async def update_activity(self, user_id: str, activity_id: str, favorite: Optional[bool] = None):
        return await self._service.update_activity(user_id=user_id, activity_id=activity_id, favorite=favorite)

    async def list_diary_entries(self, user_id: str, limit: int = 20):
        return await self._service.list_diary_entries(user_id=user_id, limit=limit)

    async def create_diary_entry(self, user_id: str, title: str, summary: str, mood_score: int, tag_keys: List[str], related_activity_id: Optional[str] = None):
        return await self._service.create_diary_entry(user_id=user_id, title=title, summary=summary, mood_score=mood_score, tag_keys=tag_keys, related_activity_id=related_activity_id)

    async def create_checkin(self, user_id: str, mood_score: int, stress_score: int, energy_score: int, note: Optional[str] = None):
        return await self._service.create_checkin(user_id=user_id, mood_score=mood_score, stress_score=stress_score, energy_score=energy_score, note=note)

    async def reset_user_data(self, user_id: str, *, keep_activity_catalog: bool = True):
        return await self._service.reset_user_data(user_id=user_id, keep_activity_catalog=keep_activity_catalog)


class SQLWellnessRepositoryAdapter:
    def __init__(self) -> None:
        from backend.services.sql.wellness_service import WellnessService as SQLWellnessService
        self._service = SQLWellnessService()

    async def get_dashboard(self, user_id: str):
        return await self._service.get_dashboard(user_id=user_id)

    async def list_activities(self, user_id: str):
        return await self._service.list_activities(user_id=user_id)

    async def get_sync_bootstrap(self, user_id: str, diary_limit: int = 50, checkin_limit: int = 50):
        return await self._service.get_sync_bootstrap(user_id=user_id, diary_limit=diary_limit, checkin_limit=checkin_limit)

    async def get_sync_changes(self, user_id: str, cursor: Optional[str] = None, limit: int = 100, entity_type: Optional[str] = None):
        return await self._service.get_sync_changes(user_id=user_id, cursor=cursor, limit=limit, entity_type=entity_type)

    async def update_activity(self, user_id: str, activity_id: str, favorite: Optional[bool] = None):
        return await self._service.update_activity(user_id=user_id, activity_id=activity_id, favorite=favorite)

    async def list_diary_entries(self, user_id: str, limit: int = 20):
        return await self._service.list_diary_entries(user_id=user_id, limit=limit)

    async def create_diary_entry(self, user_id: str, title: str, summary: str, mood_score: int, tag_keys: List[str], related_activity_id: Optional[str] = None):
        return await self._service.create_diary_entry(user_id=user_id, title=title, summary=summary, mood_score=mood_score, tag_keys=tag_keys, related_activity_id=related_activity_id)

    async def create_checkin(self, user_id: str, mood_score: int, stress_score: int, energy_score: int, note: Optional[str] = None):
        return await self._service.create_checkin(user_id=user_id, mood_score=mood_score, stress_score=stress_score, energy_score=energy_score, note=note)

    async def reset_user_data(self, user_id: str, *, keep_activity_catalog: bool = True):
        return await self._service.reset_user_data(user_id=user_id, keep_activity_catalog=keep_activity_catalog)


WELLNESS_REPOSITORY_ADAPTERS: Dict[str, Callable[[], WellnessRepository]] = {
    "mongodb": MongoDBWellnessRepositoryAdapter,
    "mongo": MongoDBWellnessRepositoryAdapter,
    "sql": SQLWellnessRepositoryAdapter,
    "postgresql": SQLWellnessRepositoryAdapter,
    "postgres": SQLWellnessRepositoryAdapter,
    "mysql": SQLWellnessRepositoryAdapter,
    "sqlite": SQLWellnessRepositoryAdapter,
}


def normalize_repository_db_type(db_type: str) -> str:
    normalized = (db_type or "").strip().lower()
    if normalized == "mongo":
        return "mongodb"
    if normalized in {"postgresql", "postgres", "mysql", "sqlite", "sql"}:
        return "sql"
    return normalized


def create_wellness_repository(db_type: str) -> WellnessRepository:
    normalized = normalize_repository_db_type(db_type)
    adapter_cls = WELLNESS_REPOSITORY_ADAPTERS.get(normalized)
    if adapter_cls is None:
        raise ValueError(f"Unsupported database type for wellness repository: {db_type}. Supported: mongodb, sql/postgresql/postgres")
    return adapter_cls()


def supports_wellness_repository(db_type: str) -> bool:
    normalized = normalize_repository_db_type(db_type)
    return normalized in WELLNESS_REPOSITORY_ADAPTERS
