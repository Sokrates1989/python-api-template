"""
Legacy database-aware backup and restore routes.

Current app definitions do not mount these built-in backup endpoints. Backup
and restore orchestration should use the external backup-restore service
documented in ``docs/DATABASE_BACKUP.md``. This module remains only for
compatibility imports.
"""
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
    """
    Response model for restore operation start.

    Attributes:
        success (bool): Whether restore startup was accepted.
        message (str): Human-readable operation message.
        warnings (List[str] | None): Optional provider warnings.
        warning_count (int): Number of warnings returned.
    """

    success: bool
    message: str
    warnings: List[str] | None = None
    warning_count: int = 0


class RestoreStatusResponse(BaseModel):
    """
    Response model for restore operation status.

    Attributes:
        status (str): Restore status such as in_progress, completed, failed,
            none, or unsupported.
        current (int): Current progress count.
        total (int): Total progress count.
        message (str): Human-readable status message.
        warnings_count (int): Number of warnings seen during restore.
        warnings (List[str] | None): Optional warning details.
        timestamp (str | None): Provider status timestamp.
        is_locked (bool): Whether the database lock is active.
        lock_operation (str | None): Active lock operation, when present.
    """

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
    """
    Response model for provider database statistics.

    Attributes:
        database_type (str): Active database provider type.
        stats (dict): Provider-specific database statistics.
    """

    database_type: str
    stats: dict


def _delete_file_safe(path: Path) -> None:
    """
    Delete a temporary backup file when it still exists.

    Args:
        path (Path): Temporary file path to remove.

    Returns:
        None.

    Side Effects:
        Removes the file from disk when present.
    """
    if path.exists():
        path.unlink()


def _upload_suffix(service: BackupService, filename: str | None) -> str:
    """
    Return the temporary upload suffix for a restore file.

    Args:
        service (BackupService): Backup facade exposing active provider type.
        filename (str | None): Uploaded filename, when provided.

    Returns:
        str: Provider-appropriate suffix, preserving gzip extension when used.

    Side Effects:
        None.
    """
    is_gzip = bool(filename and filename.endswith(".gz"))
    base_suffix = ".cypher" if service.db_type == "neo4j" else ".sql"
    return f"{base_suffix}.gz" if is_gzip else base_suffix


def get_service() -> BackupService:
    """
    Return a database-aware backup capability service instance.

    Args:
        None.

    Returns:
        BackupService: Provider-aware backup service facade.

    Side Effects:
        Instantiates the backup service for the current request.
    """
    return BackupService()


@router.get("/download")
async def download_backup(compress: bool = True, _: str = Depends(verify_admin_key)):
    """
    Create and download a backup file when supported by the current provider.

    Args:
        compress (bool): Whether to request gzip-compressed backup output.
        _ (str): Validated admin credential from ``verify_admin_key``.

    Returns:
        FileResponse: Temporary backup file response with cleanup callback.

    Raises:
        HTTPException: HTTP 400 when unsupported and HTTP 500 when generation
            fails.

    Side Effects:
        Creates and later deletes a temporary backup file.
    """
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
    """
    Start restore from an uploaded backup file in the background.

    Args:
        background_tasks (BackgroundTasks): FastAPI background task manager.
        file (UploadFile): Uploaded backup file.
        _ (str): Validated restore credential from ``verify_restore_key``.

    Returns:
        JSONResponse: HTTP 202 response when restore startup is accepted.

    Raises:
        HTTPException: HTTP 400 when unsupported, HTTP 409 when another
            operation holds the database lock, and HTTP 500 on startup failure.

    Side Effects:
        Writes the upload to a temporary file and schedules restore execution.
    """
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
    """
    Return restore operation status when supported by the provider.

    Args:
        _ (str): Validated restore credential from ``verify_restore_key``.

    Returns:
        RestoreStatusResponse: Restore progress, unsupported status, or empty
            status when no restore is active.

    Raises:
        HTTPException: HTTP 500 when status retrieval fails.

    Side Effects:
        Reads provider restore status and database lock state.
    """
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
    """
    Return database statistics for the current provider.

    Args:
        _ (str): Validated admin credential from ``verify_admin_key``.

    Returns:
        DatabaseStatsResponse: Active provider type and statistics.

    Raises:
        HTTPException: HTTP 400 when unsupported and HTTP 500 when statistics
            retrieval fails.

    Side Effects:
        Reads provider statistics through the backup service facade.
    """
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
