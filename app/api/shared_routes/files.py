"""Shared file inspection routes."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Query

from backend.shared_services.file_service import FileService

router = APIRouter(tags=["files"], prefix="/files")
MOUNT_PATH = Path("/mnt/data")
file_service = FileService(MOUNT_PATH)


@router.get("/list-txt-files")
def list_txt_files() -> dict:
    """List all `.txt` files in the mounted directory."""
    return file_service.list_txt_files()


@router.get("/list-extensions")
def list_extensions() -> dict:
    """List all unique file extensions in the mounted directory."""
    return file_service.list_extensions()


@router.get("/file-count")
def get_file_count() -> dict:
    """Return the total number of files in the mounted directory."""
    return file_service.get_file_count()


@router.get("/print-txt")
def print_txt_files() -> dict:
    """Read and return all `.txt` files in the mounted directory."""
    return file_service.print_txt_files()


@router.get("/list-files")
def list_files(ext: str = Query(..., description="File extension without dot, e.g., 'txt'")) -> dict:
    """List files with the requested extension."""
    return file_service.list_files_by_extension(ext)


@router.get("/print")
def print_files(ext: str = Query(..., description="File extension without dot, e.g., 'txt'")) -> dict:
    """Read and return all files with the requested extension."""
    return file_service.print_files_by_extension(ext)
