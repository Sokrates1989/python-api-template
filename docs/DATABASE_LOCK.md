# Database Lock Coordination

This document explains the database locking mechanism that allows external backup/restore services to coordinate with your API.

## Overview

The API now provides endpoints for external services (like the `backup-restore` service) to lock write operations during critical database operations such as restores.

## How It Works

1. **External Service Initiates Lock**: Before starting a restore operation, the backup-restore service calls `POST /database/lock`
2. **API Blocks Writes**: While locked, all write operations (POST, PUT, PATCH, DELETE) return 503 errors
3. **Read Operations Continue**: GET requests are still allowed during the lock
4. **External Service Releases Lock**: After the restore completes, the service calls `POST /database/unlock`

## Endpoints

### Lock Database

```http
POST /database/lock
Headers: X-Admin-Key: your-admin-key
Body: {
  "operation": "restore"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Database locked for operation: restore",
  "is_locked": true,
  "lock_operation": "restore"
}
```

### Unlock Database

```http
POST /database/unlock
Headers: X-Admin-Key: your-admin-key
```

**Response:**
```json
{
  "success": true,
  "message": "Database unlocked successfully",
  "is_locked": false,
  "lock_operation": null
}
```

### Check Lock Status

```http
GET /database/lock-status
Headers: X-Admin-Key: your-admin-key
```

**Response:**
```json
{
  "success": true,
  "message": "Database is locked",
  "is_locked": true,
  "lock_operation": "restore"
}
```

## Middleware Behavior

When the database is locked:

- **Allowed Requests**:
  - All GET requests (read-only operations)
  - Requests to `/database/*` endpoints (lock management)
  - Requests to `/health` and `/version`
  - Requests to `/cache/*` (Redis operations)

- **Blocked Requests**:
  - POST, PUT, PATCH, DELETE to any other endpoint
  - Returns 503 Service Unavailable with details about the lock

**Example Error Response:**
```json
{
  "error": "Service temporarily unavailable",
  "detail": "Database is locked for restore operation. Write operations are blocked to prevent data corruption.",
  "operation_in_progress": "restore",
  "database_type": "postgresql",
  "retry_after": "Poll GET /database/lock-status to check lock status"
}
```

## Security

- **Requires Admin Authentication**: All lock endpoints require the `X-Admin-Key` header
- **File-Based Lock**: Uses a file-based locking mechanism shared across API instances
- **Timeout Protection**: Locks automatically expire after 2 hours (7200 seconds)
- **Fail-Open**: If the lock check fails, requests are allowed to proceed

## Usage with backup-restore Service

The `backup-restore` service automatically manages database locks when you provide:

1. `target_api_url`: URL of the API to lock (e.g., `http://localhost:8000`)
2. `target_api_key`: Admin API key for the target API

Example restore with automatic locking:

```bash
curl -X POST "http://backup-service:8000/backup/sql/restore-upload" \
  -H "X-Restore-Key: restore-key" \
  -F "file=@backup.sql.gz" \
  -F "db_type=postgresql" \
  -F "db_host=production-db" \
  -F "db_port=5432" \
  -F "db_name=mydb" \
  -F "db_user=postgres" \
  -F "db_password=password" \
  -F "target_api_url=http://production-api:8000" \
  -F "target_api_key=admin-key"
```

The backup-restore service will:
1. Lock the target API before starting the restore
2. Perform the database restore
3. Automatically unlock the API when complete (even if restore fails)

## Removed: Built-in Backup/Restore

**⚠️ Important Change**: The built-in backup/restore endpoints have been removed from this template.

- **Before**: `/backup/download`, `/backup/restore-upload` were part of this API
- **Now**: Use the standalone `backup-restore` service for all backup/restore operations

**Benefits**:
- Centralized backup management across multiple applications
- No coupling between backup logic and application logic
- Ability to backup/restore any database without deploying application code
- Better separation of concerns

## Lock File Location

The lock is stored at:
```
/tmp/api_db_lock/database.lock  (Linux/Mac)
C:\Users\<user>\AppData\Local\Temp\api_db_lock\database.lock  (Windows)
```

## Troubleshooting

### Lock is Stuck

If a lock remains after a failed restore operation:

1. **Check lock status**:
   ```bash
   curl -X GET "http://localhost:8000/database/lock-status" \
     -H "X-Admin-Key: your-admin-key"
   ```

2. **Manually unlock**:
   ```bash
   curl -X POST "http://localhost:8000/database/unlock" \
     -H "X-Admin-Key: your-admin-key"
   ```

3. **Wait for timeout**: Locks automatically expire after 2 hours

### Lock Check Fails

If the middleware can't check the lock status, it fails open (allows requests) to prevent blocking normal operations. Check logs for warnings:

```
Warning: Failed to check database lock: <error message>
```

## See Also

- [backup-restore Service README](../../backup-restore/README.md)
- [API Security Documentation](./API_SECURITY.md)
