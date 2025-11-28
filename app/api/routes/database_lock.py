"""Database lock endpoints for coordinating with backup/restore operations."""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
import json
import tempfile
from pathlib import Path
import time

from api.security import verify_admin_key
from api.settings import settings


router = APIRouter(
    prefix="/database",
    tags=["database lock"]
)


class LockRequest(BaseModel):
    """Request model for database lock."""
    operation: str = "restore"


class LockResponse(BaseModel):
    """Response model for lock operations."""
    success: bool
    message: str
    is_locked: bool
    lock_operation: Optional[str] = None


# File-based lock (shared across API instances)
LOCK_DIR = Path(tempfile.gettempdir()) / "api_db_lock"
LOCK_DIR.mkdir(exist_ok=True)
LOCK_FILE = LOCK_DIR / "database.lock"
LOCK_TIMEOUT = settings.DB_LOCK_TIMEOUT_SECONDS


def _check_lock() -> Optional[str]:
    """Check if database is currently locked."""
    try:
        if not LOCK_FILE.exists():
            return None
        lock_data = json.loads(LOCK_FILE.read_text())
        lock_time = lock_data.get("timestamp", 0)
        if time.time() - lock_time >= LOCK_TIMEOUT:
            LOCK_FILE.unlink()
            return None
        return lock_data.get("operation")
    except Exception:
        return None


def _acquire_lock(operation: str) -> bool:
    """Acquire database lock."""
    try:
        if LOCK_FILE.exists():
            lock_data = json.loads(LOCK_FILE.read_text())
            lock_time = lock_data.get("timestamp", 0)
            if time.time() - lock_time < LOCK_TIMEOUT:
                return False
        lock_data = {"operation": operation, "timestamp": time.time()}
        LOCK_FILE.write_text(json.dumps(lock_data))
        return True
    except Exception:
        return False


def _release_lock():
    """Release database lock."""
    try:
        if LOCK_FILE.exists():
            LOCK_FILE.unlink()
    except Exception:
        pass


@router.post("/lock", response_model=LockResponse)
async def lock_database(
    lock_request: LockRequest,
    _: str = Depends(verify_admin_key)
):
    """
    Lock database write operations.
    
    **Requires admin authentication.**
    
    This endpoint is called by the backup-restore service to prevent
    write operations during restore operations.
    
    Args:
        lock_request: Lock request with operation name
        
    Returns:
        Lock response with success status
        
    Example:
        ```
        POST /database/lock
        Headers: X-Admin-Key: your-admin-key
        Body: {
            "operation": "restore"
        }
        ```
    """
    try:
        # Check if already locked
        current_lock = _check_lock()
        if current_lock:
            raise HTTPException(
                status_code=409,
                detail=f"Database is already locked by operation: {current_lock}"
            )
        
        # Acquire lock
        if not _acquire_lock(lock_request.operation):
            raise HTTPException(
                status_code=500,
                detail="Failed to acquire database lock"
            )
        
        return LockResponse(
            success=True,
            message=f"Database locked for operation: {lock_request.operation}",
            is_locked=True,
            lock_operation=lock_request.operation
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lock operation failed: {str(e)}")


@router.post("/unlock", response_model=LockResponse)
async def unlock_database(_: str = Depends(verify_admin_key)):
    """
    Unlock database write operations.
    
    **Requires admin authentication.**
    
    This endpoint is called by the backup-restore service to re-enable
    write operations after restore operations complete.
    
    Returns:
        Lock response with success status
        
    Example:
        ```
        POST /database/unlock
        Headers: X-Admin-Key: your-admin-key
        ```
    """
    try:
        # Release lock
        _release_lock()
        
        return LockResponse(
            success=True,
            message="Database unlocked successfully",
            is_locked=False,
            lock_operation=None
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unlock operation failed: {str(e)}")


@router.get("/lock-status", response_model=LockResponse)
async def get_lock_status(_: str = Depends(verify_admin_key)):
    """
    Get current database lock status.
    
    **Requires admin authentication.**
    
    Returns:
        Current lock status
        
    Example:
        ```
        GET /database/lock-status
        Headers: X-Admin-Key: your-admin-key
        ```
    """
    try:
        current_lock = _check_lock()
        
        return LockResponse(
            success=True,
            message="Database is locked" if current_lock else "Database is not locked",
            is_locked=bool(current_lock),
            lock_operation=current_lock
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get lock status: {str(e)}")
