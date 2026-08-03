"""Pure BKG-202 worker lifecycle and service-selection policy values."""

from __future__ import annotations

from enum import StrEnum

from apps.booking_service.domain.company_settings import WorkerSelectionMode


class WorkerProfileStatus(StrEnum):
    """Describe whether one worker may join newly computed availability."""

    ACTIVE = "active"
    INACTIVE = "inactive"


class ServiceWorkerSelectionMode(StrEnum):
    """Describe the authoritative worker-choice policy stored per service."""

    AUTO_ONLY = "auto_only"
    SPECIFIC_ONLY = "specific_only"
    SPECIFIC_OR_AUTO = "specific_or_auto"

    @property
    def allows_specific(self) -> bool:
        """Return whether this mode permits customer-selected workers."""
        return self is not ServiceWorkerSelectionMode.AUTO_ONLY


MAXIMUM_WORKER_LOCATIONS = 50
MAXIMUM_WORKER_QUALIFICATIONS = 100
MAXIMUM_WORKER_PRIORITY = 1_000
"""Finite bounds for explicit BKG-202 worker configuration."""


def service_mode_from_company_default(
    value: WorkerSelectionMode,
) -> ServiceWorkerSelectionMode:
    """Map one company default to the initial service-owned mode.

    Args:
        value: Organization-wide default from company settings.

    Returns:
        ServiceWorkerSelectionMode: Equivalent immutable service policy.
    """
    mapping = {
        WorkerSelectionMode.NEXT_AVAILABLE_ONLY: ServiceWorkerSelectionMode.AUTO_ONLY,
        WorkerSelectionMode.SPECIFIC_WORKER_ONLY: ServiceWorkerSelectionMode.SPECIFIC_ONLY,
        WorkerSelectionMode.NEXT_AVAILABLE_OR_SPECIFIC: (
            ServiceWorkerSelectionMode.SPECIFIC_OR_AUTO
        ),
    }
    return mapping[value]
