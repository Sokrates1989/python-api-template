"""API routes for Neo4j database backup and restore operations."""
from fastapi import APIRouter, HTTPException, UploadFile, File, Depends, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from typing import List
from pathlib import Path
import tempfile
import shutil

from backend.services.neo4j.backup_service import Neo4jBackupService
from api.security import verify_admin_key, verify_restore_key, verify_delete_key


router = APIRouter(
    prefix="/backup",
    tags=["Neo4j Backup"]
)


# Pydantic models
class BackupResponse(BaseModel):
    """Response model for backup creation."""
    success: bool
    message: str
    filename: str
    size_mb: float
    backup_type: str


class BackupInfo(BaseModel):
    """Model for backup file information."""
    filename: str
    size_bytes: int
    size_mb: float
    created_at: str
    compressed: bool
    backup_type: str


class BackupListResponse(BaseModel):
    """Response model for listing backups."""
    backups: List[BackupInfo]
    total_count: int


class RestoreResponse(BaseModel):
    """Response model for restore operation."""
    success: bool
    message: str
    warnings: List[str] | None = None
    warning_count: int = 0


class DeleteResponse(BaseModel):
    """Response model for delete operation."""
    success: bool
    message: str


class RestoreStatusResponse(BaseModel):
    """Response model for restore operation status."""
    status: str  # in_progress, completed, failed, or none
    current: int = 0
    total: int = 0
    message: str = ""
    warnings_count: int = 0
    warnings: List[str] | None = None
    timestamp: str | None = None
    is_locked: bool = False
    lock_operation: str | None = None


class DatabaseStats(BaseModel):
    """Model for database statistics."""
    node_count: int
    relationship_count: int
    labels: List[str]
    relationship_types: List[str]


# Initialize service
backup_service = Neo4jBackupService()


