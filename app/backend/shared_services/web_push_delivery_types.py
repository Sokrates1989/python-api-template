"""Dependency-free contracts shared by Web Push delivery and dispatch.

Keeping aggregate result types separate from transport and subscription storage
lets schedulers and sibling apps reuse worker policy without installing an
unselected database provider or Web Push transport package.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WebPushDeliveryReport:
    """Summarize one account-scoped delivery attempt without endpoint data.

    Attributes:
        considered (int): Subscriptions loaded for the account.
        delivered (int): Remote push services that accepted a message.
        expired_removed (int): Locally expired records removed before sending.
        gone_removed (int): Remotely expired records removed after 404/410.
        failed (int): Retryable/configuration-safe per-endpoint failures.
    """

    considered: int
    delivered: int
    expired_removed: int
    gone_removed: int
    failed: int

    @property
    def removed(self) -> int:
        """Return the total number of stale provider records removed.

        Returns:
            int: Sum of locally expired and remotely gone subscriptions.
        """
        return self.expired_removed + self.gone_removed
