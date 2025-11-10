"""
Example Neo4j node model demonstrating basic CRUD operations.

This is a template example showing how to:
1. Define a Neo4j node with properties
2. Use proper data types
3. Implement timestamps
4. Work with graph database concepts

To create your own node models:
1. Copy this file and rename it (e.g., user_node.py, product_node.py)
2. Modify the node label and properties
3. Import in your service layer
4. Use the Neo4j service to create/read/update/delete nodes
"""
from datetime import datetime
from typing import Optional, Dict, Any
import uuid


class ExampleNode:
    """
    Example node model for Neo4j graph database.
    
    Demonstrates:
    - UUID as node identifier
    - String properties
    - Automatic timestamps
    - Conversion to/from dictionary
    
    In Neo4j, this will be stored as:
    (:ExampleNode {id: "uuid", name: "...", description: "...", created_at: "...", updated_at: "..."})
    """
    
    # Node label in Neo4j
    LABEL = "ExampleNode"
    
    def __init__(
        self,
        name: str,
        description: Optional[str] = None,
        id: Optional[str] = None,
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None
    ):
        """
        Initialize an ExampleNode.
        
        Args:
            name: Required name field
            description: Optional description field
            id: Optional UUID (auto-generated if not provided)
            created_at: Optional creation timestamp (auto-generated if not provided)
            updated_at: Optional update timestamp
        """
        self.id = id or str(uuid.uuid4())
        self.name = name
        self.description = description
        self.created_at = created_at or datetime.utcnow().isoformat()
        self.updated_at = updated_at
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert node to dictionary for API responses.
        
        Returns:
            Dictionary representation of the node
        """
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }
    
    def to_neo4j_properties(self) -> Dict[str, Any]:
        """
        Convert node to properties dictionary for Neo4j storage.
        Excludes None values.
        
        Returns:
            Dictionary of properties to store in Neo4j
        """
        props = {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at
        }
        
        if self.description is not None:
            props["description"] = self.description
        
        if self.updated_at is not None:
            props["updated_at"] = self.updated_at
        
        return props
    
    @classmethod
    def from_neo4j_node(cls, node) -> "ExampleNode":
        """
        Create ExampleNode instance from Neo4j node.
        
        Args:
            node: Neo4j node object
            
        Returns:
            ExampleNode instance
        """
        return cls(
            id=node.get("id"),
            name=node.get("name"),
            description=node.get("description"),
            created_at=node.get("created_at"),
            updated_at=node.get("updated_at")
        )
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExampleNode":
        """
        Create ExampleNode instance from dictionary.
        
        Args:
            data: Dictionary with node data
            
        Returns:
            ExampleNode instance
        """
        return cls(
            id=data.get("id"),
            name=data["name"],
            description=data.get("description"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at")
        )
    
    def __repr__(self) -> str:
        """String representation of the node."""
        return f"<ExampleNode(id={self.id}, name={self.name})>"
