"""
Test route - handles test and database-related HTTP endpoints.

STRUCTURE:
- This file: HTTP request/response handling only
- Business logic: backend/services/database_service.py
"""
from fastapi import APIRouter
from backend.services.database_service import DatabaseService

router = APIRouter(tags=["test"], prefix="/test")

# Initialize service
db_service = DatabaseService()


@router.get("/db-test")
async def test_database():
    """Test database connection."""
    try:
        return await db_service.test_connection()
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/db-info")
async def get_database_info():
    """Get information about the current database."""
    try:
        return await db_service.get_database_info()
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/db-sample-query")
async def execute_sample_query():
    """Execute a sample query on the database."""
    try:
        return await db_service.execute_sample_query()
    except Exception as e:
        return {"status": "error", "message": str(e)}