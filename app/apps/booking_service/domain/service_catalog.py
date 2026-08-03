"""Pure policy constants and lifecycle values for timed service offerings.

The first Booking profile models products only as single-party timed services.
It deliberately contains no stock, capacity, physical-goods, payment-provider,
or worker-qualification behavior.
"""

from __future__ import annotations

from enum import StrEnum


class ServiceOfferingStatus(StrEnum):
    """Describe the reversible lifecycle of one service offering."""

    ACTIVE = "active"
    ARCHIVED = "archived"


MINIMUM_SERVICE_DURATION_MINUTES = 5
MAXIMUM_SERVICE_DURATION_MINUTES = 1_440
MAXIMUM_SERVICE_BUFFER_MINUTES = 1_440
MINIMUM_SLOT_STEP_MINUTES = 5
MAXIMUM_SLOT_STEP_MINUTES = 60
SLOT_STEP_INCREMENT_MINUTES = 5
MAXIMUM_SERVICE_PRICE_MINOR_UNITS = 1_000_000_000
MAXIMUM_SERVICE_LOCATIONS = 50
"""Validated bounds keeping catalog and later slot calculations finite."""


def validate_slot_step(value: int) -> int:
    """Validate one five-minute-aligned slot step.

    Args:
        value: Requested slot-step duration in minutes.

    Returns:
        int: The unchanged validated step.

    Raises:
        ValueError: When the step is outside 5–60 minutes or not divisible by
            five.
    """
    if not MINIMUM_SLOT_STEP_MINUTES <= value <= MAXIMUM_SLOT_STEP_MINUTES:
        raise ValueError("slot_step_minutes must be between 5 and 60")
    if value % SLOT_STEP_INCREMENT_MINUTES:
        raise ValueError("slot_step_minutes must use five-minute increments")
    return value
