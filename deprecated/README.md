# Deprecated Dependency Management Files

This directory contains legacy dependency management files that are **no longer used** in this project.

## ⚠️ Important Notice

**These files are kept for reference only and should NOT be used for development.**

## Current Dependency Management

This project now uses **PDM (Python Dependency Manager)** with Docker-based workflows.

- **Active files**: `pyproject.toml` and `pdm.lock` (in root directory)
- **Management script**: `python-dependency-management/scripts/manage-python-project-dependencies.sh`
- **Documentation**: See `docs/DEPENDENCY_MANAGEMENT.md`

## Files in This Directory

### `poetry.lock`
- **Status**: Deprecated
- **Replaced by**: `pdm.lock`
- **Last used**: Before migration to PDM
- **Purpose**: Poetry dependency lock file

### `requirements.txt`
- **Status**: Deprecated
- **Replaced by**: `pyproject.toml` + `pdm.lock`
- **Last used**: Before migration to PDM
- **Purpose**: Pip requirements file

## Why These Files Are Deprecated

1. **PDM is more modern**: Faster dependency resolution with uv backend
2. **Better lock files**: PDM provides more reliable dependency locking
3. **Docker integration**: PDM works seamlessly with our Docker workflow
4. **PEP 621 compliance**: Uses standardized `pyproject.toml` format

## Migration History

The project migrated from Poetry/pip to PDM to improve:
- Dependency resolution speed
- Docker build times
- Developer experience
- Compliance with modern Python standards

## Can I Delete These Files?

Yes, but they are kept here for:
- Historical reference
- Emergency rollback (if needed)
- Understanding previous dependency versions

---

**For current development, always use PDM via the Docker workflow described in the main README.md**
