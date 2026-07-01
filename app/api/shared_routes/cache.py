"""
Opt-in Redis cache diagnostics routes for backend apps.

This module exposes reusable operational cache endpoints without making them
universal. A backend app must list the ``cache`` shared route group in its
``BackendAppDefinition.shared_route_groups`` before these routes are mounted.
The Redis client import is intentionally lazy so apps that do not require Redis
can boot without importing optional cache dependencies.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api.settings import settings
from backend.observability import log_event

logger = logging.getLogger("api.shared_routes.cache")
router = APIRouter(prefix="/cache", tags=["cache"])

_redis_client: Any | None = None


def _active_app_requires_redis() -> bool:
    """
    Return whether the selected backend app declares Redis as required.

    Args:
        None.

    Returns:
        bool: True when the active app contract requires Redis.

    Side Effects:
        Resolves the active backend app definition through settings.
    """
    return settings.get_backend_app_definition().requires_redis


def get_cache_client() -> Any:
    """
    Return a lazily initialized Redis client for cache diagnostics.

    Args:
        None.

    Returns:
        Any: Redis client instance created from ``settings.REDIS_URL``.

    Raises:
        HTTPException: HTTP 503 when Redis is disabled for the active app, the
            Redis package is unavailable, or the client cannot be initialized.

    Side Effects:
        Imports the optional Redis package and caches one client instance for
        reuse across requests.
    """
    if not _active_app_requires_redis():
        raise HTTPException(status_code=503, detail="Redis not available")

    global _redis_client
    if _redis_client is not None:
        return _redis_client

    try:
        import redis

        log_event(
            logger,
            logging.INFO,
            "cache.redis_client.initialize",
            redis_url=settings.REDIS_URL,
        )
        _redis_client = redis.Redis.from_url(settings.REDIS_URL)
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="Redis client library not installed") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Redis initialization failed: {str(exc)}") from exc

    return _redis_client


def _decode_cache_value(value: Any) -> str:
    """
    Convert a Redis value into a string response payload.

    Args:
        value (Any): Raw value returned by the Redis client.

    Returns:
        str: Decoded UTF-8 string for bytes, or ``str(value)`` for other Redis
            client return types.

    Side Effects:
        None.
    """
    if isinstance(value, bytes):
        return value.decode()
    return str(value)


@router.get("/{key}")
def get_cache(key: str, cache_client: Any = Depends(get_cache_client)) -> dict[str, str]:
    """
    Read one Redis cache value.

    Args:
        key (str): Redis key to read.
        cache_client (Any): Redis client dependency returned by
            ``get_cache_client``.

    Returns:
        dict[str, str]: Cache key and decoded value.

    Raises:
        HTTPException: HTTP 404 when the key is missing and HTTP 503 when Redis
            operations fail.

    Side Effects:
        Reads the requested key from Redis.
    """
    try:
        value = cache_client.get(key)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Redis read failed: {str(exc)}") from exc

    if value is None:
        raise HTTPException(status_code=404, detail="Key not found")
    return {"key": key, "value": _decode_cache_value(value)}


@router.post("/{key}")
def set_cache(
    key: str,
    value: str,
    cache_client: Any = Depends(get_cache_client),
) -> dict[str, str]:
    """
    Write one Redis cache value.

    Args:
        key (str): Redis key to write.
        value (str): Value stored at the key.
        cache_client (Any): Redis client dependency returned by
            ``get_cache_client``.

    Returns:
        dict[str, str]: Confirmation message.

    Raises:
        HTTPException: HTTP 503 when Redis write operations fail.

    Side Effects:
        Writes the provided key and value to Redis.
    """
    try:
        cache_client.set(key, value)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Redis write failed: {str(exc)}") from exc

    return {"message": f"Stored key '{key}' with value '{value}'"}
