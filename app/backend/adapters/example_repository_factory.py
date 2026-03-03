"""Provider adapters and factory for example repository implementations."""
from __future__ import annotations

import asyncio
from typing import Callable, Dict, Optional

from backend.ports.example_repository import ExampleRepository


class SQLExampleRepositoryAdapter:
    """Example repository adapter for SQL backends."""

    def __init__(self) -> None:
        from backend.services.sql.example_service import ExampleService as SQLExampleService

        self._service = SQLExampleService()

    async def create_example(self, name: str, description: Optional[str] = None):
        return await self._service.create_example(name=name, description=description)

    async def get_example(self, example_id: str):
        return await self._service.get_example(example_id)

    async def list_examples(
        self,
        limit: int = 100,
        offset: int = 0,
        name: Optional[str] = None,
    ):
        # SQL implementation currently has no name-filter parameter.
        return await self._service.list_examples(limit=limit, offset=offset)

    async def update_example(
        self,
        example_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ):
        return await self._service.update_example(
            example_id=example_id,
            name=name,
            description=description,
        )

    async def delete_example(self, example_id: str):
        return await self._service.delete_example(example_id)

    async def delete_all_examples(self):
        return {
            "status": "error",
            "message": "Delete all examples is only available for neo4j",
        }


class Neo4jExampleRepositoryAdapter:
    """Example repository adapter for Neo4j backends."""

    def __init__(self) -> None:
        from backend.services.neo4j.example_node_service import (
            ExampleNodeService as Neo4jExampleService,
        )

        self._service = Neo4jExampleService()

    async def create_example(self, name: str, description: Optional[str] = None):
        node = await asyncio.to_thread(self._service.create, name, description)
        return {
            "status": "success",
            "message": "ExampleNode created successfully",
            "data": node.model_dump(),
        }

    async def get_example(self, example_id: str):
        node = await asyncio.to_thread(self._service.get_by_id, example_id)
        if not node:
            return {
                "status": "error",
                "message": f"ExampleNode with id {example_id} not found",
            }
        return {
            "status": "success",
            "data": node.model_dump(),
        }

    async def list_examples(
        self,
        limit: int = 100,
        offset: int = 0,
        name: Optional[str] = None,
    ):
        nodes = await asyncio.to_thread(
            self._service.get_all,
            skip=offset,
            limit=limit,
            name_filter=name,
        )
        total = await asyncio.to_thread(self._service.count, name_filter=name)
        data = [node.model_dump() for node in nodes]
        return {
            "status": "success",
            "data": data,
            "pagination": {
                "total": total,
                "limit": limit,
                "offset": offset,
                "count": len(data),
            },
        }

    async def update_example(
        self,
        example_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ):
        updated = await asyncio.to_thread(
            self._service.update,
            node_id=example_id,
            name=name,
            description=description,
        )
        if not updated:
            return {
                "status": "error",
                "message": f"ExampleNode with id {example_id} not found",
            }
        return {
            "status": "success",
            "message": "ExampleNode updated successfully",
            "data": updated.model_dump(),
        }

    async def delete_example(self, example_id: str):
        deleted = await asyncio.to_thread(self._service.delete, example_id)
        if not deleted:
            return {
                "status": "error",
                "message": f"ExampleNode with id {example_id} not found",
            }
        return {
            "status": "success",
            "message": "ExampleNode deleted successfully",
        }

    async def delete_all_examples(self):
        deleted_count = await asyncio.to_thread(self._service.delete_all)
        return {
            "status": "success",
            "message": f"Deleted {deleted_count} ExampleNode(s)",
            "deleted_count": deleted_count,
        }


class MongoDBExampleRepositoryAdapter:
    """Example repository adapter for MongoDB backends."""

    def __init__(self) -> None:
        from backend.services.mongodb.example_service import ExampleService as MongoExampleService

        self._service = MongoExampleService()

    async def create_example(self, name: str, description: Optional[str] = None):
        return await self._service.create_example(name=name, description=description)

    async def get_example(self, example_id: str):
        return await self._service.get_example(example_id)

    async def list_examples(
        self,
        limit: int = 100,
        offset: int = 0,
        name: Optional[str] = None,
    ):
        return await self._service.list_examples(limit=limit, offset=offset, name=name)

    async def update_example(
        self,
        example_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ):
        return await self._service.update_example(
            example_id=example_id,
            name=name,
            description=description,
        )

    async def delete_example(self, example_id: str):
        return await self._service.delete_example(example_id)

    async def delete_all_examples(self):
        return await self._service.delete_all_examples()


EXAMPLE_REPOSITORY_ADAPTERS: Dict[str, Callable[[], ExampleRepository]] = {
    "sql": SQLExampleRepositoryAdapter,
    "postgresql": SQLExampleRepositoryAdapter,
    "postgres": SQLExampleRepositoryAdapter,
    "mysql": SQLExampleRepositoryAdapter,
    "sqlite": SQLExampleRepositoryAdapter,
    "neo4j": Neo4jExampleRepositoryAdapter,
    "mongodb": MongoDBExampleRepositoryAdapter,
    "mongo": MongoDBExampleRepositoryAdapter,
}


def normalize_repository_db_type(db_type: str) -> str:
    """Normalize DB type names for adapter lookup."""
    normalized = (db_type or "").strip().lower()
    if normalized in {"postgresql", "postgres", "mysql", "sqlite", "sql"}:
        return "sql"
    if normalized == "mongo":
        return "mongodb"
    return normalized


def create_example_repository(db_type: str) -> ExampleRepository:
    """Create an example repository adapter for the provided backend type."""
    normalized = normalize_repository_db_type(db_type)
    adapter_cls = EXAMPLE_REPOSITORY_ADAPTERS.get(normalized)
    if adapter_cls is None:
        raise ValueError(
            f"Unsupported database type for example repository: {db_type}. "
            "Supported: postgresql/postgres, neo4j, mongodb (legacy: mysql, sqlite)"
        )
    return adapter_cls()


def supports_example_repository(db_type: str) -> bool:
    """Return True when an example repository adapter exists for the backend."""
    normalized = normalize_repository_db_type(db_type)
    return normalized in EXAMPLE_REPOSITORY_ADAPTERS
