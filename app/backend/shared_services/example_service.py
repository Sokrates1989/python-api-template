"""Shared database-agnostic example service facade."""
from __future__ import annotations

from typing import Any, Dict, Optional

from backend.adapters.example_repository_factory import create_example_repository
from backend.database import get_database_handler
from backend.ports.example_repository import ExampleRepository


class ExampleService:
    """Dispatch example operations to the configured database backend adapter."""

    def __init__(self) -> None:
        """
        Bind the service to the active provider-specific example repository.

        Args:
            None.

        Returns:
            None.

        Side Effects:
            Resolves the active database handler and repository adapter.
        """
        handler = get_database_handler()
        db_type = getattr(handler, "db_type", "").strip().lower()
        self._repository: ExampleRepository = create_example_repository(db_type)
        self._db_type = db_type

    @property
    def db_type(self) -> str:
        """
        Return the active backend type for route compatibility formatting.

        Args:
            None.

        Returns:
            str: Active provider identifier.

        Side Effects:
            None.
        """
        return self._db_type

    async def create_example(self, name: str, description: Optional[str] = None) -> Dict[str, Any]:
        """
        Create an example record.

        Args:
            name (str): Example name.
            description (Optional[str]): Optional example description.

        Returns:
            Dict[str, Any]: Provider-specific mutation payload.

        Side Effects:
            Persists a record through the active repository.
        """
        return await self._repository.create_example(name=name, description=description)

    async def get_example(self, example_id: str) -> Dict[str, Any]:
        """
        Fetch one example record by id.

        Args:
            example_id (str): Example identifier.

        Returns:
            Dict[str, Any]: Provider-specific detail payload.

        Side Effects:
            Reads a record through the active repository.
        """
        return await self._repository.get_example(example_id)

    async def list_examples(
        self,
        limit: int = 100,
        offset: int = 0,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        List example records.

        Args:
            limit (int): Maximum number of records.
            offset (int): Pagination offset.
            name (Optional[str]): Optional name filter.

        Returns:
            Dict[str, Any]: Provider-specific list payload.

        Side Effects:
            Reads records through the active repository.
        """
        return await self._repository.list_examples(limit=limit, offset=offset, name=name)

    async def update_example(
        self,
        example_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Update an example record.

        Args:
            example_id (str): Example identifier.
            name (Optional[str]): Updated example name.
            description (Optional[str]): Updated description.

        Returns:
            Dict[str, Any]: Provider-specific mutation payload.

        Side Effects:
            Persists changes through the active repository.
        """
        return await self._repository.update_example(
            example_id=example_id,
            name=name,
            description=description,
        )

    async def delete_example(self, example_id: str) -> Dict[str, Any]:
        """
        Delete one example record.

        Args:
            example_id (str): Example identifier.

        Returns:
            Dict[str, Any]: Provider-specific deletion payload.

        Side Effects:
            Deletes a record through the active repository.
        """
        return await self._repository.delete_example(example_id)

    async def delete_all_examples(self) -> Dict[str, Any]:
        """
        Delete all example records.

        Args:
            None.

        Returns:
            Dict[str, Any]: Provider-specific deletion payload.

        Side Effects:
            Deletes records through the active repository.
        """
        return await self._repository.delete_all_examples()
