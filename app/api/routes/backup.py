"""Database-aware backup and restore routes."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

from api.security import verify_admin_key, verify_restore_key
from backend.services.backup_service import BackupService


router = APIRouter(prefix="/backup", tags=["database backup"])


class RestoreResponse(BaseModel):
    """Response model for restore operation start."""

    success: bool
    message: str
    warnings: List[str] | None = None
    warning_count: int = 0


class RestoreStatusResponse(BaseModel):
    """Response model for restore operation status."""

    status: str  # in_progress, completed, failed, none, unsupported
    current: int = 0
    total: int = 0
    message: str = ""
    warnings_count: int = 0
    warnings: List[str] | None = None
    timestamp: str | None = None
    is_locked: bool = False
    lock_operation: str | None = None


class DatabaseStatsResponse(BaseModel):
    """Response model for provider database statistics."""

    database_type: str
    stats: dict


def _delete_file_safe(path: Path) -> None:
    if path.exists():
        path.unlink()


def _upload_suffix(service: BackupService, filename: str | None) -> str:
    is_gzip = bool(filename and filename.endswith(".gz"))
    base_suffix = ".cypher" if service.db_type == "neo4j" else ".sql"
    return f"{base_suffix}.gz" if is_gzip else base_suffix


def get_service() -> BackupService:
    """Get a database-aware backup capability service instance."""
    return BackupService()


@router.get("/download")
async def download_backup(compress: bool = True, _: str = Depends(verify_admin_key)):
    """Create and download a backup file when supported by the current provider."""
    service = get_service()
    if not service.capabilities.supports_backup_download:
        raise HTTPException(
            status_code=400,
            detail=f"Backup download is not supported for database type: {service.db_type}",
        )

    temp_filepath = None
    try:
        filename, temp_filepath = await run_in_threadpool(
            service.create_backup_to_temp,
            compress,
        )
        media_type = "application/gzip" if filename.endswith(".gz") else "text/plain"
        return FileResponse(
            path=temp_filepath,
            filename=filename,
            media_type=media_type,
            background=BackgroundTask(_delete_file_safe, temp_filepath),
        )
    except Exception as exc:
        if temp_filepath and temp_filepath.exists():
            temp_filepath.unlink()
        raise HTTPException(status_code=500, detail=f"Backup download failed: {str(exc)}")


@router.post("/restore-upload", response_model=RestoreResponse)
async def restore_from_uploaded_backup(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    _: str = Depends(verify_restore_key),
):
    """Start restore from uploaded backup file in background when supported."""
    service = get_service()
    if not service.capabilities.supports_restore_upload:
        raise HTTPException(
            status_code=400,
            detail=f"Restore upload is not supported for database type: {service.db_type}",
        )

    temp_file = None
    try:
        lock_operation = service.check_operation_lock()
        if lock_operation:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot start restore: {lock_operation} operation is already in progress",
            )

        suffix = _upload_suffix(service, file.filename)
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp:
            temp_file = Path(temp.name)
            shutil.copyfileobj(file.file, temp)

        background_tasks.add_task(service.restore_backup, temp_file)
        return JSONResponse(
            status_code=202,
            content={
                "success": True,
                "message": (
                    "Restore operation started in background for file: "
                    f"{file.filename}. Use GET /backup/restore-status to monitor progress."
                ),
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        if temp_file and temp_file.exists():
            temp_file.unlink()
        raise HTTPException(status_code=500, detail=f"Failed to start restore: {str(exc)}")


@router.get("/restore-status", response_model=RestoreStatusResponse)
async def get_restore_status(_: str = Depends(verify_restore_key)):
    """Get status for restore operations when supported by the provider."""
    service = get_service()
    if not service.capabilities.supports_restore_status:
        return RestoreStatusResponse(
            status="unsupported",
            message=f"Restore status is not supported for database type: {service.db_type}",
        )

    try:
        status = service.get_restore_status()
        if status is None:
            lock_operation = service.check_operation_lock()
            return RestoreStatusResponse(
                status="none",
                message="No restore operation in progress or completed recently",
                is_locked=bool(lock_operation),
                lock_operation=lock_operation,
            )
        return RestoreStatusResponse(**status)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to get restore status: {str(exc)}")


@router.get("/stats", response_model=DatabaseStatsResponse)
async def get_database_stats(_: str = Depends(verify_admin_key)):
    """Get database statistics for the current provider."""
    service = get_service()
    if not service.capabilities.supports_stats:
        raise HTTPException(
            status_code=400,
            detail=f"Stats are not supported for database type: {service.db_type}",
        )

    try:
        stats = await service.get_database_stats()
        return DatabaseStatsResponse(database_type=service.db_type, stats=stats)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to get database stats: {str(exc)}")
