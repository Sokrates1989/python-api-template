"""
Application composition contracts for the backend multi-app monorepo.

This module defines the shared structures used to register app-owned route
families and app metadata while keeping shared infrastructure reusable.
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter


@dataclass(frozen=True)
class RouteRegistration:
    """
    Describe one router mounted by an app definition.

    Args:
        router (APIRouter): Router instance exposed by the application module.
        external_prefix (str): Optional prefix applied when the router is
            mounted into the FastAPI application.
        public_prefix (str): Optional externally visible route prefix used for
            health reporting and startup diagnostics.

    Returns:
        None: Dataclass instances are used as immutable router metadata.

    Side Effects:
        None.
    """

    router: APIRouter
    external_prefix: str = ""
    public_prefix: str = ""

    def resolved_public_prefix(self) -> str:
        """
        Return the externally visible prefix for this router registration.

        Args:
            None.

        Returns:
            str: The public route prefix exposed by the registration.

        Side Effects:
            None.
        """
        if self.public_prefix:
            return self.public_prefix

        combined_prefix = f"{self.external_prefix}{self.router.prefix}"
        return combined_prefix or "/"


@dataclass(frozen=True)
class BackendAppDefinition:
    """
    Describe one backend app hosted inside the multi-app monorepo.

    Args:
        app_id (str): Stable backend app identifier.
        display_name (str): Human-readable name for logs and diagnostics.
        backend_data_profile (str): Expected backend/database profile for the
            app module.
        route_registrations (tuple[RouteRegistration, ...]): Routers exposed by
            the app module.
        exposes_sync_routes (bool): Whether the app intentionally publishes
            sync endpoints.

    Returns:
        None: Dataclass instances are used as immutable app manifests.

    Side Effects:
        None.
    """

    app_id: str
    display_name: str
    backend_data_profile: str
    route_registrations: tuple[RouteRegistration, ...]
    exposes_sync_routes: bool = False

    def registered_route_prefixes(self) -> tuple[str, ...]:
        """
        Return all externally visible route prefixes for this app definition.

        Args:
            None.

        Returns:
            tuple[str, ...]: Public route prefixes registered for the app.

        Side Effects:
            None.
        """
        return tuple(
            route_registration.resolved_public_prefix()
            for route_registration in self.route_registrations
        )

    def find_route_prefix(self, fragment: str) -> str | None:
        """
        Return the first registered route prefix containing a fragment.

        Args:
            fragment (str): Route fragment to search for.

        Returns:
            str | None: The first matching route prefix, or `None` when no
            registered prefix contains the fragment.

        Side Effects:
            None.
        """
        normalized_fragment = fragment.strip()
        for route_prefix in self.registered_route_prefixes():
            if normalized_fragment in route_prefix:
                return route_prefix
        return None
