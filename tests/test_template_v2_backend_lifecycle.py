"""Tests for Python-owned Template V2 backend managed lifecycle operations."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from template_v2.backend_foundation_contract import validate_backend_foundation
from template_v2.backend_lifecycle import execute_backend_lifecycle
from template_v2.backend_lifecycle_models import (
    APPLY_INTENT,
    CREATE_INTENT,
    DETACH_INTENT,
    ROLLBACK_CREATE_INTENT,
    BackendLifecycleError,
)
from template_v2.backend_lifecycle_planning import (
    build_backend_lifecycle_plan,
    load_backend_lifecycle_context,
)
from template_v2.backend_lifecycle_transaction import create_backend_target


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class BackendLifecycleTest(unittest.TestCase):
    """Verify read-only defaults, managed ownership, and exact rollback."""

    def _write_bundle(self, root: Path, *, readme: str = "generated v1\n", route: str = "") -> Path:
        """Write one complete ownership-bearing desired backend bundle.

        Args:
            root: Temporary parent receiving the bundle directory.
            readme: Generated README content.
            route: Optional route module content.

        Returns:
            Complete desired bundle root.
        """

        bundle = root / "bundle"
        identity = validate_backend_foundation(REPOSITORY_ROOT)
        foundation = {
            "contract_id": identity.contract_id,
            "contract_version": identity.contract_version,
            "foundation_revision": identity.foundation_revision,
            "manifest_sha256": identity.manifest_sha256,
            "source_file_count": identity.source_file_count,
            "source_sha256": identity.source_sha256,
        }
        contents = {
            ".template_v2/backend_foundation.json": json.dumps(foundation, indent=2, sort_keys=True) + "\n",
            "README.md": readme,
            "config/app_metadata.py": 'APP_ID = "sample_connected"\n',
            "definition.py": "route_registrations = ()\nmigration_version_locations = ()\n",
        }
        if route:
            contents["routes/records.py"] = route
        records = []
        for relative_path, content in sorted(contents.items(), key=lambda item: item[0].casefold()):
            encoded = content.encode("utf-8")
            target = bundle.joinpath(*relative_path.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(encoded)
            records.append(
                {
                    "path": relative_path,
                    "bytes": len(encoded),
                    "sha256": hashlib.sha256(encoded).hexdigest(),
                    "classification": "generated",
                    "detached": False,
                }
            )
        ownership = {
            "generator_version": 1,
            "ownership_schema_version": 1,
            "blueprint_schema_version": 1,
            "transaction_schema_version": 1,
            "recipes": [
                {"recipe_id": "connected_api", "version": "1.0.0"},
                {"recipe_id": "keycloak_auth", "version": "1.0.0"},
            ],
            "files": records,
        }
        ownership_path = bundle / ".template_v2" / "ownership.json"
        ownership_path.write_text(json.dumps(ownership, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return bundle

    def _context(self, repository: Path, bundle: Path):
        """Load the standard sample target lifecycle context.

        Args:
            repository: Backend publication repository.
            bundle: Complete desired bundle root.

        Returns:
            Validated lifecycle context.
        """

        return load_backend_lifecycle_context(
            REPOSITORY_ROOT,
            repository,
            bundle,
            "app/apps/sample_connected",
        )

    def test_create_and_noop_apply_require_exact_authority(self) -> None:
        """Keep planning read-only and enforce exact create/apply intents."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "backend"
            (repository / "app" / "apps").mkdir(parents=True)
            bundle = self._write_bundle(root)
            before = tuple(repository.rglob("*"))
            plan = json.loads(
                execute_backend_lifecycle(
                    "plan",
                    template_root=REPOSITORY_ROOT,
                    repository_root=repository,
                    bundle_root=bundle,
                    target_directory="app/apps/sample_connected",
                )
            )
            self.assertEqual(tuple(repository.rglob("*")), before)
            self.assertEqual(plan["action"], "create")
            with self.assertRaisesRegex(BackendLifecycleError, "write_intent"):
                execute_backend_lifecycle(
                    "create",
                    template_root=REPOSITORY_ROOT,
                    repository_root=repository,
                    bundle_root=bundle,
                    target_directory="app/apps/sample_connected",
                    expected_plan_sha256=plan["plan_sha256"],
                    write_intent="wrong",
                )
            created = json.loads(
                execute_backend_lifecycle(
                    "create",
                    template_root=REPOSITORY_ROOT,
                    repository_root=repository,
                    bundle_root=bundle,
                    target_directory="app/apps/sample_connected",
                    expected_plan_sha256=plan["plan_sha256"],
                    write_intent=CREATE_INTENT,
                )
            )
            self.assertTrue(created["writes"])
            self.assertTrue((repository / ".template_v2" / "apps" / "sample_connected.json").is_file())
            self.assertFalse(any(".env" in path.name for path in repository.rglob("*")))
            noop_plan = json.loads(
                execute_backend_lifecycle(
                    "reconcile",
                    template_root=REPOSITORY_ROOT,
                    repository_root=repository,
                    bundle_root=bundle,
                    target_directory="app/apps/sample_connected",
                )
            )
            self.assertEqual(noop_plan["action"], "noop")
            applied = json.loads(
                execute_backend_lifecycle(
                    "apply",
                    template_root=REPOSITORY_ROOT,
                    repository_root=repository,
                    bundle_root=bundle,
                    target_directory="app/apps/sample_connected",
                    expected_plan_sha256=noop_plan["plan_sha256"],
                    write_intent=APPLY_INTENT,
                )
            )
            self.assertFalse(applied["writes"])

    def test_drift_detach_and_apply_preserve_handwritten_and_unowned_paths(self) -> None:
        """Require a detach decision, then preserve product-owned backend code."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "backend"
            (repository / "app" / "apps").mkdir(parents=True)
            bundle = self._write_bundle(root)
            create_plan = build_backend_lifecycle_plan(self._context(repository, bundle), "plan")
            execute_backend_lifecycle(
                "create",
                template_root=REPOSITORY_ROOT,
                repository_root=repository,
                bundle_root=bundle,
                target_directory="app/apps/sample_connected",
                expected_plan_sha256=create_plan.plan_sha256,
                write_intent=CREATE_INTENT,
            )
            target = repository / "app" / "apps" / "sample_connected"
            (target / "README.md").write_text("customer-owned\n", encoding="utf-8")
            handwritten_route = target / "routes" / "custom.py"
            handwritten_route.parent.mkdir()
            handwritten_route.write_text("router = None\n", encoding="utf-8")
            drift_plan = build_backend_lifecycle_plan(self._context(repository, bundle), "reconcile")
            self.assertEqual(drift_plan.drifted_paths, ("README.md",))
            with self.assertRaisesRegex(BackendLifecycleError, "restore or detach"):
                execute_backend_lifecycle(
                    "apply",
                    template_root=REPOSITORY_ROOT,
                    repository_root=repository,
                    bundle_root=bundle,
                    target_directory="app/apps/sample_connected",
                    expected_plan_sha256=drift_plan.plan_sha256,
                    write_intent=APPLY_INTENT,
                )
            detach_plan = build_backend_lifecycle_plan(
                self._context(repository, bundle),
                "detach",
                ("README.md",),
            )
            public_detach_plan = json.loads(
                execute_backend_lifecycle(
                    "plan",
                    template_root=REPOSITORY_ROOT,
                    repository_root=repository,
                    bundle_root=bundle,
                    target_directory="app/apps/sample_connected",
                    detach_paths=("README.md",),
                )
            )
            self.assertEqual(
                public_detach_plan["plan_sha256"],
                detach_plan.plan_sha256,
            )
            execute_backend_lifecycle(
                "detach",
                template_root=REPOSITORY_ROOT,
                repository_root=repository,
                bundle_root=bundle,
                target_directory="app/apps/sample_connected",
                expected_plan_sha256=detach_plan.plan_sha256,
                write_intent=DETACH_INTENT,
                detach_paths=("README.md",),
            )
            updated_bundle = self._write_bundle(root / "updated", readme="generated v2\n")
            update_plan = build_backend_lifecycle_plan(self._context(repository, updated_bundle), "reconcile")
            execute_backend_lifecycle(
                "apply",
                template_root=REPOSITORY_ROOT,
                repository_root=repository,
                bundle_root=updated_bundle,
                target_directory="app/apps/sample_connected",
                expected_plan_sha256=update_plan.plan_sha256,
                write_intent=APPLY_INTENT,
            )
            self.assertEqual((target / "README.md").read_text(encoding="utf-8"), "customer-owned\n")
            self.assertEqual(handwritten_route.read_text(encoding="utf-8"), "router = None\n")
            (target / "README.md").unlink()
            for _attempt in range(2):
                preserve_absence = build_backend_lifecycle_plan(
                    self._context(repository, updated_bundle),
                    "reconcile",
                )
                execute_backend_lifecycle(
                    "apply",
                    template_root=REPOSITORY_ROOT,
                    repository_root=repository,
                    bundle_root=updated_bundle,
                    target_directory="app/apps/sample_connected",
                    expected_plan_sha256=preserve_absence.plan_sha256,
                    write_intent=APPLY_INTENT,
                )
                self.assertFalse((target / "README.md").exists())

    def test_failure_cancellation_collision_stale_plan_and_exact_rollback(self) -> None:
        """Rollback partial publication and reject unsafe lifecycle state."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "backend"
            (repository / "app" / "apps").mkdir(parents=True)
            bundle = self._write_bundle(root)
            context = self._context(repository, bundle)
            plan = build_backend_lifecycle_plan(context, "plan")

            def fail_registration(event: str) -> None:
                """Inject one failure after target publication.

                Args:
                    event: Current transaction event.

                Returns:
                    None unless the registration boundary is reached.

                Raises:
                    RuntimeError: At the intended rollback checkpoint.
                """

                if event == "before_registration_publish":
                    raise RuntimeError("injected")

            with self.assertRaisesRegex(BackendLifecycleError, "rolled back"):
                create_backend_target(
                    context,
                    plan,
                    expected_plan_sha256=plan.plan_sha256,
                    write_intent=CREATE_INTENT,
                    observer=fail_registration,
                )
            self.assertFalse(context.target_path.exists())
            self.assertFalse(context.registration_path.exists())

            def cancel(event: str) -> None:
                """Inject cancellation before registration publication.

                Args:
                    event: Current transaction event.

                Raises:
                    KeyboardInterrupt: At the intended cancellation checkpoint.
                """

                if event == "before_registration_publish":
                    raise KeyboardInterrupt()

            with self.assertRaises(KeyboardInterrupt):
                create_backend_target(
                    self._context(repository, bundle),
                    plan,
                    expected_plan_sha256=plan.plan_sha256,
                    write_intent=CREATE_INTENT,
                    observer=cancel,
                )
            self.assertFalse(context.target_path.exists())
            with self.assertRaisesRegex(BackendLifecycleError, "stale"):
                execute_backend_lifecycle(
                    "create",
                    template_root=REPOSITORY_ROOT,
                    repository_root=repository,
                    bundle_root=bundle,
                    target_directory="app/apps/sample_connected",
                    expected_plan_sha256="0" * 64,
                    write_intent=CREATE_INTENT,
                )
            created_plan = build_backend_lifecycle_plan(self._context(repository, bundle), "plan")
            execute_backend_lifecycle(
                "create",
                template_root=REPOSITORY_ROOT,
                repository_root=repository,
                bundle_root=bundle,
                target_directory="app/apps/sample_connected",
                expected_plan_sha256=created_plan.plan_sha256,
                write_intent=CREATE_INTENT,
            )
            rollback_context = self._context(repository, bundle)
            rollback_plan = build_backend_lifecycle_plan(rollback_context, "rollback-create")
            execute_backend_lifecycle(
                "rollback-create",
                template_root=REPOSITORY_ROOT,
                repository_root=repository,
                bundle_root=bundle,
                target_directory="app/apps/sample_connected",
                expected_plan_sha256=rollback_plan.plan_sha256,
                write_intent=ROLLBACK_CREATE_INTENT,
            )
            self.assertFalse(rollback_context.target_path.exists())
            self.assertFalse(rollback_context.registration_path.exists())
            shutil.copytree(bundle, rollback_context.target_path)
            with self.assertRaisesRegex(BackendLifecycleError, "state disagree"):
                build_backend_lifecycle_plan(self._context(repository, bundle), "plan")

    def test_registration_drift_fails_before_lifecycle_decision(self) -> None:
        """Reject altered selected-app metadata before any managed mutation."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "backend"
            (repository / "app" / "apps").mkdir(parents=True)
            bundle = self._write_bundle(root)
            create_plan = build_backend_lifecycle_plan(
                self._context(repository, bundle),
                "plan",
            )
            execute_backend_lifecycle(
                "create",
                template_root=REPOSITORY_ROOT,
                repository_root=repository,
                bundle_root=bundle,
                target_directory="app/apps/sample_connected",
                expected_plan_sha256=create_plan.plan_sha256,
                write_intent=CREATE_INTENT,
            )
            registration = (
                repository / ".template_v2" / "apps" / "sample_connected.json"
            )
            document = json.loads(registration.read_text(encoding="utf-8"))
            document["app_id"] = "altered_registration"
            registration.write_text(
                json.dumps(document, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(BackendLifecycleError, "metadata is invalid"):
                build_backend_lifecycle_plan(
                    self._context(repository, bundle),
                    "reconcile",
                )

    def test_forbidden_api_prefix_fails_before_any_write(self) -> None:
        """Reject redundant API-service route prefixes in desired backend code."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "backend"
            (repository / "app" / "apps").mkdir(parents=True)
            bundle = self._write_bundle(
                root,
                route='from fastapi import APIRouter\nrouter = APIRouter(prefix="/api/records")\n',
            )

            with self.assertRaisesRegex(BackendLifecycleError, "forbidden /api"):
                self._context(repository, bundle)
            self.assertEqual(tuple((repository / "app" / "apps").iterdir()), ())


if __name__ == "__main__":
    unittest.main()
