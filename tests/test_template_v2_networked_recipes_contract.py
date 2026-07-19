"""Standard-library tests for the Template V2 B4 recipe catalog."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from template_v2.networked_recipes_contract import (
    CONTRACT_RELATIVE_PATH,
    NetworkedRecipesContractError,
    validate_networked_recipes_contract,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class NetworkedRecipesContractTest(unittest.TestCase):
    """Verify catalog identity, safety, and honest implementation status."""

    def _copy_contract(self, destination: Path) -> Path:
        """Copy the JSON-only catalog into an isolated repository root.

        Args:
            destination: Empty temporary root.

        Returns:
            Prepared isolated contract root.
        """

        source = REPOSITORY_ROOT.joinpath(*CONTRACT_RELATIVE_PATH.split("/"))
        target = destination.joinpath(*CONTRACT_RELATIVE_PATH.split("/"))
        target.parent.mkdir(parents=True)
        shutil.copyfile(source, target)
        return destination

    def test_canonical_catalog_declares_all_fixed_b4_recipes(self) -> None:
        """Expose every planned recipe with deterministic removal coverage."""

        catalog = validate_networked_recipes_contract(REPOSITORY_ROOT)

        self.assertEqual(catalog.contract_version, 1)
        self.assertEqual(catalog.catalog_revision, "0.1.0")
        self.assertEqual(
            tuple(recipe.backend_recipe_id for recipe in catalog.recipes),
            (
                "hybrid_sync",
                "authenticated_web_push",
                "ai_chat",
                "account_erasure",
            ),
        )
        self.assertTrue(
            all(recipe.implementation_status == "contract_only" for recipe in catalog.recipes)
        )
        for recipe in catalog.recipes:
            self.assertTrue(recipe.routes)
            self.assertTrue(
                set((*recipe.migration_paths, *recipe.service_paths)).issubset(
                    recipe.removal_paths
                )
            )
            self.assertFalse(
                any(route.path == "/api" or route.path.startswith("/api/") for route in recipe.routes)
            )

    def test_redundant_api_prefix_fails_closed(self) -> None:
        """Reject a route that would collide with API-domain proxy routers."""

        with tempfile.TemporaryDirectory() as directory:
            root = self._copy_contract(Path(directory))
            path = root.joinpath(*CONTRACT_RELATIVE_PATH.split("/"))
            document = json.loads(path.read_text(encoding="utf-8"))
            document["recipes"][0]["routes"][0]["path"] = "/api/sync/push"
            path.write_text(json.dumps(document), encoding="utf-8")

            with self.assertRaisesRegex(
                NetworkedRecipesContractError, "unsafe service route"
            ):
                validate_networked_recipes_contract(root)

    def test_incomplete_removal_boundary_fails_closed(self) -> None:
        """Reject a recipe that would leave one generated service behind."""

        with tempfile.TemporaryDirectory() as directory:
            root = self._copy_contract(Path(directory))
            path = root.joinpath(*CONTRACT_RELATIVE_PATH.split("/"))
            document = json.loads(path.read_text(encoding="utf-8"))
            document["recipes"][2]["removal_paths"].remove("routes/ai_chat.py")
            path.write_text(json.dumps(document), encoding="utf-8")

            with self.assertRaisesRegex(
                NetworkedRecipesContractError, "must cover migrations and services"
            ):
                validate_networked_recipes_contract(root)


if __name__ == "__main__":
    unittest.main()
