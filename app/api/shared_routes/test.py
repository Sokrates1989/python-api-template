"""Shared test and database inspection routes."""
from __future__ import annotations

from fastapi import APIRouter

from backend.shared_services.database_service import DatabaseService

router = APIRouter(tags=["test"], prefix="/test")


def get_service() -> DatabaseService:
    """
    Return the shared database service instance.

    Args:
        None.

    Returns:
        DatabaseService: Shared database service facade.

    Side Effects:
        Instantiates the service lazily for the current request.
    """
    return DatabaseService()


@router.get("/db-test")
async def test_database() -> dict:
    """Test the active database connection."""
    try:
        service = get_service()
        return await service.test_connection()
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@router.get("/db-info")
async def get_database_info() -> dict:
    """Return metadata about the active database provider."""
    try:
        service = get_service()
        return await service.get_database_info()
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@router.get("/db-sample-query")
async def execute_sample_query() -> dict:
    """Execute a provider-specific sample query."""
    try:
        service = get_service()
        return await service.execute_sample_query()
    except Exception as exc:
        return {"status": "error", "message": str(exc)}
