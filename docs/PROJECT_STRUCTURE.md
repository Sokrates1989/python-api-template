# Project Structure Guide

Clear explanation of the project structure and how everything fits together.

## Directory Structure

```
python-api-template/
├── app/                              # Application code
│   ├── api/                          # 🌐 API Layer (HTTP)
│   │   ├── routes/                   # Route handlers
│   │   │   ├── __init__.py
│   │   │   ├── test.py              # Database test endpoints
│   │   │   ├── files.py             # File operation endpoints
│   │   │   └── [your_route].py      # Your new endpoints here
│   │   ├── schemas/                  # Request/response Pydantic models
│   │   │   ├── sql/                 # SQL-specific schemas
│   │   │   └── neo4j/               # Neo4j-specific schemas
│   │   └── settings.py              # Configuration management
│   │
│   ├── backend/                      # 🔧 Backend Layer (Business Logic)
│   │   ├── database/                 # Database abstraction
│   │   │   ├── __init__.py
│   │   │   ├── base.py              # Abstract interface
│   │   │   ├── factory.py           # Database factory
│   │   │   ├── neo4j_handler.py     # Neo4j implementation
│   │   │   ├── sql_handler.py       # SQL implementation
│   │   │   ├── init_db.py           # Initialization
│   │   │   └── queries.py           # Query helpers
│   │   │
│   │   └── services/                 # Business logic services
│   │       ├── __init__.py
│   │       ├── database_service.py  # Database operations
│   │       ├── file_service.py      # File operations
│   │       └── [your_service].py    # Your new services here
│   │
│   ├── models/                       # 📊 Data Models
│   │   ├── __init__.py
│   │   └── sql/example_sql_models.py    # SQLAlchemy models
│   │
│   ├── mounted_data/                 # Example data
│   └── main.py                       # 🚀 Application entry point
│
├── docs/                             # 📚 Documentation
│   ├── QUICK_START.md               # Quick start guide
│   ├── HOW_TO_ADD_ENDPOINT.md       # How to add endpoints
│   ├── DATABASE.md                  # Database guide
│   ├── ARCHITECTURE.md              # Architecture overview
│   ├── PROJECT_STRUCTURE.md         # This file
│   └── README-DE.md                 # German documentation
│
├── .env.template                     # Environment template
├── docker-compose.yml                # Docker configuration
├── Dockerfile                        # Docker build
├── pyproject.toml                    # Dependencies
└── README.md                         # Main documentation
```

## Layer Responsibilities

### 🌐 API Layer (`app/api/`)

**Purpose:** Handle HTTP requests and responses

**Contains:**
- Route handlers (`routes/`)
- Configuration (`settings.py`)

**Responsibilities:**
- Define HTTP endpoints
- Parse request parameters
- Return HTTP responses
- Input validation

**Example:**
```python
# app/api/routes/users.py
@router.get("/users/{user_id}")
def get_user(user_id: int):
    return user_service.get_user_by_id(user_id)
```

### 🔧 Backend Layer (`app/backend/`)

**Purpose:** Business logic and data operations

**Contains:**
- Database handlers (`database/`)
- Business services (`services/`)

**Responsibilities:**
- Business logic
- Data processing
- Database operations
- External API calls

**Example:**
```python
# app/backend/services/user_service.py
def get_user_by_id(self, user_id: int):
    # Business logic here
    return {"user": {...}}
```

### 📊 Models Layer (`app/models/`)

**Purpose:** Data structure definitions

**Contains:**
- SQLAlchemy models (for SQL databases)
- Pydantic schemas (for validation)

**Responsibilities:**
- Define data structures
- Database schema (ORM)
- Data validation

## Request Flow

```
1. HTTP Request
   ↓
2. FastAPI Router (app/api/routes/)
   ↓
3. Route Handler
   ↓
4. Service (app/backend/services/)
   ↓
5. Database Handler (app/backend/database/)
   ↓
6. Database (Neo4j or SQL)
   ↓
7. Response flows back up
```

## Adding New Features

### Scenario 1: Add New Endpoint (No Database)

**Example:** Add a calculator endpoint

1. **Create Service:** `app/backend/services/calculator_service.py`
   ```python
   class CalculatorService:
       def add(self, a: int, b: int):
           return {"result": a + b}
   ```

2. **Create Route:** `app/api/routes/calculator.py`
   ```python
   from backend.services.calculator_service import CalculatorService
   
   calculator_service = CalculatorService()
   
   @router.get("/add")
   def add(a: int, b: int):
       return calculator_service.add(a, b)
   ```

3. **Register:** In `app/main.py`
   ```python
   from api.routes import calculator
   app.include_router(calculator.router)
   ```

### Scenario 2: Add Endpoint with Database

