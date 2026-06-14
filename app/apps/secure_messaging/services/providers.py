"""
Provider dispatch and result tracking for notifications.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ProviderDispatchResult:
    """
    Result of a single provider dispatch attempt.

    Attributes:
        status (str): Delivery status: sent, failed, disabled, skipped.
        sender (str | None): Sender name used for dispatch when applicable.
        error (str | None): Optional sanitized error message.

    Returns:
        None: Immutable result of provider dispatch.
    """

    status: Literal["sent", "failed", "disabled", "skipped"]
    sender: str | None = None
    error: str | None = None


class ProviderDispatchError(Exception):
    """
    Exception raised when provider dispatch fails.

    Attributes:
        message (str): Error message (sanitized, no secrets).
        provider (str): Provider that failed.

    Returns:
        None: Exception for provider failures.
    """

    def __init__(self, message: str, provider: str) -> None:
        """
        Initialize provider dispatch error.

        Args:
            message (str): Sanitized error message.
            provider (str): Provider name.
        """
        super().__init__(message)
        self.provider = provider
