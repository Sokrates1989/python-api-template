# Database-Specific CRUD Examples

This template provides **database-specific CRUD examples** that demonstrate best practices for each database type.

## Overview

The template conditionally registers different example routes based on your `DB_TYPE`:

| Database Type | Routes | Model Type | Use Case |
|--------------|--------|------------|----------|
| **PostgreSQL/MySQL/SQLite** | `/examples/` | SQLAlchemy ORM | Relational data with tables |
| **Neo4j** | `/example-nodes/` | Graph nodes | Graph data with relationships |

## SQL Databases (PostgreSQL, MySQL, SQLite)

### Endpoint: `/examples/`

**Files:**
- Model: `app/models/example.py` (SQLAlchemy)
- Service: `app/backend/services/example_service.py`
- Routes: `app/api/routes/examples.py`

**Features:**
- ✅ SQLAlchemy ORM models
- ✅ Automatic migrations with Alembic
- ✅ UUID primary keys
- ✅ Automatic timestamps
- ✅ Full CRUD operations

**Example Usage:**

```bash
# Create an example
curl -X POST http://localhost:8081/examples/ \
  -H "Content-Type: application/json" \
  -d '{"name": "Test Example", "description": "Testing SQL database"}'

# List all examples
curl http://localhost:8081/examples/

# Get specific example
curl http://localhost:8081/examples/{id}

# Update example
curl -X PUT http://localhost:8081/examples/{id} \
  -H "Content-Type: application/json" \
  -d '{"name": "Updated Name"}'

# Delete example
curl -X DELETE http://localhost:8081/examples/{id}
```

**Test Script:**
```powershell
.\testing\test-crud-example.ps1
```

## Neo4j Graph Database

### Endpoint: `/example-nodes/`

**Files:**
- Model: `app/models/example_node.py` (Python class)
- Service: `app/backend/services/example_node_service.py`
- Routes: `app/api/routes/example_nodes.py`

**Features:**
- ✅ Graph database nodes
- ✅ Cypher query language
- ✅ UUID node identifiers
- ✅ Automatic timestamps
- ✅ Full CRUD operations
- ✅ Name filtering support

**Example Usage:**

```bash
# Create a node
curl -X POST http://localhost:8082/example-nodes/ \
  -H "Content-Type: application/json" \
  -d '{"name": "Test Node", "description": "Testing Neo4j"}'

# List all nodes
curl http://localhost:8082/example-nodes/

# Filter by name
curl http://localhost:8082/example-nodes/?name=Test

# Get specific node
curl http://localhost:8082/example-nodes/{id}

# Update node
curl -X PUT http://localhost:8082/example-nodes/{id} \
  -H "Content-Type: application/json" \
  -d '{"name": "Updated Node"}'

# Delete node
curl -X DELETE http://localhost:8082/example-nodes/{id}

# Delete all nodes (testing only!)
curl -X DELETE http://localhost:8082/example-nodes/
```

**Test Script:**
```powershell
.\testing\test-crud-example-nodes.ps1
```

## How It Works

### Conditional Route Registration

The `app/main.py` file conditionally registers routes based on `DB_TYPE`:

```python
# Conditionally include database-specific routers
if settings.DB_TYPE in ["postgresql", "postgres", "mysql", "sqlite"]:
    # SQL-specific routes - uses SQLAlchemy models
    from api.routes import examples
    app.include_router(examples.router)
    print(f"✅ Registered SQL-specific routes (/examples/) for {settings.DB_TYPE}")
    
elif settings.DB_TYPE == "neo4j":
    # Neo4j-specific routes - uses graph database nodes
    from api.routes import example_nodes
    app.include_router(example_nodes.router)
    print(f"✅ Registered Neo4j-specific routes (/example-nodes/) for {settings.DB_TYPE}")
```

### Startup Logs

**With PostgreSQL:**
```
✅ Registered SQL-specific routes (/examples/) for postgresql
🔄 Running database migrations...
```

**With Neo4j:**
```
✅ Registered Neo4j-specific routes (/example-nodes/) for neo4j
⚠️  Migrations skipped: DB_TYPE=neo4j (only SQL databases supported)
```

## Creating Your Own Models

### For SQL Databases

1. Copy `app/models/example.py` to `app/models/your_model.py`
2. Modify the table name and columns
3. Create a service in `app/backend/services/`
4. Create routes in `app/api/routes/`
5. Create an Alembic migration:
   ```bash
   docker compose exec app pdm run alembic revision --autogenerate -m "Add your_model table"
   ```

### For Neo4j

1. Copy `app/models/example_node.py` to `app/models/your_node.py`
2. Modify the node label and properties
3. Create a service in `app/backend/services/`
4. Create routes in `app/api/routes/`
5. No migrations needed - Neo4j is schema-free!

## API Documentation

When the application is running, visit:
- **Swagger UI**: http://localhost:8081/docs
- **ReDoc**: http://localhost:8081/redoc

The API documentation will show only the routes available for your current database type.

## Benefits of This Approach

✅ **Clean separation** - SQL and graph examples don't interfere  
✅ **No runtime errors** - Routes only registered if they'll work  
✅ **Easy to understand** - Clear examples for each database type  
✅ **Production-ready** - Proper error handling and validation  
✅ **Testable** - Dedicated test scripts for each database type  

## Switching Between Databases

To switch from PostgreSQL to Neo4j (or vice versa):

1. Update `.env`:
   ```bash
   # For PostgreSQL
   DB_TYPE=postgresql
   DB_USER=postgres
   DB_PASSWORD=postgres
   
   # For Neo4j
   DB_TYPE=neo4j
   DB_USER=neo4j
   DB_PASSWORD=neo4jpassword
   ```

2. Restart with the appropriate docker-compose file:
   ```bash
   # PostgreSQL
   docker compose -f docker/docker-compose.postgres.yml up
   
   # Neo4j
   docker compose -f docker/docker-compose.neo4j.yml up
   ```

3. The correct example routes will be automatically registered!

## Next Steps

- Explore the example code to understand the patterns
- Create your own models following the examples
- Modify the examples to fit your use case
- Remove the examples when you're ready for production

For more information, see:
- [DATABASE.md](DATABASE.md) - Database configuration guide
- [ARCHITECTURE.md](ARCHITECTURE.md) - Application architecture
