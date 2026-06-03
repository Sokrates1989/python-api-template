"""Shared file service used by backend app route modules."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


class FileService:
    """Service for file operations."""

    def __init__(self, mount_path: Path):
        """
        Initialize the file service.

        Args:
            mount_path (Path): Mounted data directory.

        Returns:
            None.

        Side Effects:
            Stores the mounted path for later filesystem access.
        """
        self.mount_path = mount_path

    def list_txt_files(self) -> Dict[str, Any]:
        """
        List all `.txt` files in the mounted directory.

        Args:
            None.

        Returns:
            Dict[str, Any]: Matching filenames or an error payload.

        Side Effects:
            Reads the filesystem under the mounted directory.
        """
        if not self.mount_path.exists():
            return {"error": f"Mount path {self.mount_path} does not exist"}

        txt_files = [file_path.name for file_path in self.mount_path.glob("*.txt") if file_path.is_file()]
        return {"txt_files": txt_files}

    def list_extensions(self) -> Dict[str, Any]:
        """
        List all unique file extensions in the mounted directory.

        Args:
            None.

        Returns:
            Dict[str, Any]: Sorted extensions or an error payload.

        Side Effects:
            Reads the filesystem under the mounted directory.
        """
        if not self.mount_path.exists():
            return {"error": f"Mount path {self.mount_path} does not exist"}

        extensions = {
            file_path.suffix
            for file_path in self.mount_path.iterdir()
            if file_path.is_file() and file_path.suffix
        }
        return {"extensions": sorted(extensions)}

    def get_file_count(self) -> Dict[str, Any]:
        """
        Return the total file count in the mounted directory.

        Args:
            None.

        Returns:
            Dict[str, Any]: Count payload or an error payload.

        Side Effects:
            Reads the filesystem under the mounted directory.
        """
        if not self.mount_path.exists():
            return {"error": f"Mount path {self.mount_path} does not exist"}

        file_count = sum(1 for file_path in self.mount_path.iterdir() if file_path.is_file())
        return {"file_count": file_count}

    def print_txt_files(self) -> Dict[str, Any]:
        """
        Read and return all `.txt` files in the mounted directory.

        Args:
            None.

        Returns:
            Dict[str, Any]: File contents keyed by filename.

        Side Effects:
            Reads files from disk.
        """
        if not self.mount_path.exists():
            return {"error": f"Mount path {self.mount_path} does not exist"}

        result: Dict[str, Any] = {}
        for file_path in self.mount_path.glob("*.txt"):
            if file_path.is_file():
                try:
                    result[file_path.name] = file_path.read_text(encoding="utf-8")
                except Exception as exc:
                    result[file_path.name] = f"<error reading file: {exc}>"
        return result

    def list_files_by_extension(self, ext: str) -> Dict[str, Any]:
        """
        List files matching an extension.

        Args:
            ext (str): File extension without the leading dot.

        Returns:
            Dict[str, Any]: Matching filenames or an error payload.

        Side Effects:
            Reads the filesystem under the mounted directory.
        """
        if not self.mount_path.exists():
            return {"error": f"Mount path {self.mount_path} does not exist"}

        normalized_ext = ext.lower().strip().lstrip(".")
        files = [
            file_path.name for file_path in self.mount_path.glob(f"*.{normalized_ext}") if file_path.is_file()
        ]
        return {"extension": normalized_ext, "files": files}

    def print_files_by_extension(self, ext: str) -> Dict[str, Any]:
        """
        Read and return files matching an extension.

        Args:
            ext (str): File extension without the leading dot.

        Returns:
            Dict[str, Any]: Matching file contents or an error payload.

        Side Effects:
            Reads files from disk.
        """
        if not self.mount_path.exists():
            return {"error": f"Mount path {self.mount_path} does not exist"}

        normalized_ext = ext.lower().strip().lstrip(".")
        result: Dict[str, Any] = {}
        for file_path in self.mount_path.glob(f"*.{normalized_ext}"):
            if file_path.is_file():
                try:
                    result[file_path.name] = file_path.read_text(encoding="utf-8")
                except Exception as exc:
                    result[file_path.name] = f"<error reading file: {exc}>"
        return {"extension": normalized_ext, "files": result}