**Example:** Add a users endpoint

1. **Create Service:** `app/backend/services/user_service.py`
   ```python
   from backend.services.database_service import DatabaseService
   
   class UserService:
       def __init__(self):
           self.db = DatabaseService()
       
       async def get_users(self):
           # Database automatically uses Neo4j or SQL
           return await self.db.execute_sample_query()
   ```

2. **Create Route:** `app/api/routes/users.py`
   ```python
   from backend.services.user_service import UserService
   
   user_service = UserService()
   
   @router.get("/users")
   async def get_users():
       return await user_service.get_users()
   ```

3. **Register:** In `app/main.py`
   ```python
   from api.routes import users
   app.include_router(users.router)
   ```

## Database Layer

The database layer automatically handles Neo4j vs SQL based on `.env` configuration.

### Configuration

```bash
# .env
DB_TYPE=neo4j  # official: neo4j, postgresql/postgres, mongodb
```

### Usage in Services

```python
from backend.services.database_service import DatabaseService

class YourService:
    def __init__(self):
        self.db = DatabaseService()
    
    async def your_method(self):
        # Works with both Neo4j and SQL
        result = await self.db.test_connection()
        return result
```

### How It Works

```
Your Service
    ↓
DatabaseService (app/backend/services/database_service.py)
    ↓
DatabaseFactory (app/backend/database/factory.py)
    ↓
    ├─→ Neo4jHandler (if DB_TYPE=neo4j)
    └─→ SQLHandler (if DB_TYPE=postgresql/postgres)
```

## File Organization Best Practices

### ✅ DO

```
app/
├── api/routes/
│   ├── users.py          # User endpoints
│   ├── products.py       # Product endpoints
│   └── orders.py         # Order endpoints
│
└── backend/services/
    ├── user_service.py   # User business logic
    ├── product_service.py # Product business logic
    └── order_service.py  # Order business logic
```

### ❌ DON'T

```
app/
├── api/routes/
│   └── everything.py     # All endpoints in one file
│
└── backend/
    └── logic.py          # All logic in one file
```

## Common Patterns

### Pattern 1: Simple CRUD

```python
# Service
class UserService:
    async def create_user(self, data): pass
    async def get_user(self, user_id): pass
    async def update_user(self, user_id, data): pass
    async def delete_user(self, user_id): pass

# Route
@router.post("/users")
async def create_user(data: UserCreate):
    return await user_service.create_user(data)
```

### Pattern 2: With Validation

```python
# Service
class ProductService:
    def validate_price(self, price: float):
        if price < 0:
            raise ValueError("Price cannot be negative")
        return True
    
    def create_product(self, data):
        self.validate_price(data["price"])
        # Create product

# Route
@router.post("/products")
def create_product(data: ProductCreate):
    try:
        return product_service.create_product(data)
    except ValueError as e:
        return {"error": str(e)}
```

### Pattern 3: With Database

```python
# Service
class OrderService:
    def __init__(self):
        self.db = DatabaseService()
    
    async def get_orders(self):
        # Automatically uses correct database
        return await self.db.execute_sample_query()

# Route
@router.get("/orders")
async def get_orders():
    return await order_service.get_orders()
```

## Testing Structure

```
tests/
├── api/                  # Test routes
│   ├── test_users.py
│   └── test_products.py
│
├── backend/              # Test services
│   ├── test_user_service.py
│   └── test_product_service.py
│
└── database/             # Test database
    ├── test_neo4j.py
    └── test_sql.py
```

## Configuration Files

### `.env` - Environment Configuration

```bash
# Database
DB_TYPE=neo4j  # official: neo4j, postgresql/postgres, mongodb
NEO4J_URL=bolt://localhost:7687
DB_USER=neo4j
DB_PASSWORD=password

# API
PORT=8000
DEBUG=true
```

### `pyproject.toml` - Dependencies

```toml
[project]
dependencies = [
    "fastapi>=0.111.0",
    "neo4j>=5.22.0",
    "sqlalchemy>=2.0.25",
    # ...
]
```

## Summary

### Clear Separation

- **Routes** (`app/api/routes/`): HTTP only
- **Services** (`app/backend/services/`): Business logic
- **Database** (`app/backend/database/`): Data access

### Easy to Extend

1. Add service in `backend/services/`
2. Add route in `api/routes/`
3. Register in `main.py`

### Database Agnostic

- Configure once in `.env`
- Works with Neo4j or SQL
- No code changes needed

### Well Documented

- `docs/HOW_TO_ADD_ENDPOINT.md` - Step-by-step guide
- `docs/DATABASE.md` - Database configuration
- `docs/ARCHITECTURE.md` - Architecture details

This structure makes it easy to understand, maintain, and extend your application!
