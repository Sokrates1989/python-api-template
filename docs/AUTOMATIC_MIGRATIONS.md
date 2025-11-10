# Automatic Migrations on Startup

## Overview

This template **automatically runs database migrations** when the application starts. This ensures your database schema is always up to date without manual intervention.

## How It Works

### 1. **Startup Sequence**

```python
# app/main.py
@app.on_event("startup")
async def startup_event():
    """Initialize database and run migrations on startup."""
    
    # Step 1: Initialize database connection
    await init_database()
    
    # Step 2: Run migrations automatically (SQL databases only)
    from backend.database.migrations import run_migrations
    run_migrations()
```

### 2. **What Gets Executed**

✅ **Only SQL databases** - PostgreSQL, MySQL, SQLite  
✅ **Only pending migrations** - Never re-runs completed migrations  
✅ **In order** - Follows the revision chain  
✅ **With verification** - Shows current version, pending migrations, and final version  

❌ **Neo4j skipped** - Schema-free, no migrations needed!

### 3. **Output Examples**

#### Scenario A: Pending Migrations

```
🔄 Checking migration status...
📍 Current database version: 001_initial_...
🔄 Running 2 pending migration(s)...
   ⏩ 002_add_categ - Add categories table
   ⏩ 003_add_prio - Add priority column to examples
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade 001 -> 002, Add categories table
INFO  [alembic.runtime.migration] Running upgrade 002 -> 003, Add priority column
✅ Migrations completed successfully!
📍 New database version: 003_add_prio...
```

**What happened:**
- Started at version `001`
- Applied `002` and `003`
- Now at version `003`

#### Scenario B: Up to Date

```
🔄 Checking migration status...
📍 Current database version: 003_add_prio...
✅ Database is up to date - no migrations needed
```

**What happened:**
- Database already at latest version
- No migrations needed
- Application starts immediately

#### Scenario C: Fresh Database

```
🔄 Checking migration status...
📍 Database not initialized (no migrations applied yet)
🔄 Running 3 pending migration(s)...
   ⏩ 001_initial_ - Initial examples table
   ⏩ 002_add_categ - Add categories table
   ⏩ 003_add_prio - Add priority column to examples
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 001, Initial examples table
INFO  [alembic.runtime.migration] Running upgrade 001 -> 002, Add categories table
INFO  [alembic.runtime.migration] Running upgrade 002 -> 003, Add priority column
✅ Migrations completed successfully!
📍 New database version: 003_add_prio...
```

**What happened:**
- No migrations applied yet
- Applied all 3 migrations in order
- Database fully initialized

#### Scenario D: Neo4j Database

```
⚠️  Migrations skipped: DB_TYPE=neo4j (only SQL databases supported)
```

**What happened:**
- Neo4j detected
- Migrations skipped (not needed for schema-free database)
- Application continues normally

#### Scenario E: Migration Error

```
🔄 Checking migration status...
📍 Current database version: 001_initial_...
🔄 Running 2 pending migration(s)...
   ⏩ 002_add_categ - Add categories table
   ⏩ 003_add_prio - Add priority column to examples
❌ Error running migrations: column "priority" already exists
   The application will continue, but database schema may be outdated.
   Please run migrations manually: alembic upgrade head
```

