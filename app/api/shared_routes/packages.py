"""Shared package inspection routes protected by the admin key."""
from __future__ import annotations

import importlib.metadata
import sys
from typing import Any, Dict

from fastapi import APIRouter, Depends

from api.shared_dependencies.security import verify_admin_key

router = APIRouter(prefix="/packages", tags=["packages"])


@router.get("/list")
def list_packages(_: str = Depends(verify_admin_key)) -> Dict[str, Any]:
    """List all installed Python packages and their versions."""
    packages = []
    distributions = sorted(importlib.metadata.distributions(), key=lambda distribution: distribution.name.lower())
    for distribution in distributions:
        packages.append({"name": distribution.name, "version": distribution.version})
    return {
        "total_packages": len(packages),
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "packages": packages,
    }


@router.get("/info/{package_name}")
def get_package_info(package_name: str, _: str = Depends(verify_admin_key)) -> Dict[str, Any]:
    """Return metadata for one installed package."""
    try:
        distribution = importlib.metadata.distribution(package_name)
        metadata = {
            "name": distribution.name,
            "version": distribution.version,
            "summary": distribution.metadata.get("Summary", ""),
            "home_page": distribution.metadata.get("Home-page", ""),
            "author": distribution.metadata.get("Author", ""),
            "license": distribution.metadata.get("License", ""),
            "requires_python": distribution.metadata.get("Requires-Python", ""),
        }
        requires = distribution.metadata.get_all("Requires-Dist")
        metadata["dependencies"] = [requirement.split(";")[0].strip() for requirement in requires] if requires else []
        return metadata
    except importlib.metadata.PackageNotFoundError:
        return {
            "error": f"Package '{package_name}' not found",
            "available_packages": [
                distribution.name
                for distribution in sorted(importlib.metadata.distributions(), key=lambda item: item.name.lower())
            ],
        }
