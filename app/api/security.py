"""
Security utilities for API authentication.
"""
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from api.settings import settings

# Define the API key headers
admin_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False)
restore_key_header = APIKeyHeader(name="X-Restore-Key", auto_error=False)
bearer_token = HTTPBearer(auto_error=False)


def _extract_bearer_value(credentials: HTTPAuthorizationCredentials | None) -> str:
    """Extract raw bearer credential value."""
    if credentials is None:
        return ""
    return (credentials.credentials or "").strip()


async def verify_admin_key(
    admin_key: str = Security(admin_key_header),
    bearer: HTTPAuthorizationCredentials | None = Security(bearer_token),
) -> str:
    """
    Verify the admin API key provided in the X-Admin-Key header.
    
    This is used for sensitive operations like backup/restore.
    
    Args:
        admin_key: The admin API key from the request header
        
    Returns:
        The validated admin API key
        
    Raises:
        HTTPException: If the admin API key is missing or invalid
    """
    # Get admin API key from file or environment
    configured_admin_key = settings.get_admin_api_key()
    
    # Check if ADMIN_API_KEY is configured
    if not configured_admin_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin API key not configured. Please set ADMIN_API_KEY or ADMIN_API_KEY_FILE."
        )
    
    # Check if API key was provided
    if not admin_key:
        bearer_value = _extract_bearer_value(bearer)
        if not bearer_value:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing credentials. Provide either 'X-Admin-Key' or 'Authorization: Bearer <token>'."
            )
        admin_key = bearer_value
    
    # Verify the API key
    if admin_key != configured_admin_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid admin API key. The provided 'X-Admin-Key' does not match the configured ADMIN_API_KEY."
        )
    
    return admin_key


async def verify_restore_key(
    restore_key: str = Security(restore_key_header),
    bearer: HTTPAuthorizationCredentials | None = Security(bearer_token),
) -> str:
    """
    Verify the restore API key provided in the X-Restore-Key header.
    
    This is used for destructive restore operations that overwrite the database.
    
    Args:
        restore_key: The restore API key from the request header
        
    Returns:
        The validated restore API key
        
    Raises:
        HTTPException: If the restore API key is missing or invalid
    """
    # Get restore API key from file or environment
    configured_restore_key = settings.get_restore_api_key()
    
    # Check if BACKUP_RESTORE_API_KEY is configured
    if not configured_restore_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Restore API key not configured. Please set BACKUP_RESTORE_API_KEY or BACKUP_RESTORE_API_KEY_FILE."
        )
    
    # Check if API key was provided
    if not restore_key:
        bearer_value = _extract_bearer_value(bearer)
        if not bearer_value:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing credentials. Provide either 'X-Restore-Key' or 'Authorization: Bearer <token>'."
            )
        restore_key = bearer_value
    
    # Verify the API key
    if restore_key != configured_restore_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid restore API key. The provided 'X-Restore-Key' does not match the configured BACKUP_RESTORE_API_KEY."
        )
    
    return restore_key
