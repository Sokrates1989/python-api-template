"""
Service layer for ExampleNode CRUD operations with Neo4j.

This service demonstrates:
1. Creating nodes in Neo4j
2. Reading nodes with filtering and pagination
3. Updating node properties
4. Deleting nodes
5. Proper error handling

To create your own Neo4j services:
1. Copy this file and rename it
2. Modify the node model and Cypher queries
3. Import in your routes
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
from models.example_node import ExampleNode
from backend.database import get_database_handler


class ExampleNodeService:
    """
    Service for managing ExampleNode instances in Neo4j.
    
    Provides CRUD operations:
    - create(): Create a new node
    - get_by_id(): Retrieve a single node by ID
    - get_all(): List nodes with pagination
    - update(): Update node properties
    - delete(): Remove a node
    """
    
    def __init__(self):
        """Initialize the service with Neo4j database handler."""
        handler = get_database_handler()
        
        # Verify we're using Neo4j
        if handler.db_type != "neo4j":
            raise RuntimeError("ExampleNodeService requires Neo4j database")
        
        self.handler = handler
    
    def create(self, name: str, description: Optional[str] = None) -> ExampleNode:
        """
        Create a new ExampleNode in Neo4j.
        
        Args:
            name: Node name (required)
            description: Node description (optional)
            
        Returns:
            Created ExampleNode instance
            
        Raises:
            Exception: If creation fails
        """
        # Create node instance
        node = ExampleNode(name=name, description=description)
        
        # Cypher query to create node
        query = f"""
        CREATE (n:{ExampleNode.LABEL} $props)
        RETURN n
        """
        
        # Execute query
        with self.handler.driver.session() as session:
            result = session.run(query, props=node.to_neo4j_properties())
            record = result.single()
            
            if not record:
                raise Exception("Failed to create node")
            
            return ExampleNode.from_neo4j_node(record["n"])
    
    def get_by_id(self, node_id: str) -> Optional[ExampleNode]:
        """
        Retrieve an ExampleNode by ID.
        
        Args:
            node_id: UUID of the node
            
        Returns:
            ExampleNode if found, None otherwise
        """
        query = f"""
        MATCH (n:{ExampleNode.LABEL} {{id: $id}})
        RETURN n
        """
        
        with self.handler.driver.session() as session:
            result = session.run(query, id=node_id)
            record = result.single()
            
            if not record:
                return None
            
            return ExampleNode.from_neo4j_node(record["n"])
    
    def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        name_filter: Optional[str] = None
    ) -> List[ExampleNode]:
        """
        Retrieve all ExampleNodes with optional filtering and pagination.
        
        Args:
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return
            name_filter: Optional filter for name (case-insensitive contains)
            
        Returns:
            List of ExampleNode instances
        """
        # Build query with optional filter
        if name_filter:
            query = f"""
            MATCH (n:{ExampleNode.LABEL})
            WHERE toLower(n.name) CONTAINS toLower($name_filter)
            RETURN n
            ORDER BY n.created_at DESC
            SKIP $skip
            LIMIT $limit
            """
            params = {"skip": skip, "limit": limit, "name_filter": name_filter}
        else:
            query = f"""
            MATCH (n:{ExampleNode.LABEL})
            RETURN n
            ORDER BY n.created_at DESC
            SKIP $skip
            LIMIT $limit
            """
            params = {"skip": skip, "limit": limit}
        
        with self.handler.driver.session() as session:
            result = session.run(query, **params)
            return [ExampleNode.from_neo4j_node(record["n"]) for record in result]
    
    def count(self, name_filter: Optional[str] = None) -> int:
        """
        Count total number of ExampleNodes.
        
        Args:
            name_filter: Optional filter for name (case-insensitive contains)
            
        Returns:
            Total count of nodes
        """
        if name_filter:
            query = f"""
            MATCH (n:{ExampleNode.LABEL})
            WHERE toLower(n.name) CONTAINS toLower($name_filter)
            RETURN count(n) as count
            """
            params = {"name_filter": name_filter}
        else:
            query = f"""
            MATCH (n:{ExampleNode.LABEL})
            RETURN count(n) as count
            """
            params = {}
        
        with self.handler.driver.session() as session:
            result = session.run(query, **params)
            record = result.single()
            return record["count"] if record else 0
    
    def update(
        self,
        node_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None
    ) -> Optional[ExampleNode]:
        """
        Update an ExampleNode's properties.
        
        Args:
            node_id: UUID of the node to update
            name: New name (optional)
            description: New description (optional)
            
        Returns:
            Updated ExampleNode if found, None otherwise
        """
        # Build update properties
        updates = {"updated_at": datetime.utcnow().isoformat()}
        
        if name is not None:
            updates["name"] = name
        
        if description is not None:
            updates["description"] = description
        
        # Cypher query to update node
        query = f"""
        MATCH (n:{ExampleNode.LABEL} {{id: $id}})
        SET n += $updates
        RETURN n
        """
        
        with self.handler.driver.session() as session:
            result = session.run(query, id=node_id, updates=updates)
            record = result.single()
            
            if not record:
                return None
            
            return ExampleNode.from_neo4j_node(record["n"])
    
    def delete(self, node_id: str) -> bool:
        """
        Delete an ExampleNode.
        
        Args:
            node_id: UUID of the node to delete
            
        Returns:
            True if deleted, False if not found
        """
        query = f"""
        MATCH (n:{ExampleNode.LABEL} {{id: $id}})
        DELETE n
        RETURN count(n) as deleted
        """
        
        with self.handler.driver.session() as session:
            result = session.run(query, id=node_id)
            record = result.single()
            return record["deleted"] > 0 if record else False
    
    def delete_all(self) -> int:
        """
        Delete all ExampleNodes (use with caution!).
        
        Returns:
            Number of nodes deleted
        """
        query = f"""
        MATCH (n:{ExampleNode.LABEL})
        DELETE n
        RETURN count(n) as deleted
        """
        
        with self.handler.driver.session() as session:
            result = session.run(query)
            record = result.single()
            return record["deleted"] if record else 0