**What happened:**
- Migration failed (e.g., schema conflict)
- Application continues running (doesn't crash)
- Manual intervention needed

---

## Benefits

### ✅ **Zero Manual Steps**

No need to remember to run migrations:

```bash
# ❌ Without auto-migrations (manual)
docker compose up -d
docker compose exec app alembic upgrade head  # Easy to forget!
```

```bash
# ✅ With auto-migrations (automatic)
docker compose up -d  # Done! Migrations run automatically
```

### ✅ **Always Up to Date**

Every time the app starts, the database schema is verified and updated if needed.

### ✅ **Safe for Production**

- Only runs pending migrations
- Never re-runs completed migrations
- Transactional (rolls back on error)
- Detailed logging for debugging

### ✅ **Developer Friendly**

Clear output shows:
- Current version
- What migrations will run
- Progress during execution
- Final version

### ✅ **Team Coordination**

When a teammate adds a migration:

1. They commit the migration file
2. You pull the changes
3. You restart the app
4. **Migrations run automatically** ✨

No communication needed about "remember to run migrations!"

---

## When Migrations Run

### ✅ **Always Run On:**

- Application startup
- Container restart
- `docker compose up`
- `docker compose restart app`

### ❌ **Never Run On:**

- Hot reload (code changes during development)
- API requests
- Background tasks
- Manual database connections

---

## Verification

### Check Current Version

The startup log shows:

```
📍 Current database version: 003_add_prio...
```

Or manually:

```bash
docker compose exec app pdm run alembic current
```

### Check Migration History

```bash
docker compose exec app pdm run alembic history
```

Output:
```
001 -> 002 (head), Add categories table
<base> -> 001, Initial examples table
```

### Verify Schema

Connect to database and check tables:

```bash
# PostgreSQL
docker compose exec postgres psql -U postgres -d apidb -c "\dt"

# Or use a GUI tool like pgAdmin, DBeaver, etc.
```

---

## Disabling Automatic Migrations

If you prefer manual control, comment out the migration call:

```python
# app/main.py
@app.on_event("startup")
async def startup_event():
    """Initialize database on startup."""
    await init_database()
    
    # Disable automatic migrations
    # from backend.database.migrations import run_migrations
    # run_migrations()
```

Then run migrations manually:

```bash
docker compose exec app pdm run alembic upgrade head
```

---

## Troubleshooting

### "Error running migrations: No module named 'models.example'"

**Cause:** Import path in `alembic/env.py` is incorrect

**Fix:**
```python
# alembic/env.py
from models.sql.example import Base  # ✅ Correct path
```

### "Database is not up to date"

**Cause:** Migration files exist that haven't been applied

**Fix:** Restart the application - migrations will run automatically

Or manually:
```bash
docker compose exec app pdm run alembic upgrade head
```

### "Migration failed: column already exists"

**Cause:** Database schema doesn't match migration expectations

**Possible causes:**
1. Manual schema changes
2. Failed previous migration
3. Inconsistent migration state

**Fix:**
```bash
# Check current version
docker compose exec app pdm run alembic current

# Check what Alembic thinks should exist
docker compose exec app pdm run alembic history

# If needed, stamp database with correct version
docker compose exec app pdm run alembic stamp head
```

### "Migrations skipped: DB_TYPE=neo4j"

**This is normal!** Neo4j doesn't need migrations.

---

## Best Practices

### 1. **Always Test Locally First**

Before committing a migration:

```bash
# Create migration
docker compose exec app pdm run alembic revision --autogenerate -m "Add field"

# Review the generated file
cat alembic/versions/xxx_add_field.py

# Test it
docker compose restart app  # Migrations run automatically

# Verify it worked
docker compose exec app pdm run alembic current
```

### 2. **Commit Migration Files**

Always commit migration files to version control:

```bash
git add alembic/versions/xxx_add_field.py
git commit -m "Add field to examples table"
```

### 3. **Never Edit Applied Migrations**

Once a migration has been applied (especially in production), **never edit it**.

Create a new migration instead:

```bash
# ❌ Don't edit 003_add_priority.py
# ✅ Create new migration
alembic revision -m "Fix priority column"
```

### 4. **Monitor Startup Logs**

Always check startup logs to verify migrations ran successfully:

```bash
docker compose logs app | grep -A 10 "Checking migration status"
```

### 5. **Backup Before Production Migrations**

Always backup production database before deploying new migrations:

```bash
# PostgreSQL backup
pg_dump -U user -d database > backup_$(date +%Y%m%d_%H%M%S).sql
```

---

## Comparison: Manual vs Automatic

| Aspect | Manual Migrations | Automatic Migrations (This Template) |
|--------|-------------------|--------------------------------------|
| **Startup** | Start app, then run migrations | Migrations run on startup |
| **Forgetting** | Easy to forget | Impossible to forget |
| **Team sync** | Requires communication | Automatic |
| **Production** | Extra deployment step | Handled automatically |
| **Verification** | Manual check needed | Logged on every startup |
| **Safety** | Same (transactional) | Same (transactional) |
| **Control** | Full manual control | Automatic with manual override |

---

## Summary

✅ **Migrations run automatically** on every application startup  
✅ **Only pending migrations** are executed  
✅ **Detailed logging** shows what's happening  
✅ **Safe and transactional** - rolls back on error  
✅ **Works with SQL databases** - PostgreSQL, MySQL, SQLite  
✅ **Skips Neo4j** - schema-free, no migrations needed  
✅ **Production-ready** - used in real applications  

**Key Benefit:** You never have to remember to run migrations manually!

For more information:
- [How Migrations Work](HOW_MIGRATIONS_WORK.md) - Deep dive into Alembic
- [Migration Guide](MIGRATION_GUIDE.md) - Creating and managing migrations
- [Alembic Documentation](https://alembic.sqlalchemy.org/)