@router.post("/create", response_model=BackupResponse)
async def create_database_backup(compress: bool = True, use_apoc: bool = False, _: str = Depends(verify_admin_key)):
    """Create a Neo4j database backup.

    **Requires admin authentication.**

    The heavy backup work is executed in a threadpool to avoid blocking
    the FastAPI event loop, but this endpoint still waits for completion
    and returns the backup metadata in the response.
    """
    try:
        if use_apoc:
            filename, filepath = await run_in_threadpool(
                backup_service.create_backup_apoc,
                compress=compress,
            )
            backup_type = "apoc"
        else:
            filename, filepath = await run_in_threadpool(
                backup_service.create_backup,
                compress=compress,
            )
            backup_type = "cypher"
        
        # Get file size
        size_bytes = filepath.stat().st_size
        size_mb = round(size_bytes / (1024 * 1024), 2)
        
        return BackupResponse(
            success=True,
            message=f"Neo4j backup created successfully: {filename}",
            filename=filename,
            size_mb=size_mb,
            backup_type=backup_type
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backup creation failed: {str(e)}")


@router.get("/download/{filename}")
async def download_backup(filename: str, _: str = Depends(verify_admin_key)):
    """
    Download a Neo4j backup file.
    
    **Requires admin authentication.**
    
    Args:
        filename: Name of the backup file to download
        
    Returns:
        The backup file for download
        
    Example:
        ```
        GET /backup/download/backup_neo4j_20241110_120000.cypher.gz
        Headers: X-Admin-Key: your-admin-key
        ```
    """
    try:
        filepath = backup_service.get_backup_path(filename)
        
        # Determine media type
        media_type = "application/gzip" if filename.endswith('.gz') else "text/plain"
        
        return FileResponse(
            path=filepath,
            filename=filename,
            media_type=media_type
        )
        
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Backup file not found: {filename}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")


@router.post("/restore/{filename}", response_model=RestoreResponse)
async def restore_from_backup(filename: str, _: str = Depends(verify_restore_key)):
    """Restore Neo4j database from an existing backup file.

    **⚠️ WARNING: This will DELETE ALL existing data and replace it with the backup!**

    **Requires admin authentication.**

    The restore operation itself is heavy and runs in a threadpool so the
    event loop stays responsive, but this endpoint still waits until the
    restore finishes and then returns the result.
    """
    try:
        filepath = backup_service.get_backup_path(filename)
        await run_in_threadpool(backup_service.restore_backup, filepath)
        
        return RestoreResponse(
            success=True,
            message=f"Neo4j database restored successfully from: {filename}"
        )
        
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Backup file not found: {filename}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Restore failed: {str(e)}")


@router.post("/restore-upload", response_model=RestoreResponse)
async def restore_from_uploaded_backup(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    _: str = Depends(verify_restore_key)
):
    """
    Restore Neo4j database from an uploaded backup file (runs in background).
    
    **⚠️ WARNING: This will DELETE ALL existing data and replace it with the backup!**
    
    **Requires restore authentication.**
    
    This endpoint accepts the backup file, saves it, and starts the restore
    operation in the background. It returns immediately with a 202 Accepted status.
    
    Use GET /backup/restore-status to monitor the restore progress.
    
    Args:
        file: Backup file to upload and restore from (Cypher script)
        
    Returns:
        Immediate response confirming restore has started
        
    Example:
        ```
        POST /backup/restore-upload
        Headers: X-Restore-Key: your-restore-key
        Body: multipart/form-data with file
        
        Response: 202 Accepted
        {
            "success": true,
            "message": "Restore operation started in background..."
        }
        
        Then poll: GET /backup/restore-status
        ```
        
    Security:
        - Requires X-Restore-Key header with restore API key
        - Clears all existing Neo4j data before restore
        - Use with extreme caution in production
    """
    temp_file = None
    try:
        # Check if another operation is in progress
        lock_operation = backup_service.check_operation_lock()
        if lock_operation:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot start restore: {lock_operation} operation is already in progress"
            )
        
        # Save uploaded file to temporary location
        suffix = '.cypher.gz' if file.filename and file.filename.endswith('.gz') else '.cypher'
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp:
            temp_file = Path(temp.name)
            shutil.copyfileobj(file.file, temp)
        
        # Start restore in background
        background_tasks.add_task(backup_service.restore_backup, temp_file)
        
        return JSONResponse(
            status_code=202,
            content={
                "success": True,
                "message": f"Restore operation started in background for file: {file.filename}. Use GET /backup/restore-status to monitor progress."
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        # Clean up temp file on error
        if temp_file and temp_file.exists():
            temp_file.unlink()
        raise HTTPException(status_code=500, detail=f"Failed to start restore: {str(e)}")


@router.get("/list", response_model=BackupListResponse)
async def list_backups(_: str = Depends(verify_admin_key)):
    """
    List all available Neo4j backup files.
    
    **Requires admin authentication.**
    
    Returns:
        List of backup files with metadata
        
    Example:
        ```
        GET /backup/list
        Headers: X-Admin-Key: your-admin-key
        ```
    """
    try:
        backups = backup_service.list_backups()
        
        return BackupListResponse(
            backups=[BackupInfo(**backup) for backup in backups],
            total_count=len(backups)
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list backups: {str(e)}")


@router.delete("/delete/{filename}", response_model=DeleteResponse)
async def delete_backup(filename: str, _: str = Depends(verify_delete_key)):
    """
    Delete a Neo4j backup file.
    
    **Requires admin authentication.**
    
    Args:
        filename: Name of the backup file to delete
        
    Returns:
        Delete operation result
        
    Example:
        ```
        DELETE /backup/delete/backup_neo4j_20241110_120000.cypher.gz
        Headers: X-Admin-Key: your-admin-key
        ```
    """
    try:
        backup_service.delete_backup(filename)
        
        return DeleteResponse(
            success=True,
            message=f"Backup deleted successfully: {filename}"
        )
        
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Backup file not found: {filename}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")


@router.get("/restore-status", response_model=RestoreStatusResponse)
async def get_restore_status(_: str = Depends(verify_restore_key)):
    """
    Get the current status of a restore operation.
    
    **Requires restore authentication.**
    
    Returns:
        Current restore operation status including progress, warnings, and lock status
        
    Example:
        ```
        GET /backup/restore-status
        Headers: X-Restore-Key: your-restore-key
        ```
        
    Response:
        - `status`: Operation status (in_progress, completed, failed, or none)
        - `current`: Current statement number being executed
        - `total`: Total number of statements
        - `message`: Status message
        - `warnings_count`: Number of warnings encountered
        - `warnings`: List of warning messages (if any)
        - `is_locked`: Whether backup/restore operations are currently locked
        - `lock_operation`: Name of the operation holding the lock (if any)
        
    Useful for:
        - Monitoring long-running restore operations
        - Checking if restore completed successfully
        - Detecting if another operation is blocking backup/restore
        - Viewing warnings from the most recent restore
    """
    try:
        status = backup_service.get_restore_status()
        
        if status is None:
            # No restore operation tracked
            lock_operation = backup_service.check_operation_lock()
            return RestoreStatusResponse(
                status="none",
                message="No restore operation in progress or completed recently",
                is_locked=bool(lock_operation),
                lock_operation=lock_operation
            )
        
        return RestoreStatusResponse(**status)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get restore status: {str(e)}")


@router.get("/stats", response_model=DatabaseStats)
async def get_database_stats(_: str = Depends(verify_admin_key)):
    """
    Get current Neo4j database statistics.
    
    **Requires admin authentication.**
    
    Returns:
        Database statistics including node count, relationship count, labels, and types
        
    Example:
        ```
        GET /backup/stats
        Headers: X-Admin-Key: your-admin-key
        ```
        
    Useful for:
        - Checking database size before backup
        - Verifying restore completed successfully
        - Monitoring database growth
    """
    try:
        stats = backup_service.get_database_stats()
        
        return DatabaseStats(**stats)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get database stats: {str(e)}")
