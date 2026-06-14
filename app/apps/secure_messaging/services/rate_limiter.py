"""
In-memory rate limiting for secure messaging.

Simple per-app rate limiting using monotonic time. Note: This is per-process
and per-replica. Production deployments should use replicas=1 or implement
Redis-backed distributed rate limiting for multi-replica setups.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from threading import Lock


@dataclass
class _RateLimitWindow:
    """
    Internal rate limit window for a single app.

    Attributes:
        timestamps (deque): Queue of request timestamps within the window.

    Returns:
        None: Internal mutable state for rate limiting.
    """

    timestamps: deque[float] = field(default_factory=lambda: deque(maxlen=1000))


class RateLimiter:
    """
    In-memory per-app rate limiter.

    Tracks request timestamps per app and enforces rate limits using a sliding
    window. Old timestamps outside the window are automatically purged.

    Attributes:
        _windows (dict): Map of app names to their rate limit windows.
        _lock (Lock): Thread-safe lock for window updates.
        _window_seconds (int): Sliding window duration in seconds.
        _max_requests (int): Maximum requests allowed per window.

    Returns:
        RateLimiter: Instance for checking and recording rate limits.
    """

    def __init__(self, max_requests_per_minute: int = 30) -> None:
        """
        Initialize rate limiter with configurable limits.

        Args:
            max_requests_per_minute (int): Maximum requests per minute per app.
                Defaults to 30.

        Returns:
            None.
        """
        self._windows: dict[str, _RateLimitWindow] = {}
        self._lock = Lock()
        self._window_seconds = 60  # 1 minute window
        self._max_requests = max_requests_per_minute

    def is_allowed(self, app: str) -> tuple[bool, int]:
        """
        Check if a request from the given app is allowed.

        Purges old timestamps outside the window and checks if the current
        request count is within the limit.

        Args:
            app (str): App identifier for rate limiting.

        Returns:
            tuple[bool, int]: (is_allowed, current_count) where is_allowed
                is True if the request should be permitted, False if rate
                limited. current_count is the number of requests in the window.

        Side Effects:
            Updates internal rate limit window for the app.
        """
        now = time.monotonic()
        cutoff = now - self._window_seconds

        with self._lock:
            # Get or create window for this app
            if app not in self._windows:
                self._windows[app] = _RateLimitWindow()
            window = self._windows[app]

            # Purge old timestamps outside the window
            while window.timestamps and window.timestamps[0] < cutoff:
                window.timestamps.popleft()

            current_count = len(window.timestamps)

            # Check if under limit
            if current_count >= self._max_requests:
                return False, current_count

            # Record this request
            window.timestamps.append(now)
            return True, current_count + 1

    def get_current_count(self, app: str) -> int:
        """
        Get current request count for an app without incrementing.

        Args:
            app (str): App identifier to check.

        Returns:
            int: Current number of requests in the window.
        """
        now = time.monotonic()
        cutoff = now - self._window_seconds

        with self._lock:
            if app not in self._windows:
                return 0
            window = self._windows[app]

            # Purge old timestamps
            while window.timestamps and window.timestamps[0] < cutoff:
                window.timestamps.popleft()

            return len(window.timestamps)
