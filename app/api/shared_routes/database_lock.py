"""Shared database lock routes used across backend apps."""
from __future__ import annotations

import json
import tempfile
import time
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.settings import settings
from api.shared_dependencies.security import verify_admin_key
from backend.adapters.provider_capability_factory import (
    get_provider_capabilities_for_db_type,
    normalize_provider_db_type,
)
from backend.database import get_database_handler

router = APIRouter(prefix="/database", tags=["database lock"])


class LockRequest(BaseModel):
    """Request model for database lock operations."""

    operation: str = "restore"


class LockResponse(BaseModel):
    """Response model for database lock operations."""

    success: bool
    message: str
    is_locked: bool
    lock_operation: Optional[str] = None


class ProviderInfoResponse(BaseModel):
    """Response model describing the active provider capability profile."""

    database_type: str
    provider_profile: str
    capabilities: dict[str, bool]
    is_locked: bool
    lock_operation: Optional[str] = None


LOCK_DIR = Path(tempfile.gettempdir()) / "api_db_lock"
LOCK_DIR.mkdir(exist_ok=True)
LOCK_FILE = LOCK_DIR / "database.lock"
LOCK_TIMEOUT = settings.DB_LOCK_TIMEOUT_SECONDS


def _check_lock() -> Optional[str]:
    """Return the current lock operation when a valid lock exists."""
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
    """Acquire the file-based lock for one operation."""
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


def _release_lock() -> None:
    """Release the file-based lock when it exists."""
    try:
        if LOCK_FILE.exists():
            LOCK_FILE.unlink()
    except Exception:
        pass


def _resolve_provider_info() -> tuple[str, str, dict[str, bool]]:
    """Resolve active database type and provider capabilities."""
    database_type = settings.normalized_db_type()
    try:
        handler = get_database_handler()
        handler_db_type = (getattr(handler, "db_type", "") or "").strip().lower()
        if handler_db_type:
            database_type = handler_db_type
    except Exception:
        pass

    provider_profile = normalize_provider_db_type(database_type)
    capabilities = asdict(get_provider_capabilities_for_db_type(database_type))
    return database_type, provider_profile, capabilities


@router.post("/lock", response_model=LockResponse)
async def lock_database(
    lock_request: LockRequest,
    _: str = Depends(verify_admin_key),
) -> LockResponse:
    """Lock database write operations."""
    try:
        current_lock = _check_lock()
        if current_lock:
            raise HTTPException(
                status_code=409,
                detail=f"Database is already locked by operation: {current_lock}",
            )
        if not _acquire_lock(lock_request.operation):
            raise HTTPException(status_code=500, detail="Failed to acquire database lock")
        return LockResponse(
            success=True,
            message=f"Database locked for operation: {lock_request.operation}",
            is_locked=True,
            lock_operation=lock_request.operation,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Lock operation failed: {str(exc)}")


@router.get("/provider-info", response_model=ProviderInfoResponse)
async def get_provider_info(_: str = Depends(verify_admin_key)) -> ProviderInfoResponse:
    """Return active database provider profile and capability flags."""
    try:
        database_type, provider_profile, capabilities = _resolve_provider_info()
        current_lock = _check_lock()
        return ProviderInfoResponse(
            database_type=database_type,
            provider_profile=provider_profile,
            capabilities=capabilities,
            is_locked=bool(current_lock),
            lock_operation=current_lock,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to resolve provider info: {str(exc)}")


@router.post("/unlock", response_model=LockResponse)
async def unlock_database(_: str = Depends(verify_admin_key)) -> LockResponse:
    """Unlock database write operations."""
    try:
        _release_lock()
        return LockResponse(
            success=True,
            message="Database unlocked successfully",
            is_locked=False,
            lock_operation=None,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unlock operation failed: {str(exc)}")


@router.get("/lock-status", response_model=LockResponse)
async def get_lock_status(_: str = Depends(verify_admin_key)) -> LockResponse:
    """Return the current database lock status."""
    try:
        current_lock = _check_lock()
        return LockResponse(
            success=True,
            message="Database is locked" if current_lock else "Database is not locked",
            is_locked=bool(current_lock),
            lock_operation=current_lock,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to get lock status: {str(exc)}")
