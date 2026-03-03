"""Example domain repository contract."""
from __future__ import annotations

from typing import Any, Dict, Optional, Protocol, runtime_checkable

ExampleOperationResult = Dict[str, Any]


@runtime_checkable
class ExampleRepository(Protocol):
    """Port for example persistence operations across database providers."""

    async def create_example(
        self,
        name: str,
        description: Optional[str] = None,
    ) -> ExampleOperationResult:
        ...

    async def get_example(self, example_id: str) -> ExampleOperationResult:
        ...

    async def list_examples(
        self,
        limit: int = 100,
        offset: int = 0,
        name: Optional[str] = None,
    ) -> ExampleOperationResult:
        ...

    async def update_example(
        self,
        example_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> ExampleOperationResult:
        ...

    async def delete_example(self, example_id: str) -> ExampleOperationResult:
        ...

    async def delete_all_examples(self) -> ExampleOperationResult:
        ...
