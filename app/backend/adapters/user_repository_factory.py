"""Provider adapters and factory for user repository implementations."""
from __future__ import annotations

from typing import Callable, Dict

from backend.ports.user_repository import UserRepository


class SQLUserRepositoryAdapter:
    """User repository adapter for SQL backends."""

    def __init__(self) -> None:
        from backend.services.sql.user_service import UserService as SQLUserService

        self._service = SQLUserService()

    async def create_user(self, *args, **kwargs):
        return await self._service.create_user(*args, **kwargs)

    async def get_user(self, *args, **kwargs):
        return await self._service.get_user(*args, **kwargs)

    async def update_user(self, *args, **kwargs):
        return await self._service.update_user(*args, **kwargs)

    async def update_username(self, *args, **kwargs):
        return await self._service.update_username(*args, **kwargs)


class Neo4jUserRepositoryAdapter:
    """User repository adapter for Neo4j backends."""

    def __init__(self) -> None:
        from backend.services.neo4j.user_service import UserService as Neo4jUserService

        self._service = Neo4jUserService()

    async def create_user(self, *args, **kwargs):
        return await self._service.create_user(*args, **kwargs)

    async def get_user(self, *args, **kwargs):
        return await self._service.get_user(*args, **kwargs)

    async def update_user(self, *args, **kwargs):
        return await self._service.update_user(*args, **kwargs)

    async def update_username(self, *args, **kwargs):
        return await self._service.update_username(*args, **kwargs)


class MongoDBUserRepositoryAdapter:
    """User repository adapter for MongoDB backends."""

    def __init__(self) -> None:
        from backend.services.mongodb.user_service import UserService as MongoUserService

        self._service = MongoUserService()

    async def create_user(self, *args, **kwargs):
        return await self._service.create_user(*args, **kwargs)

    async def get_user(self, *args, **kwargs):
        return await self._service.get_user(*args, **kwargs)

    async def update_user(self, *args, **kwargs):
        return await self._service.update_user(*args, **kwargs)

    async def update_username(self, *args, **kwargs):
        return await self._service.update_username(*args, **kwargs)


USER_REPOSITORY_ADAPTERS: Dict[str, Callable[[], UserRepository]] = {
    "sql": SQLUserRepositoryAdapter,
    "postgresql": SQLUserRepositoryAdapter,
    "postgres": SQLUserRepositoryAdapter,
    "mysql": SQLUserRepositoryAdapter,
    "sqlite": SQLUserRepositoryAdapter,
    "neo4j": Neo4jUserRepositoryAdapter,
    "mongodb": MongoDBUserRepositoryAdapter,
    "mongo": MongoDBUserRepositoryAdapter,
}


def normalize_repository_db_type(db_type: str) -> str:
    """Normalize DB type names for adapter lookup."""
    normalized = (db_type or "").strip().lower()
    if normalized in {"postgresql", "postgres", "mysql", "sqlite", "sql"}:
        return "sql"
    if normalized == "mongo":
        return "mongodb"
    return normalized


def create_user_repository(db_type: str) -> UserRepository:
    """Create a user repository adapter for the provided backend type."""
    normalized = normalize_repository_db_type(db_type)
    adapter_cls = USER_REPOSITORY_ADAPTERS.get(normalized)
    if adapter_cls is None:
        raise ValueError(
            f"Unsupported database type for user repository: {db_type}. "
            "Supported: postgresql/postgres, neo4j, mongodb (legacy: mysql, sqlite)"
        )
    return adapter_cls()
