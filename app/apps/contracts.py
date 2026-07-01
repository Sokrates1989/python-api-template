"""
Application composition contracts for the backend multi-app monorepo.

This module defines the shared structures used to register app-owned route
families and app metadata while keeping shared infrastructure reusable.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
class OpenApiSecurityScheme:
    """
    Describe one OpenAPI security scheme owned by a backend app.

    Args:
        name (str): Component name used by OpenAPI security requirements.
        scheme (dict[str, Any]): OpenAPI security scheme object.

    Returns:
        None: Dataclass instances are used as immutable OpenAPI metadata.

    Side Effects:
        None.
    """

    name: str
    scheme: dict[str, Any]


@dataclass(frozen=True)
class RouteSecurityRequirement:
    """
    Describe OpenAPI security requirements for a route family.

    Args:
        path_prefix (str): Route path prefix to match, such as `/v1/notify`.
        requirement (dict[str, list[str]]): OpenAPI security requirement object.
        methods (tuple[str, ...]): Lowercase HTTP methods the requirement applies
            to. Defaults to common mutation and read methods.
        exact_path (bool): When True, only the exact path matches.

    Returns:
        None: Dataclass instances are used as immutable OpenAPI metadata.

    Side Effects:
        None.
    """

    path_prefix: str
    requirement: dict[str, list[str]]
    methods: tuple[str, ...] = ("get", "post", "delete", "put", "patch")
    exact_path: bool = False

    def matches_path(self, path: str) -> bool:
        """
        Return whether an OpenAPI path matches this requirement.

        Args:
            path (str): OpenAPI path key to evaluate.

        Returns:
            bool: True when the path should receive this security requirement.

        Side Effects:
            None.
        """
        if self.exact_path:
            return path == self.path_prefix
        return path.startswith(self.path_prefix)


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
        migration_version_locations (tuple[str, ...]): App-owned Alembic
            version directories, relative to ``app/apps/<app_id>`` unless
            absolute. These run only when this app is selected.
        exposes_sync_routes (bool): Whether the app intentionally publishes
            sync endpoints.
        requires_database (bool): Whether the app requires database
            initialization. Defaults to True for backward compatibility.
        requires_redis (bool): Whether the app requires Redis connection.
            Defaults to True for backward compatibility.
        include_shared_routes (bool): Whether to mount explicitly selected
            shared route groups. Defaults to True, but no shared routes are
            selected unless ``shared_route_groups`` names them.
        shared_route_groups (tuple[str, ...]): Shared route group names this
            app exposes when include_shared_routes is True. Defaults to an
            empty tuple so each app must opt in to shared HTTP surfaces.
        openapi_security_schemes (tuple[OpenApiSecurityScheme, ...]): Security
            schemes owned by this app and shown in Swagger UI only when this app
            is selected.
        openapi_route_security (tuple[RouteSecurityRequirement, ...]): Route
            security requirements owned by this app.

    Returns:
        None: Dataclass instances are used as immutable app manifests.

    Side Effects:
        None.
    """

    app_id: str
    display_name: str
    backend_data_profile: str
    route_registrations: tuple[RouteRegistration, ...]
    migration_version_locations: tuple[str, ...] = ()
    exposes_sync_routes: bool = False
    requires_database: bool = True
    requires_redis: bool = True
    include_shared_routes: bool = True
    shared_route_groups: tuple[str, ...] = ()
    openapi_security_schemes: tuple[OpenApiSecurityScheme, ...] = ()
    openapi_route_security: tuple[RouteSecurityRequirement, ...] = ()

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
