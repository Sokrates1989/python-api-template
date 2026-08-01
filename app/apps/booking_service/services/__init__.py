"""Booking Service application services and safe domain errors."""

from apps.booking_service.services.errors import TenancyError
from apps.booking_service.services.tenancy_service import BookingTenancyService

__all__ = ["BookingTenancyService", "TenancyError"]
