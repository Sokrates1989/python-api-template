"""Database-agnostic example service facade."""
from __future__ import annotations

from typing import Any, Dict, Optional

from backend.adapters.example_repository_factory import create_example_repository
from backend.database import get_database_handler
from backend.ports.example_repository import ExampleRepository


class ExampleService:
    """Dispatch example operations to the configured database backend adapter."""

    def __init__(self):
        handler = get_database_handler()
        db_type = getattr(handler, "db_type", "").strip().lower()
        self._repository: ExampleRepository = create_example_repository(db_type)
        self._db_type = db_type

    @property
    def db_type(self) -> str:
        """Return active backend type for route-level compatibility formatting."""
        return self._db_type

    async def create_example(
        self,
        name: str,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await self._repository.create_example(name=name, description=description)

    async def get_example(self, example_id: str) -> Dict[str, Any]:
        return await self._repository.get_example(example_id)

    async def list_examples(
        self,
        limit: int = 100,
        offset: int = 0,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await self._repository.list_examples(limit=limit, offset=offset, name=name)

    async def update_example(
        self,
        example_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await self._repository.update_example(
            example_id=example_id,
            name=name,
            description=description,
        )

    async def delete_example(self, example_id: str) -> Dict[str, Any]:
        return await self._repository.delete_example(example_id)

    async def delete_all_examples(self) -> Dict[str, Any]:
        return await self._repository.delete_all_examples()
