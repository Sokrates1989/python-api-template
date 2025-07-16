"""
📁 files.py

This module provides endpoints for interacting with files in a mounted volume directory.
It allows clients to list `.txt` files, print their contents, list all available file
extensions, and dynamically access files by any given extension.

Mounted directory: /mnt/data
"""

from fastapi import APIRouter, Query
from pathlib import Path

router = APIRouter(tags=["files"], prefix="/files")

MOUNT_PATH = Path("/mnt/data")



@router.get("/list-txt-files")
def list_txt_files():
    """
    List all `.txt` files in the mounted directory.

    Returns:
        JSON object with a list of `.txt` filenames.
    """
    if not MOUNT_PATH.exists():
        return {"error": f"Mount path {MOUNT_PATH} does not exist"}

    txt_files = [
        f.name for f in MOUNT_PATH.glob("*.txt") if f.is_file()
    ]
    return {"txt_files": txt_files}



@router.get("/list-extensions")
def list_extensions():
    """
    List all unique file extensions present in the mounted directory.

    Returns:
        JSON object with a sorted list of unique file extensions (e.g., `.txt`, `.py`).
    """
    if not MOUNT_PATH.exists():
        return {"error": f"Mount path {MOUNT_PATH} does not exist"}

    extensions = {
        f.suffix for f in MOUNT_PATH.iterdir() if f.is_file() and f.suffix
    }
    return {"extensions": sorted(extensions)}





@router.get("/print-txt")
def print_txt_files():
    """
    Read and return the contents of all `.txt` files in the mounted directory.

    Returns:
        JSON object mapping each `.txt` filename to its content.
    """
    if not MOUNT_PATH.exists():
        return {"error": f"Mount path {MOUNT_PATH} does not exist"}

    result = {}
    for f in MOUNT_PATH.glob("*.txt"):
        if f.is_file():
            try:
                result[f.name] = f.read_text(encoding="utf-8")
            except Exception as e:
                result[f.name] = f"<error reading file: {e}>"

    return result


@router.get("/list-files")
def list_files(ext: str = Query(..., description="File extension without dot, e.g., 'txt'")):
    """
    List all files in the mounted directory with the specified extension.

    Args:
        ext: File extension (without the leading dot), e.g., 'txt', 'json', 'py'.

    Returns:
        JSON object with the requested extension and a list of matching filenames.
    """
    if not MOUNT_PATH.exists():
        return {"error": f"Mount path {MOUNT_PATH} does not exist"}

    ext = ext.lower().strip().lstrip(".")  # Normalize
    files = [
        f.name for f in MOUNT_PATH.glob(f"*.{ext}") if f.is_file()
    ]
    return {"extension": ext, "files": files}






@router.get("/print")
def print_files(ext: str = Query(..., description="File extension without dot, e.g., 'txt'")):
    """
    Read and return the contents of all files in the mounted directory with the given extension.

    Args:
        ext: File extension (without the leading dot), e.g., 'txt', 'json', 'md'.

    Returns:
        JSON object mapping each filename with the given extension to its file content.
    """
    if not MOUNT_PATH.exists():
        return {"error": f"Mount path {MOUNT_PATH} does not exist"}

    ext = ext.lower().strip().lstrip(".")
    result = {}

    for f in MOUNT_PATH.glob(f"*.{ext}"):
        if f.is_file():
            try:
                result[f.name] = f.read_text(encoding="utf-8")
            except Exception as e:
                result[f.name] = f"<error reading file: {e}>"

    return {"extension": ext, "files": result}