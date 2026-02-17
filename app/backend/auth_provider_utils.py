"""
Module: auth_provider_utils.py
Author: Cascade
Date: 2025-01-01
Version: 1.0.0

Description:
    Utilities for resolving authentication providers and validating JWTs.
    Handles JWKS caching, Cognito/Keycloak signature verification, and
    normalization of user claim payloads.

Dependencies:
    - requests
    - python-jose
    - api.settings

Usage:
    from backend.auth_provider_utils import get_user_info_from_provider

    user_info = get_user_info_from_provider("keycloak", token)
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

import requests
from jose import jwk, jwt
from jose.utils import base64url_decode

from api.settings import settings

_JWKS_CACHE_TTL_SECONDS = 3600
_cognito_jwks_cache: Optional[Dict[str, Any]] = None
_cognito_jwks_cache_time: float = 0.0
_keycloak_jwks_cache: Optional[Dict[str, Any]] = None
_keycloak_jwks_cache_time: float = 0.0


def _is_cache_valid(cache_time: float) -> bool:
    """Return True when the JWKS cache is still valid.

    Args:
        cache_time: Epoch timestamp for the last JWKS refresh.

    Returns:
        bool: True when the cache is within the TTL window.
    """
    return (time.time() - cache_time) < _JWKS_CACHE_TTL_SECONDS


def _fetch_jwks(jwks_url: str) -> Dict[str, Any]:
    """Fetch JWKS data from the provided URL.

    Args:
        jwks_url: The URL to fetch JWKS data from.

    Returns:
        Dict[str, Any]: Parsed JWKS payload.

    Raises:
        ValueError: When the JWKS payload is missing required keys.
        requests.HTTPError: When the JWKS fetch fails.
    """
    response = requests.get(jwks_url, timeout=5)
    response.raise_for_status()
    jwks = response.json()
    if "keys" not in jwks:
        raise ValueError("Invalid JWKS payload returned by identity provider")
    return jwks


def _find_jwk_by_kid(jwks: Dict[str, Any], kid: str) -> Optional[Dict[str, Any]]:
    """Return the JWK matching the given key ID.

    Args:
        jwks: JWKS payload.
        kid: Key ID to match.

    Returns:
        Optional[Dict[str, Any]]: Matching JWK entry if found.
    """
    return next((key for key in jwks.get("keys", []) if key.get("kid") == kid), None)


def _build_user_info_from_claims(claims: Dict[str, Any], provider: str) -> Dict[str, Any]:
    """Normalize JWT claims into a consistent user info structure.

    Args:
        claims: JWT claims payload.
        provider: Provider name (cognito or keycloak).

    Returns:
        Dict[str, Any]: Normalized user info payload.
    """
    if provider == "keycloak":
        user_id = claims.get("sub") or claims.get("sid") or claims.get("azp")
        username = claims.get("preferred_username") or claims.get("azp") or user_id
    else:
        user_id = claims.get("sub")
        username = claims.get("cognito:username") or claims.get("username") or user_id

    return {
        "sub": claims.get("sub") or user_id,
        "user_id": user_id,
        "email": claims.get("email"),
        "username": username,
        "claims": claims,
        "provider": provider,
    }


def _get_cognito_jwks(force_refresh: bool = False) -> Dict[str, Any]:
    """Return cached JWKS for the configured Cognito user pool.

    Args:
        force_refresh: When True, always fetch a fresh JWKS payload.

    Returns:
        Dict[str, Any]: JWKS payload.

    Raises:
        RuntimeError: When Cognito configuration is missing.
    """
    region = (settings.AWS_REGION or "").strip()
    user_pool = (settings.get_cognito_user_pool_id() or "").strip()

    if not region or not user_pool:
        raise RuntimeError("AWS Cognito configuration is missing")

    jwks_url = (
        f"https://cognito-idp.{region}.amazonaws.com/"
        f"{user_pool}/.well-known/jwks.json"
    )

    global _cognito_jwks_cache, _cognito_jwks_cache_time
    if not force_refresh and _cognito_jwks_cache and _is_cache_valid(_cognito_jwks_cache_time):
        return _cognito_jwks_cache

    jwks = _fetch_jwks(jwks_url)
    _cognito_jwks_cache = jwks
    _cognito_jwks_cache_time = time.time()
    return jwks


def _verify_cognito_token(token: str) -> Dict[str, Any]:
    """Verify a JWT access token issued by Cognito.

    Args:
        token: JWT access token string.

    Returns:
        Dict[str, Any]: Decoded JWT claims.

    Raises:
        ValueError: When token validation fails.
        RuntimeError: When Cognito configuration is missing.
    """
    jwks = _get_cognito_jwks()
    headers = jwt.get_unverified_header(token)
    kid = headers.get("kid")

    if not kid:
        raise ValueError("Token header missing 'kid'")

    key = _find_jwk_by_kid(jwks, kid)
    if not key:
        jwks = _get_cognito_jwks(force_refresh=True)
        key = _find_jwk_by_kid(jwks, kid)
    if not key:
        raise ValueError("Matching JWK not found for token")

    public_key = jwk.construct(key)
    message, encoded_signature = token.rsplit(".", 1)
    decoded_signature = base64url_decode(encoded_signature.encode())

    if not public_key.verify(message.encode(), decoded_signature):
        raise ValueError("Token signature verification failed")

    issuer = (
        f"https://cognito-idp.{settings.AWS_REGION}.amazonaws.com/"
        f"{settings.get_cognito_user_pool_id()}"
    )

    audience = settings.get_cognito_app_client_id()
    if audience == "app_client_id_is_not_set":
        audience = None

    claims = jwt.decode(
        token,
        key,
        algorithms=["RS256"],
        audience=audience,
        issuer=issuer,
    )

    if claims.get("token_use") != "access":
        raise ValueError("Token is not an access token")

    return claims


def _get_keycloak_jwks(force_refresh: bool = False) -> Dict[str, Any]:
    """Return cached JWKS for the configured Keycloak realm.

    Args:
        force_refresh: When True, always fetch a fresh JWKS payload.

    Returns:
        Dict[str, Any]: JWKS payload.

    Raises:
        RuntimeError: When Keycloak configuration is missing.
    """
    jwks_url = settings.get_keycloak_jwks_url()
    if not jwks_url:
        raise RuntimeError("Keycloak configuration is missing")

    global _keycloak_jwks_cache, _keycloak_jwks_cache_time
    if not force_refresh and _keycloak_jwks_cache and _is_cache_valid(_keycloak_jwks_cache_time):
        return _keycloak_jwks_cache

    jwks = _fetch_jwks(jwks_url)
    _keycloak_jwks_cache = jwks
    _keycloak_jwks_cache_time = time.time()
    return jwks


def _verify_keycloak_token(token: str) -> Dict[str, Any]:
    """Verify a JWT access token issued by Keycloak.

    Args:
        token: JWT access token string.

    Returns:
        Dict[str, Any]: Decoded JWT claims.

    Raises:
        ValueError: When token validation fails.
        RuntimeError: When Keycloak configuration is missing.
    """
    jwks = _get_keycloak_jwks()
    headers = jwt.get_unverified_header(token)
    kid = headers.get("kid")

    if not kid:
        raise ValueError("Token header missing 'kid'")

    key = _find_jwk_by_kid(jwks, kid)
    if not key:
        jwks = _get_keycloak_jwks(force_refresh=True)
        key = _find_jwk_by_kid(jwks, kid)
    if not key:
        raise ValueError("Matching JWK not found for token")

    public_key = jwk.construct(key)
    message, encoded_signature = token.rsplit(".", 1)
    decoded_signature = base64url_decode(encoded_signature.encode())

    if not public_key.verify(message.encode(), decoded_signature):
        raise ValueError("Token signature verification failed")

    issuer = settings.get_keycloak_issuer_url()
    if not issuer:
        raise RuntimeError("Keycloak configuration is missing")

    audience = (settings.KEYCLOAK_CLIENT_ID or "").strip() or None

    claims = jwt.decode(
        token,
        key,
        algorithms=["RS256"],
        audience=audience,
        issuer=issuer,
        options={"verify_aud": bool(audience)},
    )

    return claims


def get_user_info_from_provider(provider: str, token: str) -> Dict[str, Any]:
    """Validate token for the provider and return normalized user info.

    Args:
        provider: Provider name (cognito or keycloak).
        token: JWT access token.

    Returns:
        Dict[str, Any]: Normalized user info payload.
    """
    if provider == "cognito":
        claims = _verify_cognito_token(token)
    elif provider == "keycloak":
        claims = _verify_keycloak_token(token)
    else:
        raise ValueError(f"Unsupported provider: {provider}")

    return _build_user_info_from_claims(claims, provider)


def resolve_provider_sequence(provider: str) -> list[str]:
    """Resolve provider sequence for authentication attempts.

    Args:
        provider: Configured provider value.

    Returns:
        list[str]: Ordered list of providers to attempt.

    Raises:
        ValueError: When provider is unknown.
    """
    normalized = (provider or "").strip().lower()
    if normalized == "dual":
        return ["keycloak", "cognito"]
    if normalized in {"cognito", "keycloak"}:
        return [normalized]
    if normalized == "none":
        return []
    raise ValueError(f"Unsupported auth provider: {provider}")
