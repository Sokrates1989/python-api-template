# SQL Database Models

This directory contains **SQLAlchemy ORM models** for SQL databases (PostgreSQL, MySQL, SQLite).

## What's Here

- `example.py` - Example SQLAlchemy model demonstrating CRUD operations
- `example_sql_models.py` - Additional SQL model examples

## Characteristics

- **ORM-based** - Uses SQLAlchemy declarative models
- **Schema-driven** - Requires migrations for schema changes
- **Type-safe** - Column types enforced at database level
- **Relational** - Supports foreign keys, joins, relationships

## Creating Your Own Models

1. Copy `example.py` to `your_model.py`
2. Modify the `__tablename__` and columns
3. Create a migration:
   ```bash
   docker compose exec app pdm run alembic revision --autogenerate -m "Add your_model table"
   ```
4. Create provider-specific reusable service code in `backend/services/sql/`
   only when the behavior is product-neutral.
5. Create product route facades in `app/apps/<app_id>/routes/`, or create a
   shared route group in `app/api/shared_routes/` when the endpoint is reusable
   and explicitly opt-in.

## Example

```python
from sqlalchemy import Column, String, Integer
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class YourModel(Base):
    __tablename__ = "your_table"
    
    id = Column(String, primary_key=True)
    name = Column(String(255), nullable=False)
    count = Column(Integer, default=0)
```
