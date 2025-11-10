"""API routes for database backup and restore operations."""
from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List
from pathlib import Path
import tempfile
import shutil

from backend.services.sql.backup_service import BackupService
from api.security import verify_admin_key


router = APIRouter(
    prefix="/backup",
    tags=["Database Backup"],
    dependencies=[Depends(verify_admin_key)]  # Require admin authentication
)


# Pydantic models
class BackupResponse(BaseModel):
    """Response model for backup creation."""
    success: bool
    message: str
    filename: str
    size_mb: float


class BackupInfo(BaseModel):
    """Model for backup file information."""
    filename: str
    size_bytes: int
    size_mb: float
    created_at: str
    compressed: bool


class BackupListResponse(BaseModel):
    """Response model for listing backups."""
    backups: List[BackupInfo]
    total_count: int


class RestoreResponse(BaseModel):
    """Response model for restore operation."""
    success: bool
    message: str


class DeleteResponse(BaseModel):
    """Response model for delete operation."""
    success: bool
    message: str


# Initialize service
backup_service = BackupService()


@router.post("/create", response_model=BackupResponse)
async def create_database_backup(compress: bool = True):
    """
    Create a database backup.
    
    **Requires admin authentication.**
    
    Args:
        compress: Whether to compress the backup with gzip (default: True)
        
    Returns:
        Backup information including filename and size
        
    Example:
        ```
        POST /backup/create?compress=true
        Headers: X-Admin-Key: your-admin-key
        ```
    """
    try:
        filename, filepath = backup_service.create_backup(compress=compress)
        
        # Get file size
        size_bytes = filepath.stat().st_size
        size_mb = round(size_bytes / (1024 * 1024), 2)
        
        return BackupResponse(
            success=True,
            message=f"Backup created successfully: {filename}",
            filename=filename,
            size_mb=size_mb
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backup creation failed: {str(e)}")


@router.get("/download/{filename}")
async def download_backup(filename: str):
    """
    Download a backup file.
    
    **Requires admin authentication.**
    
    Args:
        filename: Name of the backup file to download
        
    Returns:
        The backup file for download
        
    Example:
        ```
        GET /backup/download/backup_postgresql_20241110_120000.sql.gz
        Headers: X-Admin-Key: your-admin-key
        ```
    """
    try:
        filepath = backup_service.get_backup_path(filename)
        
        # Determine media type
        media_type = "application/gzip" if filename.endswith('.gz') else "application/sql"
        
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
async def restore_from_backup(filename: str):
    """
    Restore database from an existing backup file.
    
    **⚠️ WARNING: This will overwrite the current database!**
    
    **Requires admin authentication.**
    
    Args:
        filename: Name of the backup file to restore from
        
    Returns:
        Restore operation result
        
    Example:
        ```
        POST /backup/restore/backup_postgresql_20241110_120000.sql.gz
        Headers: X-Admin-Key: your-admin-key
        ```
    """
    try:
        filepath = backup_service.get_backup_path(filename)
        backup_service.restore_backup(filepath)
        
        return RestoreResponse(
            success=True,
            message=f"Database restored successfully from: {filename}"
        )
        
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Backup file not found: {filename}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Restore failed: {str(e)}")


@router.post("/restore-upload", response_model=RestoreResponse)
async def restore_from_uploaded_backup(file: UploadFile = File(...)):
    """
    Restore database from an uploaded backup file.
    
    **⚠️ WARNING: This will overwrite the current database!**
    
    **Requires admin authentication.**
    
    Args:
        file: Backup file to upload and restore from
        
    Returns:
        Restore operation result
        
    Example:
        ```
        POST /backup/restore-upload
        Headers: X-Admin-Key: your-admin-key
        Body: multipart/form-data with file
        ```
    """
    # Create temporary file
    temp_file = None
    try:
        # Save uploaded file to temporary location
        with tempfile.NamedTemporaryFile(delete=False, suffix='.sql') as temp:
            temp_file = Path(temp.name)
            shutil.copyfileobj(file.file, temp)
        
        # Restore from temporary file
        backup_service.restore_backup(temp_file)
        
        return RestoreResponse(
            success=True,
            message=f"Database restored successfully from uploaded file: {file.filename}"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Restore failed: {str(e)}")
        
    finally:
        # Clean up temporary file
        if temp_file and temp_file.exists():
            temp_file.unlink()


@router.get("/list", response_model=BackupListResponse)
async def list_backups():
    """
    List all available backup files.
    
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
async def delete_backup(filename: str):
    """
    Delete a backup file.
    
    **Requires admin authentication.**
    
    Args:
        filename: Name of the backup file to delete
        
    Returns:
        Delete operation result
        
    Example:
        ```
        DELETE /backup/delete/backup_postgresql_20241110_120000.sql.gz
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
