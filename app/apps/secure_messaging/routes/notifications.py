"""
Notification routes for secure messaging API.
"""
from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, status

from apps.secure_messaging.config.runtime import SecureMessagingSettings
from apps.secure_messaging.schemas.notifications import (
    NotifyRequest,
    NotifyResponse,
    ProviderResult,
)
from apps.secure_messaging.services.auth import authenticate_request
from apps.secure_messaging.services.notification_service import dispatch_notification
from apps.secure_messaging.services.providers import ProviderDispatchResult
from apps.secure_messaging.services.rate_limiter import RateLimiter

logger = logging.getLogger("secure_messaging.routes")

# Initialize rate limiter
_rate_limiter = RateLimiter(
    max_requests_per_minute=SecureMessagingSettings.get_rate_limit_per_minute()
)

router = APIRouter(tags=["secure-messaging"], prefix="/v1")


@router.post("/notify", response_model=NotifyResponse)
async def notify(
    request: Request,
    notify_request: NotifyRequest,
) -> NotifyResponse:
    """
    Send a notification through configured providers.

    Requires Bearer authentication. Validates the Authorization header against
    the single configured secure messaging token. Rate limited per calling app.
    Content is redacted before logging and sending.

    Args:
        request (Request): FastAPI request for auth header extraction.
        notify_request (NotifyRequest): Notification details.

    Returns:
        NotifyResponse: Delivery status per provider.

    Raises:
        HTTPException: 401 for missing/malformed auth, 403 for invalid token,
            429 for rate limit exceeded, 400 for disabled provider,
            502 for all providers failed, 503 for configuration errors.
    """
    # Authenticate the request
    auth_client = authenticate_request(request, notify_request.app)
    logger.info(
        "notify.authenticated",
        extra={"app": auth_client.app},
    )

    # Rate limiting check
    allowed, current_count = _rate_limiter.is_allowed(notify_request.app)
    if not allowed:
        logger.warning(
            "notify.rate_limited",
            extra={"app": notify_request.app, "current_count": current_count},
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Max {_rate_limiter._max_requests} requests per minute.",
        )

    # Validate provider selection
    try:
        overall_status, provider_results = await dispatch_notification(notify_request)
    except ValueError as exc:
        logger.error(
            "notify.provider_error",
            extra={"app": notify_request.app, "error": str(exc)},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    # Convert results to response schema
    results = {
        name: ProviderResult(
            status=result.status,
            sender=result.sender,
            error=result.error,
        )
        for name, result in provider_results.items()
    }

    # Determine HTTP status code
    http_status = _determine_http_status(overall_status, provider_results)

    if http_status >= 400:
        raise HTTPException(
            status_code=http_status,
            detail=NotifyResponse(status=overall_status, providers=results).model_dump(),
        )

    return NotifyResponse(status=overall_status, providers=results)


def _determine_http_status(
    overall_status: Literal["sent", "partial_failure", "failed"],
    provider_results: dict[str, ProviderDispatchResult],
) -> int:
    """
    Determine HTTP status code from dispatch results.

    Args:
        overall_status (str): Overall dispatch status.
        provider_results (dict): Per-provider dispatch results.

    Returns:
        int: HTTP status code.
    """
    if overall_status == "sent":
        return status.HTTP_200_OK

    if overall_status == "partial_failure":
        # 207 Multi-Status for partial success
        return status.HTTP_207_MULTI_STATUS

    # overall_status == "failed"
    # Check if all providers were disabled (503) vs actual failures (502)
    all_disabled = all(
        result.status == "disabled" for result in provider_results.values()
    )
    if all_disabled:
        return status.HTTP_503_SERVICE_UNAVAILABLE

    return status.HTTP_502_BAD_GATEWAY
