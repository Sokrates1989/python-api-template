"""Regression tests for privacy-safe production HTTP diagnostics.

The suite verifies that normal request outcomes and validation failures reach
the application logger without concrete account paths, query values, request
bodies, or invalid email values.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from fastapi import Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, EmailStr, ValidationError

from api.middleware.logging import (
    log_request_outcome,
    log_request_validation_failure,
)


class _EmailPayload(BaseModel):
    """Minimal validated request used by the 422 logging test.

    Attributes:
        email: Syntactically deliverable email address.
    """

    email: EmailStr


def _request(
    *,
    method: str,
    path: str,
    route_template: str,
    query: str = "",
) -> Request:
    """Create one routed Starlette request without an HTTP client dependency.

    Args:
        method: HTTP method supplied to middleware diagnostics.
        path: Concrete request path that must remain private.
        route_template: Safe declared route pattern expected in logs.
        query: Optional concrete query string that must remain private.

    Returns:
        Request with the minimum complete ASGI scope used by the middleware.
    """

    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "https",
            "path": path,
            "raw_path": path.encode("utf-8"),
            "query_string": query.encode("utf-8"),
            "root_path": "",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("api.example.com", 443),
            "route": SimpleNamespace(path=route_template),
        }
    )


class HttpLoggingMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    """Protect production request visibility and privacy boundaries."""

    async def test_completion_uses_route_template_not_concrete_path(
        self,
    ) -> None:
        """Log a factual 404 without exposing its account identifier.

        Returns:
            Nothing after asserting the captured production log record.
        """

        request = _request(
            method="GET",
            path="/users/private-owner-123",
            route_template="/users/{user_id}",
            query="diagnostic=private-value",
        )

        async def return_not_found(_request: Request) -> Response:
            """Return factual absence to the middleware under test.

            Args:
                _request: Routed request; its concrete values remain unused.

            Returns:
                Empty HTTP 404 response.
            """

            return Response(status_code=404)

        with self.assertLogs("api.middleware.request", level="INFO") as logs:
            response = await log_request_outcome(request, return_not_found)

        rendered = "\n".join(logs.output)
        self.assertEqual(response.status_code, 404)
        self.assertIn('route="/users/{user_id}"', rendered)
        self.assertIn("status_code=404", rendered)
        self.assertNotIn("private-owner-123", rendered)
        self.assertNotIn("private-value", rendered)

    async def test_validation_log_omits_rejected_email_value(self) -> None:
        """Record only the invalid field and validator type for HTTP 422.

        Returns:
            Nothing after asserting response compatibility and log redaction.
        """

        rejected_email = "private-user@example.invalid"
        request = _request(
            method="POST",
            path="/users",
            route_template="/users",
        )
        try:
            _EmailPayload(email=rejected_email)
        except ValidationError as validation_error:
            request_error = RequestValidationError(
                [
                    {
                        **item,
                        "loc": ("body", *item.get("loc", ())),
                    }
                    for item in validation_error.errors()
                ]
            )
        else:  # pragma: no cover - protects the fixture's invalidity.
            self.fail("Reserved test email unexpectedly passed validation.")

        with self.assertLogs("api.middleware.request", level="WARNING") as logs:
            response = await log_request_validation_failure(
                request,
                request_error,
            )

        rendered = "\n".join(logs.output)
        self.assertEqual(response.status_code, 422)
        self.assertIn("http.request.validation_failed", rendered)
        self.assertIn("body.email", rendered)
        self.assertIn("value_error", rendered)
        self.assertNotIn(rejected_email, rendered)


if __name__ == "__main__":
    unittest.main()
