"""Application-owned repositories for scoped Booking persistence."""

from apps.booking_service.repositories.membership_repository import MembershipRepository
from apps.booking_service.repositories.tenancy_repository import TenancyRepository

__all__ = ["MembershipRepository", "TenancyRepository"]
