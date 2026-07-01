"""
Tests for backend app/shared route boundary contracts.

These tests cover the cleanup rules that prevent apps from inheriting broad
shared HTTP surfaces by accident and keep the Redis cache route group usable as
an explicit opt-in shared route.
"""
from __future__ import annotations

import unittest

from fastapi import HTTPException

from api.shared_routes import cache
from apps.contracts import BackendAppDefinition


class FakeCacheClient:
    """
    In-memory Redis-like client used by cache route tests.

    Attributes:
        values (dict[str, object]): Stored key/value pairs returned by ``get``
            and updated by ``set``.

    Methods:
        get: Return a stored value for one key.
        set: Store a value for one key.
    """

    def __init__(self, values: dict[str, object] | None = None) -> None:
        """
        Initialize the fake cache.

        Args:
            values (dict[str, object] | None): Optional initial key/value map.

        Returns:
            None.

        Side Effects:
            Copies the provided values into the fake cache instance.
        """
        self.values = dict(values or {})

    def get(self, key: str) -> object | None:
        """
        Return one cached value.

        Args:
            key (str): Cache key to read.

        Returns:
            object | None: Stored value, or None when the key is missing.

        Side Effects:
            None.
        """
        return self.values.get(key)

    def set(self, key: str, value: str) -> None:
        """
        Store one cache value.

        Args:
            key (str): Cache key to write.
            value (str): Cache value to store.

        Returns:
            None.

        Side Effects:
            Mutates the fake cache value map.
        """
        self.values[key] = value


class SharedRouteBoundaryTests(unittest.TestCase):
    """
    Verify shared route defaults and cache route helper behavior.

    Methods:
        test_backend_app_definition_defaults_to_no_shared_routes: Ensures app
            definitions do not inherit demo/test route groups.
        test_cache_get_decodes_bytes: Ensures cache GET returns string payloads.
        test_cache_get_missing_key_raises_not_found: Ensures missing cache keys
            map to HTTP 404.
        test_cache_set_writes_value: Ensures cache POST writes through the
            injected client.
    """

    def test_backend_app_definition_defaults_to_no_shared_routes(self) -> None:
        """
        Ensure backend app definitions do not inherit shared route groups.

        Args:
            None.

        Returns:
            None.

        Side Effects:
            None.
        """
        definition = BackendAppDefinition(
            app_id="unit_test",
            display_name="Unit Test",
            backend_data_profile="none",
            route_registrations=(),
        )

        self.assertEqual(definition.shared_route_groups, ())

    def test_cache_get_decodes_bytes(self) -> None:
        """
        Ensure cache GET decodes Redis byte values.

        Args:
            None.

        Returns:
            None.

        Side Effects:
            None.
        """
        result = cache.get_cache("demo", cache_client=FakeCacheClient({"demo": b"value"}))

        self.assertEqual(result, {"key": "demo", "value": "value"})

    def test_cache_get_missing_key_raises_not_found(self) -> None:
        """
        Ensure cache GET returns HTTP 404 for missing keys.

        Args:
            None.

        Returns:
            None.

        Raises:
            AssertionError: When the route does not raise HTTP 404.

        Side Effects:
            None.
        """
        with self.assertRaises(HTTPException) as raised:
            cache.get_cache("missing", cache_client=FakeCacheClient())

        self.assertEqual(raised.exception.status_code, 404)

    def test_cache_set_writes_value(self) -> None:
        """
        Ensure cache POST writes through the provided client.

        Args:
            None.

        Returns:
            None.

        Side Effects:
            Mutates the fake cache client used by the assertion.
        """
        cache_client = FakeCacheClient()
        result = cache.set_cache("demo", "value", cache_client=cache_client)

        self.assertEqual(cache_client.values["demo"], "value")
        self.assertEqual(result, {"message": "Stored key 'demo' with value 'value'"})
