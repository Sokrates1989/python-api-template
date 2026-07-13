"""Unit coverage for selected-app background-service lifecycle ownership."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from api.config.lifecycle import (
    _start_background_services,
    _stop_background_services,
)


class _Service:
    """Record deterministic service starts and stops."""

    def __init__(
        self,
        name: str,
        events: list[str],
        *,
        fail_start: bool = False,
        fail_stop: bool = False,
    ) -> None:
        """Create one lifecycle-observable fake service.

        Args:
            name (str): Stable service name.
            events (list[str]): Shared ordered lifecycle event log.
            fail_start (bool): Whether ``start`` raises after recording.
            fail_stop (bool): Whether ``stop`` raises after recording.

        Returns:
            None.
        """
        self._name = name
        self.events = events
        self.fail_start = fail_start
        self.fail_stop = fail_stop

    @property
    def name(self) -> str:
        """Return the stable fake service name.

        Returns:
            str: Configured name.
        """
        return self._name

    async def start(self) -> None:
        """Record startup and optionally fail.

        Returns:
            None.

        Raises:
            RuntimeError: When ``fail_start`` is enabled.

        Side Effects:
            Appends one start event.
        """
        self.events.append(f"start:{self.name}")
        if self.fail_start:
            raise RuntimeError("configured start failure")

    async def stop(self) -> None:
        """Record shutdown and optionally fail.

        Returns:
            None.

        Raises:
            RuntimeError: When ``fail_stop`` is enabled.

        Side Effects:
            Appends one stop event.
        """
        self.events.append(f"stop:{self.name}")
        if self.fail_stop:
            raise RuntimeError("configured stop failure")


def test_background_services_start_in_order_and_stop_in_reverse() -> None:
    """Ensure selected-app declaration order has deterministic ownership.

    Returns:
        None.
    """
    events: list[str] = []
    first = _Service("first", events)
    second = _Service("second", events, fail_stop=True)
    selected_app = SimpleNamespace(
        background_service_factories=(lambda: first, lambda: second)
    )

    services = asyncio.run(_start_background_services(selected_app))
    asyncio.run(_stop_background_services(services))

    assert events == [
        "start:first",
        "start:second",
        "stop:second",
        "stop:first",
    ]


def test_background_service_start_failure_cleans_up_started_services() -> None:
    """Ensure partial startup stops already-owned services before re-raising.

    Returns:
        None.
    """
    events: list[str] = []
    first = _Service("first", events)
    failing = _Service("failing", events, fail_start=True)
    selected_app = SimpleNamespace(
        background_service_factories=(lambda: first, lambda: failing)
    )

    with pytest.raises(RuntimeError, match="configured start failure"):
        asyncio.run(_start_background_services(selected_app))

    assert events == ["start:first", "start:failing", "stop:first"]
