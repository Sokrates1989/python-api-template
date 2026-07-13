"""Authenticated Web Push registration routes owned by the Felix backend.

Routes are mounted below ``/felix/v1/notifications/web-push`` and never use a
redundant ``/api`` prefix. The router exposes only browser-safe public
configuration, account-scoped subscription mutations, and fixed-kind schedule
replacement. Callers never provide visible notification copy or routes.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from api.shared_dependencies.auth import get_user_id_from_token
from api.shared_schemas.web_push import (
    WebPushDeletionData,
    WebPushDeletionResponse,
    WebPushPublicKeyResponse,
    WebPushRegistrationData,
    WebPushRegistrationResponse,
    WebPushSubscriptionDeleteRequest,
    WebPushSubscriptionRequest,
)
from apps.felix.schemas.web_push_dispatch import (
    FelixWebPushScheduleData,
    FelixWebPushScheduleReplaceRequest,
    FelixWebPushScheduleResponse,
)
from apps.felix.services.web_push_dispatch_service import (
    FelixWebPushDispatchService,
    FelixWebPushDispatchUnavailable,
    FelixWebPushScheduledOccurrence,
)
from apps.felix.services.web_push_service import FelixWebPushService
from backend.shared_services.web_push_subscriptions import WebPushSubscription

logger = logging.getLogger("apps.felix.routes.web_push")
router = APIRouter(prefix="/v1/notifications/web-push", tags=["web-push"])


def get_web_push_service() -> FelixWebPushService:
    """Return a Felix Web Push service for one request.

    Args:
        None.

    Returns:
        FelixWebPushService: App-owned policy and persistence service.

    Side Effects:
        None until configuration or provider storage is requested.
    """
    return FelixWebPushService()


def get_web_push_dispatch_service() -> FelixWebPushDispatchService:
    """Return a Felix durable dispatch service for one request.

    Returns:
        FelixWebPushDispatchService: App-owned schedule policy and storage.

    Side Effects:
        None until enablement or provider storage is requested.
    """
    return FelixWebPushDispatchService()


@router.get("/public-key", response_model=WebPushPublicKeyResponse)
async def get_web_push_public_key(
    current_user_id: str = Depends(get_user_id_from_token),
    service: FelixWebPushService = Depends(get_web_push_service),
) -> WebPushPublicKeyResponse:
    """Return the public VAPID key to an authenticated Felix account.

    Args:
        current_user_id (str): Authenticated user id from the bearer token.
        service (FelixWebPushService): Request-scoped Felix Web Push service.

    Returns:
        WebPushPublicKeyResponse: Browser-safe application-server key.

    Raises:
        HTTPException: With 503 when public Web Push configuration is missing
            or malformed.

    Side Effects:
        May read file-backed public-key configuration. The authenticated id is
        intentionally consumed by the dependency even though it is not echoed.
    """
    del current_user_id
    try:
        return WebPushPublicKeyResponse(application_server_key=service.get_public_key())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Felix Web Push is not configured.",
        ) from exc


@router.post(
    "/subscriptions",
    response_model=WebPushRegistrationResponse,
    status_code=status.HTTP_200_OK,
)
async def register_web_push_subscription(
    request: WebPushSubscriptionRequest,
    current_user_id: str = Depends(get_user_id_from_token),
    service: FelixWebPushService = Depends(get_web_push_service),
) -> WebPushRegistrationResponse:
    """Idempotently register one browser subscription to the current account.

    Args:
        request (WebPushSubscriptionRequest): Standard browser subscription.
        current_user_id (str): Authenticated user id from the bearer token.
        service (FelixWebPushService): Request-scoped Felix Web Push service.

    Returns:
        WebPushRegistrationResponse: Accepted endpoint and creation status.

    Raises:
        HTTPException: With 503 when the active provider cannot persist the
            subscription.

    Side Effects:
        Creates or refreshes one account-owned provider record.
    """
    try:
        created = await service.register(
            current_user_id,
            WebPushSubscription(
                endpoint=request.endpoint,
                expiration_time=request.expiration_time,
                p256dh=request.keys.p256dh,
                auth=request.keys.auth,
            ),
        )
    except Exception as exc:
        logger.exception("Felix Web Push registration failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Felix Web Push registration is temporarily unavailable.",
        ) from exc
    return WebPushRegistrationResponse(
        data=WebPushRegistrationData(
            endpoint=request.endpoint,
            created=created,
        )
    )


@router.delete(
    "/subscriptions",
    response_model=WebPushDeletionResponse,
    status_code=status.HTTP_200_OK,
)
async def delete_web_push_subscription(
    request: WebPushSubscriptionDeleteRequest,
    current_user_id: str = Depends(get_user_id_from_token),
    service: FelixWebPushService = Depends(get_web_push_service),
) -> WebPushDeletionResponse:
    """Idempotently remove one current-account browser endpoint.

    Args:
        request (WebPushSubscriptionDeleteRequest): Endpoint deletion payload.
        current_user_id (str): Authenticated user id from the bearer token.
        service (FelixWebPushService): Request-scoped Felix Web Push service.

    Returns:
        WebPushDeletionResponse: Endpoint and whether a record existed.

    Raises:
        HTTPException: With 503 when the active provider cannot perform the
            deletion. An already-absent endpoint remains a successful response.

    Side Effects:
        Deletes at most one account-owned provider record.
    """
    try:
        deleted = await service.unregister(current_user_id, request.endpoint)
    except Exception as exc:
        logger.exception("Felix Web Push deletion failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Felix Web Push removal is temporarily unavailable.",
        ) from exc
    return WebPushDeletionResponse(
        data=WebPushDeletionData(
            endpoint=request.endpoint,
            deleted=deleted,
        )
    )


@router.put(
    "/schedule",
    response_model=FelixWebPushScheduleResponse,
    status_code=status.HTTP_200_OK,
)
async def replace_web_push_schedule(
    request: FelixWebPushScheduleReplaceRequest,
    current_user_id: str = Depends(get_user_id_from_token),
    service: FelixWebPushDispatchService = Depends(get_web_push_dispatch_service),
) -> FelixWebPushScheduleResponse:
    """Replace the current account's predefined rolling push horizon.

    Args:
        request (FelixWebPushScheduleReplaceRequest): Zero to 60 future
            fixed-kind occurrences. No visible copy or route is accepted.
        current_user_id (str): Authenticated user id from the bearer token.
        service (FelixWebPushDispatchService): Request-scoped schedule service.

    Returns:
        FelixWebPushScheduleResponse: Count-only replacement result.

    Raises:
        HTTPException: With 422 for invalid horizon policy, 503 when dispatch
            is disabled, or 503 when provider persistence fails.

    Side Effects:
        Replaces unleased durable jobs owned by the authenticated account.
    """
    occurrences = [
        FelixWebPushScheduledOccurrence(
            schedule_key=item.schedule_key,
            kind=item.kind,
            due_at=item.due_at,
            locale=item.locale,
        )
        for item in request.occurrences
    ]
    try:
        result = await service.replace_schedule(current_user_id, occurrences)
    except FelixWebPushDispatchUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Felix scheduled Web Push is not enabled.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Felix Web Push schedule replacement failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Felix Web Push scheduling is temporarily unavailable.",
        ) from exc
    return FelixWebPushScheduleResponse(
        data=FelixWebPushScheduleData(
            scheduled=result.scheduled,
            removed=result.removed,
            dispatch_enabled=service.dispatch_enabled,
        )
    )
