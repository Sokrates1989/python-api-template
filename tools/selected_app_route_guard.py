"""Normalize and validate selected-app API route declarations.

The guard is framework-light so repository tests can prove the exact service-
root rule without starting infrastructure. Runtime callers pass FastAPI route
paths after importing the selected application.
"""

from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import unquote, urlsplit


class SelectedAppRouteGuardError(ValueError):
    """Report one or more forbidden selected-app routes."""


def normalize_route_path(route_path: str) -> str:
    """Return a canonical absolute path for a declared API route.

    Args:
        route_path: Literal route or URL-like value supplied by a framework.

    Returns:
        str: Percent-decoded, slash-normalized path without a trailing slash,
        except that the root route remains ``/``.

    Side Effects:
        None.
    """
    stripped_path = route_path.strip()
    parsed_path = (
        stripped_path
        if stripped_path.startswith(("/", "\\"))
        else urlsplit(stripped_path).path
    )
    raw_path = parsed_path.replace("\\", "/")
    decoded_path = unquote(raw_path)
    segments: list[str] = []
    for segment in decoded_path.split("/"):
        if not segment or segment == ".":
            continue
        if segment == "..":
            if segments:
                segments.pop()
            continue
        segments.append(segment)
    return f"/{'/'.join(segments)}" if segments else "/"


def is_forbidden_api_route(route_path: str) -> bool:
    """Return whether a route violates the service-root ``/api`` rule.

    Args:
        route_path: Route path before or after normalization.

    Returns:
        bool: ``True`` only when the normalized path equals ``/api`` or begins
        with ``/api/``.

    Side Effects:
        None.
    """
    normalized = normalize_route_path(route_path)
    return normalized == "/api" or normalized.startswith("/api/")


def is_within_prefix(route_path: str, forbidden_prefix: str) -> bool:
    """Return whether a route equals or descends from a forbidden prefix.

    Args:
        route_path: Candidate route path.
        forbidden_prefix: Absolute route prefix that must be absent.

    Returns:
        bool: Whether the normalized route matches the normalized prefix.

    Side Effects:
        None.
    """
    normalized_route = normalize_route_path(route_path)
    normalized_prefix = normalize_route_path(forbidden_prefix)
    return normalized_route == normalized_prefix or normalized_route.startswith(
        f"{normalized_prefix}/"
    )


def collect_forbidden_routes(
    route_paths: Iterable[str],
    forbidden_prefixes: Iterable[str] = (),
) -> tuple[str, ...]:
    """Collect normalized routes rejected by global and app-specific policy.

    Args:
        route_paths: Framework route paths to inspect.
        forbidden_prefixes: Additional exact-or-descendant prefixes to reject.

    Returns:
        tuple[str, ...]: Sorted unique forbidden paths. The tuple is empty when
        every route is service-root relative and outside additional prefixes.

    Side Effects:
        None.
    """
    normalized_prefixes = tuple(
        normalize_route_path(prefix) for prefix in forbidden_prefixes
    )
    rejected = {
        normalize_route_path(route)
        for route in route_paths
        if is_forbidden_api_route(route)
        or any(is_within_prefix(route, prefix) for prefix in normalized_prefixes)
    }
    return tuple(sorted(rejected))


def assert_allowed_routes(
    route_paths: Iterable[str],
    forbidden_prefixes: Iterable[str] = (),
) -> tuple[str, ...]:
    """Validate routes and return their normalized deterministic inventory.

    Args:
        route_paths: Framework route paths to validate.
        forbidden_prefixes: Additional product-specific prefixes to reject.

    Returns:
        tuple[str, ...]: Sorted unique normalized route inventory.

    Raises:
        SelectedAppRouteGuardError: When any forbidden route is present.

    Side Effects:
        None.
    """
    normalized_routes = tuple(sorted({normalize_route_path(path) for path in route_paths}))
    forbidden = collect_forbidden_routes(normalized_routes, forbidden_prefixes)
    if forbidden:
        raise SelectedAppRouteGuardError(
            "Forbidden API route declarations: " + ", ".join(forbidden)
        )
    return normalized_routes
