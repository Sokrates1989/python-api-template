"""Validate the exact runtime route surface for one selected backend app."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from selected_app_route_guard import (
    SelectedAppRouteGuardError,
    assert_allowed_routes,
)


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the selected-app route-guard command parser.

    Returns:
        argparse.ArgumentParser: Parser accepting an expected app identity and
        optional product-specific forbidden prefixes.

    Side Effects:
        None.
    """
    parser = argparse.ArgumentParser(
        description="Reject /api-prefixed and explicitly forbidden API routes.",
    )
    parser.add_argument("--expected-app-id", required=True)
    parser.add_argument("--forbid-prefix", action="append", default=[])
    return parser


def collect_application_routes(application: object) -> tuple[str, ...]:
    """Extract declared path strings from a FastAPI-compatible application.

    Args:
        application: Object exposing an iterable ``routes`` attribute.

    Returns:
        tuple[str, ...]: Route paths in framework declaration order.

    Raises:
        SelectedAppRouteGuardError: When the object has no usable route list.

    Side Effects:
        None.
    """
    raw_routes = getattr(application, "routes", None)
    if raw_routes is None:
        raise SelectedAppRouteGuardError("Application does not expose routes.")
    route_paths = tuple(
        str(path)
        for route in raw_routes
        if (path := getattr(route, "path", None)) is not None
    )
    if not route_paths:
        raise SelectedAppRouteGuardError("Application route inventory is empty.")
    return route_paths


def main(argv: Sequence[str] | None = None) -> int:
    """Validate the selected runtime and print a credential-free summary.

    Args:
        argv: Optional argument vector used by tests; process arguments are
        parsed when omitted.

    Returns:
        int: Zero on success and one for identity or route violations.

    Side Effects:
        Imports the selected FastAPI application and writes sanitized JSON or a
        stable error message.
    """
    arguments = build_argument_parser().parse_args(argv)
    try:
        from api.settings import settings
        from main import app

        observed_app_id = settings.normalized_app_profile()
        if observed_app_id != arguments.expected_app_id:
            raise SelectedAppRouteGuardError(
                "Selected app mismatch: "
                f"expected={arguments.expected_app_id} observed={observed_app_id}"
            )
        routes = assert_allowed_routes(
            collect_application_routes(app),
            arguments.forbid_prefix,
        )
    except (ImportError, SelectedAppRouteGuardError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "app_id": observed_app_id,
                "forbidden_route_count": 0,
                "route_count": len(routes),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
