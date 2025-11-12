"""API routes for Neo4j database backup and restore operations."""
from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from fastapi.responses import FileResponse
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


class DeleteResponse(BaseModel):
    """Response model for delete operation."""
    success: bool
    message: str


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
    """
    Create a Neo4j database backup.
    
    **Requires admin authentication.**
    
    Args:
        compress: Whether to compress the backup with gzip (default: True)
        use_apoc: Whether to use APOC export (requires APOC plugin, default: False)
        
    Returns:
        Backup information including filename and size
        
    Example:
        ```
        POST /backup/create?compress=true&use_apoc=false
        Headers: X-Admin-Key: your-admin-key
        ```
        
    Note:
        - Standard backup exports all nodes and relationships as Cypher CREATE statements
        - APOC backup uses the APOC plugin (if installed) for more efficient export
        - Both methods create portable Cypher scripts that can be restored
    """
    try:
        if use_apoc:
            filename, filepath = backup_service.create_backup_apoc(compress=compress)
            backup_type = "apoc"
        else:
            filename, filepath = backup_service.create_backup(compress=compress)
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
    """
    Restore Neo4j database from an existing backup file.
    
    **⚠️ WARNING: This will DELETE ALL existing data and replace it with the backup!**
    
    **Requires admin authentication.**
    
    Args:
        filename: Name of the backup file to restore from
        
    Returns:
        Restore operation result
        
    Example:
        ```
        POST /backup/restore/backup_neo4j_20241110_120000.cypher.gz
        Headers: X-Admin-Key: your-admin-key
        ```
    """
    try:
        filepath = backup_service.get_backup_path(filename)
        backup_service.restore_backup(filepath)
        
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
async def restore_from_uploaded_backup(file: UploadFile = File(...), _: str = Depends(verify_restore_key)):
    """
    Restore Neo4j database from an uploaded backup file.
    
    **⚠️ WARNING: This will DELETE ALL existing data and replace it with the backup!**
    
    **Requires admin authentication.**
    
    Args:
        file: Backup file to upload and restore from (Cypher script)
        
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
        suffix = '.cypher.gz' if file.filename.endswith('.gz') else '.cypher'
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp:
            temp_file = Path(temp.name)
            shutil.copyfileobj(file.file, temp)
        
        # Restore from temporary file
        backup_service.restore_backup(temp_file)
        
        return RestoreResponse(
            success=True,
            message=f"Neo4j database restored successfully from uploaded file: {file.filename}"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Restore failed: {str(e)}")
        
    finally:
        # Clean up temporary file
        if temp_file and temp_file.exists():
            temp_file.unlink()


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
