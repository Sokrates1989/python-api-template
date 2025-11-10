"""
Example CRUD routes - demonstrates RESTful API endpoints.

This file shows how to:
1. Structure REST API endpoints
2. Handle request/response models with Pydantic
3. Implement proper HTTP methods (GET, POST, PUT, DELETE)
4. Return appropriate status codes

STRUCTURE:
- This file: HTTP request/response handling only
- Business logic: backend/services/example_service.py
- Data models: models/example.py
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional
from backend.services.sql.example_service import ExampleService

router = APIRouter(tags=["examples"], prefix="/examples")


# Helper function to get service instance (lazy initialization)
def get_service() -> ExampleService:
    """Get ExampleService instance. Initialized on first call."""
    return ExampleService()


# Pydantic models for request/response validation
class ExampleCreate(BaseModel):
    """Request model for creating an example."""
    name: str = Field(..., min_length=1, max_length=255, description="Name of the example")
    description: Optional[str] = Field(None, description="Optional description")


class ExampleUpdate(BaseModel):
    """Request model for updating an example."""
    name: Optional[str] = Field(None, min_length=1, max_length=255, description="New name")
    description: Optional[str] = Field(None, description="New description")


# ============================================================================
# CRUD Endpoints
# ============================================================================
# Note: Table is created automatically via Alembic migrations on startup.
# No manual initialization needed!

@router.post("/", status_code=201)
async def create_example(example: ExampleCreate):
    """
    Create a new example.
    
    Request body:
    - name: Required, 1-255 characters
    - description: Optional text
    
    Returns:
    - 201: Example created successfully
    - 500: Database error
    """
    service = get_service()
    result = await service.create_example(
        name=example.name,
        description=example.description
    )
    
    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result["message"])
    
    return result


@router.get("/{example_id}")
async def get_example(example_id: str):
    """
    Get a single example by ID.
    
    Path parameters:
    - example_id: UUID of the example
    
    Returns:
    - 200: Example found
    - 404: Example not found
    - 500: Database error
    """
    service = get_service()
    result = await service.get_example(example_id)
    
    if result["status"] == "error":
        if "not found" in result["message"]:
            raise HTTPException(status_code=404, detail=result["message"])
        raise HTTPException(status_code=500, detail=result["message"])
    
    return result


@router.get("/")
async def list_examples(
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip")
):
    """
    List all examples with pagination.
    
    Query parameters:
    - limit: Maximum number of results (1-1000, default: 100)
    - offset: Number of results to skip (default: 0)
    
    Returns:
    - 200: List of examples with pagination info
    - 500: Database error
    """
    service = get_service()
    result = await service.list_examples(limit=limit, offset=offset)
    
    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result["message"])
    
    return result


@router.put("/{example_id}")
async def update_example(example_id: str, example: ExampleUpdate):
    """
    Update an existing example (rename or update description).
    
    Path parameters:
    - example_id: UUID of the example
    
    Request body:
    - name: Optional new name
    - description: Optional new description
    
    At least one field must be provided.
    
    Returns:
    - 200: Example updated successfully
    - 404: Example not found
    - 400: No fields provided
    - 500: Database error
    """
    # Check if at least one field is provided
    if example.name is None and example.description is None:
        raise HTTPException(
            status_code=400,
            detail="At least one field (name or description) must be provided"
        )
    
    service = get_service()
    result = await service.update_example(
        example_id=example_id,
        name=example.name,
        description=example.description
    )
    
    if result["status"] == "error":
        if "not found" in result["message"]:
            raise HTTPException(status_code=404, detail=result["message"])
        raise HTTPException(status_code=500, detail=result["message"])
    
    return result


@router.delete("/{example_id}")
async def delete_example(example_id: str):
    """
    Delete an example by ID.
    
    Path parameters:
    - example_id: UUID of the example
    
    Returns:
    - 200: Example deleted successfully
    - 404: Example not found
    - 500: Database error
    """
    service = get_service()
    result = await service.delete_example(example_id)
    
    if result["status"] == "error":
        if "not found" in result["message"]:
            raise HTTPException(status_code=404, detail=result["message"])
        raise HTTPException(status_code=500, detail=result["message"])
    
    return result
