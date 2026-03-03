import asyncio
import unittest

from api.settings import settings
from backend.database import close_database
from backend.database.init_db import initialize_database
from backend.database.migrations import run_migrations


class MigrationSmokeTests(unittest.TestCase):
    def test_run_migrations_smoke_for_sql_backends(self):
        if not settings.is_sql_database():
            self.skipTest("Migration smoke test only applies to SQL backends")

        init_result = asyncio.run(initialize_database())
        self.assertEqual(init_result.get("status"), "success")

        try:
            self.assertTrue(run_migrations(fail_on_error=True))
        finally:
            asyncio.run(close_database())
