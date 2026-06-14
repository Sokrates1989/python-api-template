"""
Authentication service for secure messaging API.

Validates bearer tokens against the single configured auth token.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from apps.secure_messaging.config.runtime import SecureMessagingSettings


@dataclass(frozen=True)
class AuthenticatedClient:
    """
    Represents an authenticated request.

    Attributes:
        app (str): The app identifier from the request (for logging/identification).

    Returns:
        None: Immutable dataclass for authenticated client info.
    """

    app: str


def authenticate_request(request: Request, request_app: str) -> AuthenticatedClient:
    """
    Authenticate a request using Bearer token from Authorization header.

    Validates the token against the single configured auth token.
    The app field is used only for identification in logs/notifications.

    Args:
        request (Request): FastAPI request object.
        request_app (str): App identifier from request body (for identification only).

    Returns:
        AuthenticatedClient: Authenticated client information.

    Raises:
        HTTPException: 401 for missing/malformed auth, 403 for invalid token,
            503 for configuration errors.

    Side Effects:
        None.
    """
    # Extract Authorization header
    auth_header = request.headers.get("authorization")
    if not auth_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Validate Bearer scheme and extract token
    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format. Expected: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )
    submitted_token = parts[1]

    # Load configured auth token
    try:
        expected_token = SecureMessagingSettings.get_auth_token()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication configuration error",
        ) from exc

    # Validate token using constant-time comparison
    if not secrets.compare_digest(submitted_token, expected_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid authentication token",
        )

    return AuthenticatedClient(app=request_app)
