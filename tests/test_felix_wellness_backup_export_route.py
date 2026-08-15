"""Contract tests for the complete Felix wellness backup export route."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from apps.felix.routes.wellness import get_sync_export


class _BackupExportService:
    """Capture the row bounds requested by the route."""

    def __init__(self) -> None:
        """Create an empty call capture."""
        self.call: tuple[str, int, int] | None = None

    async def get_sync_bootstrap(
        self,
        user_id: str,
        diary_limit: int = 50,
        checkin_limit: int = 50,
    ) -> dict[str, object]:
        """Return one valid empty snapshot and record requested limits.

        Args:
            user_id (str): Authenticated owner identifier.
            diary_limit (int): Requested diary row bound.
            checkin_limit (int): Requested check-in row bound.

        Returns:
            dict[str, object]: Provider-normalized bootstrap result.
        """
        self.call = (user_id, diary_limit, checkin_limit)
        return {
            "status": "success",
            "data": {
                "server_timestamp": "2026-08-15T12:00:00Z",
                "activity_categories": [],
                "activities": [],
                "diary_entries": [],
                "checkins": [],
            },
        }


class FelixWellnessBackupExportRouteTests(unittest.TestCase):
    """Verify full-history bounds stay separate from normal bootstrap reads."""

    def test_export_requests_one_over_the_portable_row_limit(self) -> None:
        """The client must be able to detect a 20,001st record."""
        service = _BackupExportService()

        with patch(
            "apps.felix.routes.wellness.get_service",
            return_value=service,
        ):
            response = asyncio.run(get_sync_export("verified-owner"))

        self.assertEqual(service.call, ("verified-owner", 20_001, 20_001))
        self.assertEqual(response.status, "success")
        self.assertEqual(response.data.checkins, [])


if __name__ == "__main__":
    unittest.main()
