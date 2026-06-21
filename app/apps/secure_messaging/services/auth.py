"""
Authentication service for secure messaging API.

Supports two auth modes that are resolved in priority order:

1. Per-client token registry (preferred).
   When SECURE_MESSAGING_CLIENT_TOKENS_JSON / _FILE is configured the
   submitted bearer token is matched against the map of client-name →
   token pairs. Each client has an independent token that can be rotated
   without affecting other callers.

2. Legacy single-token mode (backward-compatible fallback).
   When the per-client registry is absent or empty the submitted token is
   compared against SECURE_MESSAGING_AUTH_TOKEN / _FILE.  This preserves
   backward compatibility for deployments that have not yet migrated.
"""
from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from apps.secure_messaging.config.runtime import SecureMessagingSettings

logger = logging.getLogger("secure_messaging.auth")


@dataclass(frozen=True)
class AuthenticatedClient:
    """
    Represents a successfully authenticated request.

    Attributes:
        app (str): The app identifier from the request body (logging / tracing only).
        client_name (str | None): Named client key from the per-client token registry,
            or None when the legacy single-token mode was used for authentication.

    Returns:
        None: Immutable dataclass.
    """

    app: str
    client_name: str | None = None


def _extract_bearer_token(request: Request) -> str:
    """
    Extract and return the raw bearer token from the Authorization header.

    Args:
        request (Request): Incoming FastAPI request.

    Returns:
        str: The raw bearer token string.

    Raises:
        HTTPException: 401 when the header is absent or malformed.
    """
    auth_header = request.headers.get("authorization")
    if not auth_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format. Expected: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return parts[1]


def _try_client_registry_auth(submitted_token: str) -> str | None:
    """
    Attempt to authenticate the submitted token against the per-client registry.

    Iterates the client token map and performs a constant-time comparison for
    each entry to prevent timing-based enumeration of registered client names.

    Args:
        submitted_token (str): Raw bearer token from the request.

    Returns:
        str | None: The matched client name, or None when the registry is
            empty or the token does not match any entry.

    Raises:
        HTTPException: 503 when the registry configuration file is declared
            but cannot be read.
    """
    try:
        client_tokens = SecureMessagingSettings.get_client_tokens()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication configuration error",
        ) from exc

    if not client_tokens:
        return None

    for client_name, expected_token in client_tokens.items():
        if secrets.compare_digest(submitted_token, expected_token):
            return client_name

    return None


def _try_legacy_single_token_auth(submitted_token: str) -> bool:
    """
    Attempt to authenticate the submitted token against the legacy single token.

    Used as a fallback when no per-client registry is configured.

    Args:
        submitted_token (str): Raw bearer token from the request.

    Returns:
        bool: True when the submitted token matches the configured token.

    Raises:
        HTTPException: 503 when the token is not configured.
    """
    try:
        expected_token = SecureMessagingSettings.get_auth_token()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication configuration error",
        ) from exc

    return secrets.compare_digest(submitted_token, expected_token)


def authenticate_request(request: Request, request_app: str) -> AuthenticatedClient:
    """
    Authenticate a request using the Bearer token from the Authorization header.

    Resolution order:
      1. Per-client token registry (SECURE_MESSAGING_CLIENT_TOKENS_JSON / _FILE).
         Returns a named AuthenticatedClient when the token matches a registry entry.
      2. Legacy single-token mode (SECURE_MESSAGING_AUTH_TOKEN / _FILE).
         Returns an anonymous AuthenticatedClient (client_name=None) for backward
         compatibility when no per-client registry is configured.

    Both paths use constant-time comparison to prevent timing attacks.

    Args:
        request (Request): FastAPI request object.
        request_app (str): App identifier from the request body (logging / tracing only).

    Returns:
        AuthenticatedClient: Authenticated client information including the
            matched client name (None when legacy mode was used).

    Raises:
        HTTPException: 401 for missing or malformed Authorization header.
        HTTPException: 403 when the token does not match any registered entry.
        HTTPException: 503 when the auth configuration cannot be loaded.

    Side Effects:
        Logs a warning when the legacy single-token fallback is used, so operators
        can identify deployments that have not yet migrated to per-client tokens.
    """
    submitted_token = _extract_bearer_token(request)

    # Priority 1: per-client registry.
    matched_client = _try_client_registry_auth(submitted_token)
    if matched_client is not None:
        logger.info(
            "auth.client_registry.success",
            extra={"app": request_app, "client_name": matched_client},
        )
        return AuthenticatedClient(app=request_app, client_name=matched_client)

    # Priority 2: legacy single-token fallback.
    if _try_legacy_single_token_auth(submitted_token):
        logger.warning(
            "auth.legacy_token.success",
            extra={
                "app": request_app,
                "hint": "Migrate to per-client token registry (SECURE_MESSAGING_CLIENT_TOKENS_FILE)",
            },
        )
        return AuthenticatedClient(app=request_app, client_name=None)

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid authentication token",
    )
