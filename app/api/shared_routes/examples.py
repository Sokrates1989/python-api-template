"""Shared database-aware example CRUD routes."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from api.schemas.sql.examples.requests import ExampleCreateRequest, ExampleUpdateRequest
from api.schemas.sql.examples.responses import (
    ExampleDetailResponse,
    ExampleListResponse,
    ExampleMutationResponse,
)
from api.settings import settings
from backend.adapters.example_repository_factory import supports_example_repository
from backend.shared_services.example_service import ExampleService

_IS_NEO4J = settings.normalized_db_type() == "neo4j"
_SUPPORTS_EXAMPLES = supports_example_repository(settings.normalized_db_type())

router = APIRouter(
    tags=["Example Nodes (Neo4j)"] if _IS_NEO4J else ["examples"],
    prefix="/example-nodes" if _IS_NEO4J else "/examples",
)


def get_service() -> ExampleService:
    """Return the shared example service instance."""
    return ExampleService()


def _raise_result_error(result: dict) -> None:
    """Convert provider error payloads into HTTP exceptions."""
    message = str(result.get("message", "Database error"))
    if "not found" in message.lower():
        raise HTTPException(status_code=404, detail=message)
    raise HTTPException(status_code=500, detail=message)


def _ensure_examples_supported() -> None:
    """Ensure example routes are enabled for the active provider."""
    if not _SUPPORTS_EXAMPLES:
        raise HTTPException(
            status_code=400,
            detail=f"Example routes are not supported for database type: {settings.DB_TYPE}",
        )


@router.post("/", status_code=201)
async def create_example(example: ExampleCreateRequest) -> ExampleMutationResponse:
    """Create a new example record or Neo4j example node."""
    _ensure_examples_supported()
    service = get_service()
    result = await service.create_example(name=example.name, description=example.description)
    if result.get("status") == "error":
        _raise_result_error(result)
    return ExampleMutationResponse(**result)


@router.get("/{example_id}")
async def get_example(example_id: str) -> ExampleDetailResponse:
    """Return one example record by id."""
    _ensure_examples_supported()
    service = get_service()
    result = await service.get_example(example_id)
    if result.get("status") == "error":
        _raise_result_error(result)
    return ExampleDetailResponse(**result)


@router.get("/")
async def list_examples(
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    name: Optional[str] = Query(None, description="Neo4j only: filter by name"),
):
    """List example records with pagination."""
    _ensure_examples_supported()
    service = get_service()
    result = await service.list_examples(
        limit=limit,
        offset=offset,
        name=name if _IS_NEO4J else None,
    )
    if result.get("status") == "error":
        _raise_result_error(result)
    if _IS_NEO4J:
        pagination = result.get("pagination", {})
        return {
            "status": "success",
            "data": {
                "total": pagination.get("total", 0),
                "offset": pagination.get("offset", offset),
                "limit": pagination.get("limit", limit),
                "data": result.get("data", []),
            },
        }
    return ExampleListResponse(**result)


@router.put("/{example_id}")
async def update_example(example_id: str, example: ExampleUpdateRequest) -> ExampleMutationResponse:
    """Update one example record by id."""
    _ensure_examples_supported()
    if example.name is None and example.description is None:
        raise HTTPException(
            status_code=400,
            detail="At least one field (name or description) must be provided",
        )

    service = get_service()
    result = await service.update_example(
        example_id=example_id,
        name=example.name,
        description=example.description,
    )
    if result.get("status") == "error":
        _raise_result_error(result)
    return ExampleMutationResponse(**result)


@router.delete("/{example_id}")
async def delete_example(example_id: str) -> ExampleMutationResponse:
    """Delete one example record by id."""
    _ensure_examples_supported()
    service = get_service()
    result = await service.delete_example(example_id)
    if result.get("status") == "error":
        _raise_result_error(result)
    return ExampleMutationResponse(**result)


if _IS_NEO4J:
    @router.delete("/")
    async def delete_all_example_nodes() -> dict:
        """Delete all Neo4j example nodes."""
        _ensure_examples_supported()
        service = get_service()
        result = await service.delete_all_examples()
        if result.get("status") == "error":
            _raise_result_error(result)
        return result
