"""Reusable lifecycle contract for selected-app background services.

The FastAPI lifespan owns service start/stop ordering while individual backend
apps own factories and product configuration. Snapshots must contain only
privacy-safe operational metadata suitable for the shared health response.
"""

from __future__ import annotations

from typing import Any, Callable, Protocol


class BackgroundService(Protocol):
    """Describe one selected-app service managed by FastAPI lifespan."""

    @property
    def name(self) -> str:
        """Return the stable health-diagnostic service name.

        Returns:
            str: App-unique background service identifier.
        """
        ...

    async def start(self) -> None:
        """Start owned asynchronous work.

        Returns:
            None.

        Side Effects:
            May validate configuration and create background tasks.
        """
        ...

    async def stop(self) -> None:
        """Stop owned asynchronous work and release resources.

        Returns:
            None.

        Side Effects:
            Signals and awaits any task created by :meth:`start`.
        """
        ...

    def snapshot(self) -> dict[str, Any]:
        """Return privacy-safe health metadata.

        Returns:
            dict[str, Any]: Status/count fields without user or payload data.

        Side Effects:
            None.
        """
        ...


BackgroundServiceFactory = Callable[[], BackgroundService]
"""Factory invoked after selected-app database initialization completes."""
