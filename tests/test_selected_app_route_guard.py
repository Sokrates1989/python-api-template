"""Unit tests for the exact selected-app route-prefix guard."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = REPOSITORY_ROOT / "tools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from selected_app_route_guard import (  # noqa: E402
    SelectedAppRouteGuardError,
    assert_allowed_routes,
    is_forbidden_api_route,
    normalize_route_path,
)


class SelectedAppRouteGuardTests(unittest.TestCase):
    """Prove exact normalization and forbidden-prefix behavior."""

    def test_normalization_handles_urls_slashes_and_dot_segments(self) -> None:
        """Canonicalize framework-like route variants deterministically."""
        self.assertEqual(normalize_route_path("https://example.test//v1/./slots/"), "/v1/slots")
        self.assertEqual(normalize_route_path(r"\\v1\\slots"), "/v1/slots")
        self.assertEqual(normalize_route_path("/v1/old/../slots"), "/v1/slots")

    def test_api_predicate_rejects_only_exact_or_descendant_paths(self) -> None:
        """Enforce the global predicate after canonical normalization."""
        rejected = ("/api", "/api/", "/api/v1", "/%61pi/v1", "//api//v1")
        allowed = ("/", "/v1/api", "/apis", "/API/v1")
        self.assertTrue(all(is_forbidden_api_route(path) for path in rejected))
        self.assertTrue(all(not is_forbidden_api_route(path) for path in allowed))

    def test_product_prefix_guard_rejects_detached_records_surface(self) -> None:
        """Reject the removed neutral fixture while retaining product routes."""
        with self.assertRaises(SelectedAppRouteGuardError):
            assert_allowed_routes(
                ("/health", "/records/{record_id}"),
                forbidden_prefixes=("/records",),
            )
        self.assertEqual(
            assert_allowed_routes(("/health", "/v1/me/identity"), ("/records",)),
            ("/health", "/v1/me/identity"),
        )


if __name__ == "__main__":
    unittest.main()
