"""
API routes for ExampleNode CRUD operations (Neo4j).

This module demonstrates RESTful API design with Neo4j:
1. POST /example-nodes/ - Create a new node
2. GET /example-nodes/ - List all nodes (with pagination)
3. GET /example-nodes/{id} - Get a specific node
4. PUT /example-nodes/{id} - Update a node
5. DELETE /example-nodes/{id} - Delete a node

To create your own Neo4j routes:
1. Copy this file and rename it
2. Modify the service and model imports
3. Update the route paths and tags
4. Register in main.py (conditionally for Neo4j)
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List
from backend.services.example_node_service import ExampleNodeService


router = APIRouter(
    prefix="/example-nodes",
    tags=["Example Nodes (Neo4j)"],
    responses={404: {"description": "Not found"}},
)


def get_service() -> ExampleNodeService:
    """Get ExampleNodeService instance. Initialized on first call."""
    return ExampleNodeService()


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class ExampleNodeCreate(BaseModel):
    """Request model for creating a new ExampleNode."""
    name: str = Field(..., min_length=1, max_length=255, description="Node name")
    description: Optional[str] = Field(None, description="Optional description")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Sample Node",
                "description": "This is a sample Neo4j node"
            }
        }


class ExampleNodeUpdate(BaseModel):
    """Request model for updating an ExampleNode."""
    name: Optional[str] = Field(None, min_length=1, max_length=255, description="New name")
    description: Optional[str] = Field(None, description="New description")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Updated Node Name",
                "description": "Updated description"
            }
        }


class ExampleNodeResponse(BaseModel):
    """Response model for a single ExampleNode."""
    id: str
    name: str
    description: Optional[str]
    created_at: str
    updated_at: Optional[str]

    class Config:
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "Sample Node",
                "description": "This is a sample Neo4j node",
                "created_at": "2024-01-01T12:00:00",
                "updated_at": None
            }
        }


class ExampleNodeListResponse(BaseModel):
    """Response model for list of ExampleNodes."""
    total: int
    offset: int
    limit: int
    data: List[ExampleNodeResponse]


# ============================================================================
# CRUD ENDPOINTS
# ============================================================================

@router.post("/", response_model=dict, status_code=201)
async def create_example_node(node: ExampleNodeCreate):
    """
    Create a new ExampleNode in Neo4j.
    
    - **name**: Required node name (1-255 characters)
    - **description**: Optional description
    
    Returns the created node with generated ID and timestamp.
    """
    try:
        service = get_service()
        created_node = service.create(
            name=node.name,
            description=node.description
        )
        
        return {
            "status": "success",
            "message": "ExampleNode created successfully",
            "data": created_node.to_dict()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create node: {str(e)}")


@router.get("/", response_model=dict)
async def list_example_nodes(
    offset: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
    name: Optional[str] = Query(None, description="Filter by name (case-insensitive contains)")
):
    """
    List all ExampleNodes with pagination and optional filtering.
    
    - **offset**: Number of records to skip (default: 0)
    - **limit**: Maximum records to return (default: 100, max: 1000)
    - **name**: Optional name filter (case-insensitive contains)
    
    Returns paginated list of nodes.
    """
    try:
        service = get_service()
        
        # Get nodes and total count
        nodes = service.get_all(skip=offset, limit=limit, name_filter=name)
        total = service.count(name_filter=name)
        
        return {
            "status": "success",
            "data": {
                "total": total,
                "offset": offset,
                "limit": limit,
                "items": [node.to_dict() for node in nodes]
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list nodes: {str(e)}")


@router.get("/{node_id}", response_model=dict)
async def get_example_node(node_id: str):
    """
    Get a specific ExampleNode by ID.
    
    - **node_id**: UUID of the node
    
    Returns the node if found, 404 otherwise.
    """
    try:
        service = get_service()
        node = service.get_by_id(node_id)
        
        if not node:
            raise HTTPException(status_code=404, detail="ExampleNode not found")
        
        return {
            "status": "success",
            "data": node.to_dict()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get node: {str(e)}")


@router.put("/{node_id}", response_model=dict)
async def update_example_node(node_id: str, node_update: ExampleNodeUpdate):
    """
    Update an ExampleNode.
    
    - **node_id**: UUID of the node to update
    - **name**: Optional new name
    - **description**: Optional new description
    
    Returns the updated node if found, 404 otherwise.
    """
    try:
        service = get_service()
        
        # Check if at least one field is provided
        if node_update.name is None and node_update.description is None:
            raise HTTPException(
                status_code=400,
                detail="At least one field (name or description) must be provided"
            )
        
        updated_node = service.update(
            node_id=node_id,
            name=node_update.name,
            description=node_update.description
        )
        
        if not updated_node:
            raise HTTPException(status_code=404, detail="ExampleNode not found")
        
        return {
            "status": "success",
            "message": "ExampleNode updated successfully",
            "data": updated_node.to_dict()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update node: {str(e)}")


@router.delete("/{node_id}", response_model=dict)
async def delete_example_node(node_id: str):
    """
    Delete an ExampleNode.
    
    - **node_id**: UUID of the node to delete
    
    Returns success message if deleted, 404 if not found.
    """
    try:
        service = get_service()
        deleted = service.delete(node_id)
        
        if not deleted:
            raise HTTPException(status_code=404, detail="ExampleNode not found")
        
        return {
            "status": "success",
            "message": "ExampleNode deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete node: {str(e)}")


@router.delete("/", response_model=dict)
async def delete_all_example_nodes():
    """
    Delete all ExampleNodes (use with caution!).
    
    This endpoint is useful for testing and development.
    In production, you may want to remove or protect this endpoint.
    
    Returns the number of nodes deleted.
    """
    try:
        service = get_service()
        deleted_count = service.delete_all()
        
        return {
            "status": "success",
            "message": f"Deleted {deleted_count} ExampleNode(s)",
            "deleted_count": deleted_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete nodes: {str(e)}")
