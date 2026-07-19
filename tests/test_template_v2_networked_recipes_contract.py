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
from template_v2.networked_recipe_sources import validate_networked_recipe_sources


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
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        return destination

    def test_canonical_catalog_declares_all_fixed_b4_recipes(self) -> None:
        """Expose every planned recipe with deterministic removal coverage."""

        catalog = validate_networked_recipes_contract(REPOSITORY_ROOT)

        self.assertEqual(catalog.contract_version, 3)
        self.assertEqual(catalog.catalog_revision, "0.4.0")
        self.assertEqual(
            tuple(recipe.backend_recipe_id for recipe in catalog.recipes),
            (
                "hybrid_sync",
                "authenticated_web_push",
                "ai_chat",
                "account_erasure",
            ),
        )
        self.assertEqual(
            tuple(recipe.implementation_status for recipe in catalog.recipes),
            ("renderable", "renderable", "renderable", "contract_only"),
        )
        self.assertEqual(
            catalog.recipes[1].python_dependency_profile,
            "postgresql_web_push",
        )
        self.assertEqual(
            catalog.recipes[1].python_dependencies,
            ("pywebpush>=2.3.0,<2.4.0",),
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

    def test_hybrid_sync_sources_render_complete_syntax_safe_slice(self) -> None:
        """Validate checksums and render only the promoted hybrid-sync files."""

        catalog = validate_networked_recipes_contract(REPOSITORY_ROOT)
        recipes = validate_networked_recipe_sources(REPOSITORY_ROOT, catalog)
        self.assertEqual(len(recipes), 3)
        self.assertEqual(recipes[0].backend_recipe_id, "hybrid_sync")
        self.assertEqual(recipes[0].backend_revision, "1.0.0")
        files = {
            item.relative_path: item.content
            for item in recipes[0].render("sample_app")
        }
        self.assertEqual(
            tuple(files),
            (
                "migrations/versions/sample_app_002_hybrid_sync.py",
                "models/sync_state.py",
                "repositories/sync_repository.py",
                "routes/sync.py",
                "schemas/sync.py",
                "services/sync_service.py",
            ),
        )
        rendered = b"\n".join(files.values())
        self.assertIn(b'prefix="/sync"', rendered)
        self.assertIn(b"operation_id_collision", rendered)
        self.assertIn(b"version_conflict", rendered)
        self.assertIn(b"next_cursor", rendered)
        self.assertNotIn(b"__APP_ID__", rendered)
        self.assertNotIn(b'prefix="/api/', rendered)
        for path, content in files.items():
            compile(content, path, "exec")

    def test_authenticated_web_push_sources_cover_owner_dispatch_and_cleanup(self) -> None:
        """Render the complete route, storage, delivery, and migration slice."""

        catalog = validate_networked_recipes_contract(REPOSITORY_ROOT)
        recipes = validate_networked_recipe_sources(REPOSITORY_ROOT, catalog)
        recipe = next(
            item for item in recipes if item.backend_recipe_id == "authenticated_web_push"
        )
        self.assertEqual(recipe.backend_revision, "1.0.0")
        files = {
            item.relative_path: item.content
            for item in recipe.render("sample_app")
        }
        self.assertEqual(
            tuple(files),
            (
                "migrations/versions/sample_app_003_web_push.py",
                "models/web_push_subscription.py",
                "repositories/web_push_repository.py",
                "routes/web_push.py",
                "schemas/web_push.py",
                "services/web_push_service.py",
            ),
        )
        rendered = b"\n".join(files.values())
        self.assertIn(b'prefix="/push/web"', rendered)
        self.assertIn(b'@router.put("/subscriptions"', rendered)
        self.assertIn(b"WebPushDispatchWorker", rendered)
        self.assertIn(b"WebPushDeliveryCoordinator", rendered)
        self.assertIn(b"delete_subscription(owner_subject", rendered)
        self.assertNotIn(b"@router.post", files["routes/web_push.py"])
        self.assertNotIn(b"__APP_ID__", rendered)
        self.assertNotIn(b'prefix="/api/', rendered)
        for path, content in files.items():
            compile(content, path, "exec")

    def test_ai_chat_sources_cover_consent_context_history_and_error_seams(self) -> None:
        """Render the authenticated minimized-history AI chat backend slice."""

        catalog = validate_networked_recipes_contract(REPOSITORY_ROOT)
        recipes = validate_networked_recipe_sources(REPOSITORY_ROOT, catalog)
        recipe = next(item for item in recipes if item.backend_recipe_id == "ai_chat")
        self.assertEqual(recipe.backend_revision, "1.0.0")
        files = {
            item.relative_path: item.content
            for item in recipe.render("sample_app")
        }
        self.assertEqual(
            tuple(files),
            (
                "migrations/versions/sample_app_004_ai_chat_history.py",
                "models/ai_chat_message.py",
                "repositories/ai_chat_repository.py",
                "routes/ai_chat.py",
                "schemas/ai_chat.py",
                "services/ai_chat_service.py",
            ),
        )
        rendered = b"\n".join(files.values())
        self.assertIn(b'prefix="/ai"', rendered)
        self.assertIn(b'@router.post("/chat"', rendered)
        self.assertIn(b"AiChatConsentProof", rendered)
        self.assertIn(b"RejectUnreviewedContext", rendered)
        self.assertIn(b"AllowAllAiChatQuota", rendered)
        self.assertIn(b"on_conflict_do_nothing", rendered)
        self.assertIn(b"delete_owner_data", rendered)
        self.assertNotIn(b"context_payload", files["models/ai_chat_message.py"])
        self.assertNotIn(b"provider_name", files["models/ai_chat_message.py"])
        self.assertNotIn(b"__APP_ID__", rendered)
        self.assertNotIn(b'prefix="/api/', rendered)
        for path, content in files.items():
            compile(content, path, "exec")

    def test_hybrid_sync_source_drift_fails_closed(self) -> None:
        """Reject a changed renderable template before any output is returned."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(
                REPOSITORY_ROOT / "template_v2" / "networked_recipes",
                root / "template_v2" / "networked_recipes",
            )
            self._copy_contract(root)
            source = (
                root
                / "template_v2"
                / "networked_recipes"
                / "hybrid_sync"
                / "templates"
                / "routes"
                / "sync.py.tmpl"
            )
            source.write_text(
                source.read_text(encoding="utf-8") + "\n# drift\n",
                encoding="utf-8",
            )
            catalog = validate_networked_recipes_contract(root)

            with self.assertRaisesRegex(
                NetworkedRecipesContractError,
                "checksum drifted",
            ):
                validate_networked_recipe_sources(root, catalog)

    def test_web_push_dependency_lock_drift_fails_closed(self) -> None:
        """Reject a changed selected-only Web Push lock before rendering."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(
                REPOSITORY_ROOT / "template_v2" / "networked_recipes",
                root / "template_v2" / "networked_recipes",
            )
            shutil.copytree(
                REPOSITORY_ROOT / "template_v2" / "dependency_profiles",
                root / "template_v2" / "dependency_profiles",
            )
            self._copy_contract(root)
            path = (
                root
                / "template_v2"
                / "dependency_profiles"
                / "postgresql_web_push"
                / "pdm.lock"
            )
            path.write_bytes(path.read_bytes() + b"\n")
            catalog = validate_networked_recipes_contract(root)

            with self.assertRaisesRegex(
                NetworkedRecipesContractError,
                "lock checksum drifted",
            ):
                validate_networked_recipe_sources(root, catalog)

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

    def test_web_push_dependency_profile_drift_fails_closed(self) -> None:
        """Reject Web Push promotion without its selected-only transport lock."""

        with tempfile.TemporaryDirectory() as directory:
            root = self._copy_contract(Path(directory))
            path = root.joinpath(*CONTRACT_RELATIVE_PATH.split("/"))
            document = json.loads(path.read_text(encoding="utf-8"))
            document["recipes"][1]["python_dependencies"] = []
            path.write_text(json.dumps(document), encoding="utf-8")

            with self.assertRaisesRegex(
                NetworkedRecipesContractError,
                "unsupported dependency contract",
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
