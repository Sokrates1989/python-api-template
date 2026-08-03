"""Booking Service product routers composed by public API boundary."""

from fastapi import APIRouter

from apps.booking_service.routes.context import router as context_router
from apps.booking_service.routes.discovery import discovery_router
from apps.booking_service.routes.identity import router as identity_router
from apps.booking_service.routes.organizations import (
    organization_router,
    platform_router,
)


me_router = APIRouter(prefix="/v1/me")
"""Compose identity and effective context under the single ``/v1/me`` prefix."""

me_router.include_router(identity_router)
me_router.include_router(context_router)

__all__ = [
    "discovery_router",
    "me_router",
    "organization_router",
    "platform_router",
]
