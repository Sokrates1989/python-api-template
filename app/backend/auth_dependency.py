"""Authentication dependencies for FastAPI endpoints.

Supports Cognito and Keycloak JWT validation with optional dual-provider fallback.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

import requests
from fastapi import Depends, HTTPException, Request, status
from jose.exceptions import JWTClaimsError, JWTError, ExpiredSignatureError

from backend.auth_provider_utils import get_user_info_from_provider, resolve_provider_sequence
from backend.observability import log_event
from api.settings import settings

logger = logging.getLogger("backend.auth")


def _log_auth_failure(
    request: Request,
    *,
    provider: str,
    status_code: int,
    detail: Any,
) -> None:
    """Log an authentication failure without exposing bearer tokens.

    Args:
        request: FastAPI request that failed authentication.
        provider: Configured auth provider or provider branch that rejected the request.
        status_code: HTTP status code returned to the client.
        detail: Sanitized error detail sent with the HTTP response.

    Returns:
        None: The function only emits a structured warning log.
    """
    log_event(
        logger,
        logging.WARNING,
        "auth.failure",
        method=request.method,
        path=request.url.path,
        provider=provider,
        status_code=status_code,
        detail=str(detail),
        has_authorization=bool(request.headers.get("Authorization")),
    )


def _extract_bearer_token(request: Request) -> str:
    """Extract the bearer token from the Authorization header.

    Args:
        request: FastAPI request object.

    Returns:
        str: JWT token string.

    Raises:
        HTTPException: When the header is missing or token is empty.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header is required",
        )

    token = auth_header[7:] if auth_header.startswith("Bearer ") else auth_header
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="JWT token is required",
        )
    return token


def _build_debug_user_info(request: Request) -> Dict[str, Any]:
    """Build a placeholder identity for AUTH_PROVIDER=none.

    Args:
        request: FastAPI request object.

    Returns:
        Dict[str, Any]: User info payload with a synthetic user identity.
    """
    user_id = request.headers.get("X-User-Id") or "local-user"
    email = request.headers.get("X-User-Email") or "local-user@example.com"
    username = request.headers.get("X-Username") or user_id
    claims = {
        "sub": user_id,
        "email": email,
        "preferred_username": username,
    }
    return {
        "sub": user_id,
        "user_id": user_id,
        "email": email,
        "username": username,
        "claims": claims,
        "provider": "none",
    }


def _raise_http_error_for_provider(provider: str, exc: Exception) -> None:
    """Raise an HTTPException corresponding to provider verification errors.

    Args:
        provider: Provider name used for context.
        exc: Exception raised during verification.

    Raises:
        HTTPException: Mapped to the appropriate HTTP status.
    """
    provider_label = provider.capitalize()
    if isinstance(exc, RuntimeError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{provider_label} configuration is missing",
        ) from exc
    if isinstance(exc, requests.HTTPError):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch {provider_label} JWKS",
        ) from exc
    if isinstance(exc, (ValueError, ExpiredSignatureError, JWTClaimsError, JWTError)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid JWT token: {exc}",
        ) from exc
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Token verification error: {exc}",
    ) from exc


def _format_auth_error(provider: str, exc: Exception) -> str:
    """Format provider errors for dual-auth failure messages.

    Args:
        provider: Provider name used for context.
        exc: Exception raised during verification.

    Returns:
        str: Human-readable error message.
    """
    provider_label = provider.capitalize()
    if isinstance(exc, RuntimeError):
        return f"{provider_label} configuration missing"
    if isinstance(exc, requests.HTTPError):
        return f"{provider_label} JWKS fetch failed"
    if isinstance(exc, (ValueError, ExpiredSignatureError, JWTClaimsError, JWTError)):
        return f"{provider_label} token invalid: {exc}"
    return f"{provider_label} error: {exc}"


def _build_dual_auth_exception(errors: list[tuple[str, Exception]]) -> HTTPException:
    """Build HTTPException for dual-provider authentication failures.

    Args:
        errors: List of provider/error pairs.

    Returns:
        HTTPException: Exception describing the combined failure.
    """
    detail = "; ".join(_format_auth_error(provider, exc) for provider, exc in errors)
    if any(isinstance(exc, RuntimeError) for _, exc in errors):
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    elif any(isinstance(exc, requests.HTTPError) for _, exc in errors):
        status_code = status.HTTP_502_BAD_GATEWAY
    else:
        status_code = status.HTTP_401_UNAUTHORIZED
    return HTTPException(status_code=status_code, detail=detail)


async def verify_auth_dependency(request: Request) -> Dict[str, Any]:
    """Validate JWT tokens based on the configured auth provider.

    Args:
        request: FastAPI request object.

    Returns:
        Dict[str, Any]: Normalized user info payload.

    Raises:
        HTTPException: When validation fails or configuration is missing.
    """
    provider = settings.get_auth_provider()
    providers = resolve_provider_sequence(provider)

    if not providers:
        return _build_debug_user_info(request)

    try:
        token = _extract_bearer_token(request)
    except HTTPException as exc:
        _log_auth_failure(
            request,
            provider=provider,
            status_code=exc.status_code,
            detail=exc.detail,
        )
        raise

    errors: list[tuple[str, Exception]] = []
    for provider_name in providers:
        try:
            return get_user_info_from_provider(provider_name, token)
        except Exception as exc:
            if provider == "dual":
                errors.append((provider_name, exc))
                continue
            try:
                _raise_http_error_for_provider(provider_name, exc)
            except HTTPException as http_exc:
                _log_auth_failure(
                    request,
                    provider=provider_name,
                    status_code=http_exc.status_code,
                    detail=http_exc.detail,
                )
                raise

    dual_auth_exception = _build_dual_auth_exception(errors)
    _log_auth_failure(
        request,
        provider="dual",
        status_code=dual_auth_exception.status_code,
        detail=dual_auth_exception.detail,
    )
    raise dual_auth_exception


async def verify_jwt_token_dependency(request: Request) -> Dict[str, Any]:
    """Backward-compatible alias for verify_auth_dependency."""
    return await verify_auth_dependency(request)


def get_user_id_from_token(user_info: Dict[str, Any] = Depends(verify_auth_dependency)) -> str:
    """Helper dependency returning the authenticated user's ID."""

    user_id = user_info.get("user_id") or user_info.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject claim",
        )
    return user_id
