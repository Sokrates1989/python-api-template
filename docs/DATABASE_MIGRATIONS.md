# Database Migrations Guide

This template uses **Alembic** for production-ready database schema management and migrations.

## Current Multi-App Rule

The backend now has two migration scopes:

1. Global provider-wide migrations in `alembic/versions/`.
2. Selected-app migrations in `app/apps/<app_id>/migrations/versions/`.

Use the global Alembic tree only for schema that intentionally affects every
SQL app profile, such as shared users/auth tables or provider-wide sync
infrastructure. Product tables, app-owned feature tables, and selected-app data
migrations must live inside the owning app slice.

Startup applies global migrations first with the `alembic_version` table, then
applies only the selected app's declared `migration_version_locations` with an
app-specific version table such as `alembic_version_felix`.

Legacy Felix databases can contain the old global revision marker
`010_create_wellness_tables`. That marker is now a no-op compatibility revision
in the global stream; the Felix app migration stream owns the actual wellness
tables and reuses pre-existing local tables before applying later Felix schema
changes.

See also:

- `docs/APP_SLICE_BOUNDARY_GUIDE.md`
- `app/apps/README.md`

## 📋 Table of Contents

1. [Why Migrations?](#why-migrations)
2. [How It Works](#how-it-works)
3. [Automatic Migrations](#automatic-migrations)
4. [Creating New Migrations](#creating-new-migrations)
5. [Manual Migration Commands](#manual-migration-commands)
6. [Best Practices](#best-practices)
7. [Troubleshooting](#troubleshooting)

---

## Why Migrations?

### ❌ Without Migrations (Bad)
```python
# Manual table creation - NOT production ready
def create_tables():
    Base.metadata.create_all(engine)
```

**Problems:**
- ❌ No version control for schema changes
- ❌ Can't track what's deployed in production
- ❌ No way to rollback changes
- ❌ Team members have different schemas
- ❌ Manual steps required
- ❌ Can't audit schema history

### ✅ With Migrations (Good)
```bash
# Automatic, versioned, trackable
alembic upgrade head
```

**Benefits:**
- ✅ Version controlled schema changes
- ✅ Automatic on startup
- ✅ Can rollback if needed
- ✅ Team stays in sync
- ✅ Audit trail of all changes
- ✅ Production ready

---

## How It Works

### Migration Flow

```
1. Developer creates model
   └─> app/models/your_model.py

2. Generate migration
   └─> alembic revision --autogenerate -m "add your_model"
   └─> Creates: alembic/versions/002_add_your_model.py

3. Commit migration file to git
   └─> Team members get the migration

4. On startup, migrations run automatically
   └─> Database schema updated
   └─> Application ready to use
```

### File Structure

```
python-api-template/
├── alembic/                      # Migration configuration
│   ├── versions/                 # Migration files (version controlled)
│   │   ├── 001_initial_examples_table.py
│   │   └── 002_add_users_table.py
│   ├── env.py                    # Alembic environment config
│   └── script.py.mako           # Migration template
├── alembic.ini                   # Alembic configuration
└── app/
    ├── models/                   # Your SQLAlchemy models
    │   └── example.py
    └── backend/
        └── database/
            └── migrations.py     # Migration runner
```

---

## Automatic Migrations

Migrations run **automatically on application startup**. No manual steps required!

### Startup Sequence

```python
# app/api/config/lifecycle.py
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def app_lifespan(app: FastAPI):
    await initialize_database()  # 1. Connect to database
    run_migrations()             # 2. Run pending migrations
    yield
```

### What You'll See

```bash
$ docker compose up

app-1  | 🔄 Running database migrations...
app-1  | INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
app-1  | INFO  [alembic.runtime.migration] Will assume transactional DDL.
app-1  | INFO  [alembic.runtime.migration] Running upgrade  -> 001, Initial examples table
app-1  | ✅ Database migrations completed successfully
app-1  | INFO: Uvicorn running on http://0.0.0.0:8000
```

### When Migrations Run

- ✅ **First startup**: Creates all tables
- ✅ **After pulling new code**: Applies new migrations
- ✅ **Production deployment**: Automatically updates schema
- ⚠️ **Already up-to-date**: Skips (no changes)

---

## Creating New Migrations

### Method 1: Autogenerate (Recommended)

Alembic can automatically detect model changes and generate migrations.

#### Step 1: Create or Modify Your Model

```python
# app/models/user.py
from sqlalchemy import Column, String, Boolean
from models.example import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(String, primary_key=True)
    username = Column(String(100), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    is_active = Column(Boolean, default=True)
```

#### Step 2: Generate Migration

```bash
# From project root
docker compose run --rm app alembic revision --autogenerate -m "add users table"
```

Provider-wide migrations create files under `alembic/versions/`. App-owned
migrations must be created under
`app/apps/<app_id>/migrations/versions/` and declared by that app's
`BackendAppDefinition`.

#### Step 3: Review the Generated Migration

```python
# alembic/versions/002_add_users_table.py
def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('username', sa.String(length=100), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username'),
        sa.UniqueConstraint('email')
    )

def downgrade() -> None:
    op.drop_table('users')
```

#### Step 4: Commit and Push

```bash
git add alembic/versions/002_add_users_table.py
git commit -m "Add users table migration"
git push
```

#### Step 5: Restart Application

```bash
docker compose restart app
# Migration runs automatically on startup
```

### Method 2: Manual Migration

For complex changes, write migrations manually.

```bash
docker compose run --rm app alembic revision -m "add custom indexes"
```

Edit the generated file:

```python
def upgrade() -> None:
    op.create_index('idx_users_email_active', 'users', ['email', 'is_active'])
    op.execute("CREATE INDEX idx_users_username_lower ON users (LOWER(username))")

def downgrade() -> None:
    op.drop_index('idx_users_email_active', table_name='users')
    op.execute("DROP INDEX idx_users_username_lower")
```

---

## Manual Migration Commands

### Check Current Version

```bash
docker compose run --rm app alembic current
```

### View Migration History

```bash
docker compose run --rm app alembic history
```

### Upgrade to Latest

```bash
docker compose run --rm app alembic upgrade head
```

### Upgrade to Specific Version

```bash
docker compose run --rm app alembic upgrade 002
```

### Downgrade One Version

```bash
docker compose run --rm app alembic downgrade -1
```

### Downgrade to Specific Version

```bash
docker compose run --rm app alembic downgrade 001
```

### Show SQL Without Running

```bash
docker compose run --rm app alembic upgrade head --sql
```

---

## Best Practices

### 1. Always Review Autogenerated Migrations

Alembic is smart but not perfect. Always check:

```python
# ✅ Good - Alembic detected everything
def upgrade():
    op.create_table('users', ...)
    op.create_index('idx_users_email', 'users', ['email'])

# ⚠️ Check - Did Alembic miss anything?
# - Custom constraints
# - Triggers
# - Functions
# - Data migrations
```

### 2. One Migration Per Feature

```bash
# ✅ Good
alembic revision -m "add users table"
alembic revision -m "add posts table"

# ❌ Bad
alembic revision -m "add users and posts and comments and likes"
```

### 3. Test Migrations Locally First

```bash
# Test upgrade
docker compose run --rm app alembic upgrade head

# Test downgrade
docker compose run --rm app alembic downgrade -1

# Test upgrade again
docker compose run --rm app alembic upgrade head
```

### 4. Never Edit Applied Migrations

```bash
# ❌ NEVER do this if migration is already applied
# Edit: alembic/versions/001_initial.py

# ✅ Instead, create a new migration
alembic revision -m "fix users table"
```

### 5. Include Data Migrations When Needed

```python
def upgrade():
    # Schema change
    op.add_column('users', sa.Column('status', sa.String(20)))
    
    # Data migration
    op.execute("UPDATE users SET status = 'active' WHERE is_active = true")
    op.execute("UPDATE users SET status = 'inactive' WHERE is_active = false")
    
    # Remove old column
    op.drop_column('users', 'is_active')
```

### 6. Use Transactions

Migrations run in transactions by default. If something fails, everything rolls back.

```python
def upgrade():
    # All or nothing - if any step fails, all rollback
    op.create_table('users', ...)
    op.create_index('idx_users_email', ...)
    op.execute("INSERT INTO users ...")
```

---

## Troubleshooting

### Migration Failed During Startup

```bash
❌ Error running migrations: (psycopg2.errors.DuplicateTable) relation "examples" already exists
```

**Solution**: The table exists but Alembic doesn't know about it.

```bash
# Mark current state as migrated (without running)
docker compose run --rm app alembic stamp head
```

### Alembic Out of Sync

```bash
❌ Error: Can't locate revision identified by '002'
```

**Solution**: Pull latest migrations from git.

```bash
git pull
docker compose restart app
```

### Need to Reset Everything

```bash
# ⚠️ WARNING: This deletes all data!

# Drop all tables
docker compose down -v

# Restart (migrations will recreate everything)
docker compose up
```

### Autogenerate Didn't Detect Changes

**Common causes:**
1. Model not imported in `alembic/env.py`
2. Using wrong Base
3. Model file not in correct location

**Solution**: Check `alembic/env.py`:

```python
# Make sure your models are imported
from models.example import Base
from models.user import User  # Add new models here
```

### Production Deployment

For production, you might want to run migrations separately:

```bash
# Option 1: Run before starting app
docker compose run --rm app alembic upgrade head
docker compose up app

# Option 2: Let app run them automatically (default)
docker compose up
```

---

## Example Workflow

### Adding a New Feature

```bash
# 1. Create model
# Edit: app/models/product.py

# 2. Generate migration
docker compose run --rm app alembic revision --autogenerate -m "add products table"

# 3. Review migration
# Check: alembic/versions/003_add_products_table.py

# 4. Test locally
docker compose restart app
# Check logs for migration success

# 5. Commit
git add alembic/versions/003_add_products_table.py
git add app/models/product.py
git commit -m "Add products feature"

# 6. Push
git push

# 7. Deploy
# Migrations run automatically on deployment
```

---

## Summary

### Key Points

1. **Migrations run automatically** on startup
2. **Always commit** migration files to git
3. **Review autogenerated** migrations before committing
4. **Test locally** before deploying
5. **Never edit** applied migrations
6. **One migration** per logical change

### Quick Reference

```bash
# Generate new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback one version
alembic downgrade -1

# Check current version
alembic current

# View history
alembic history
```

---

## Next Steps

- Read [CRUD_EXAMPLE.md](./CRUD_EXAMPLE.md) for model examples
- See [DATABASE.md](./DATABASE.md) for database configuration
- Check [ARCHITECTURE.md](./ARCHITECTURE.md) for project structure
