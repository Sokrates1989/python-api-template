# Neo4j Database Models

This directory contains **Pydantic models** for Neo4j graph database.

## What's Here

- `example.py` - Example Pydantic model for Neo4j nodes

## Characteristics

- **Schema-free** - No migrations needed!
- **Pydantic-based** - Simple validation models
- **Flexible** - Add properties anytime without schema changes
- **Graph-native** - Perfect for relationships and connections

## Neo4j Advantages

✅ **No migrations** - Just write Cypher and go  
✅ **No rigid schema** - Add/remove properties freely  
✅ **Simple models** - Just Pydantic for API validation  
✅ **Direct queries** - Write Cypher, no ORM complexity  

## Creating Your Own Models

1. Copy `example.py` to `your_node.py`
2. Modify the Pydantic fields
3. Create a service in `backend/services/neo4j/` with Cypher queries
4. Create product route facades in `app/apps/<app_id>/routes/`, or create a
   shared route group in `app/api/shared_routes/` when the endpoint is reusable
   and explicitly opt-in
5. **No migrations needed!**

## Example

```python
from pydantic import BaseModel, Field
from typing import Optional
import uuid

class YourNode(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: Optional[str] = None
    
# That's it! No schema, no migrations, just Cypher queries in your service:
# CREATE (n:YourNode {id: $id, name: $name})
```

## Why Pydantic?

Pydantic models are used **only for API validation**. Neo4j doesn't need schema definitions - you just write Cypher queries and Neo4j handles the rest!
