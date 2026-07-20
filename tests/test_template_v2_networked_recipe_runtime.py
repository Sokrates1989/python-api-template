"""Execute product-neutral runtime seams for generated B4 backend recipes.

AI chat and Account Erasure already have executable behavior coverage in their
focused suites. This module closes the remaining aggregate runtime gap for
hybrid sync and authenticated Web Push without contacting a provider, network,
database, worker process, or secret store.
"""

from __future__ import annotations

import asyncio
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from template_v2.networked_recipe_sources import validate_networked_recipe_sources
from template_v2.networked_recipes_contract import validate_networked_recipes_contract


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _render_service(recipe_id: str, relative_path: str) -> bytes:
    """Render one checksum-validated generated service source.

    Args:
        recipe_id: Python-owned backend recipe identifier.
        relative_path: Rendered app-relative service path.

    Returns:
        Complete rendered Python source bytes.

    Raises:
        AssertionError: If the fixed recipe or service path is absent.
    """

    catalog = validate_networked_recipes_contract(REPOSITORY_ROOT)
    recipe = next(
        item
        for item in validate_networked_recipe_sources(REPOSITORY_ROOT, catalog)
        if item.backend_recipe_id == recipe_id
    )
    return next(
        item.content
        for item in recipe.render("sample_b4_runtime")
        if item.relative_path == relative_path
    )


def _package(name: str) -> types.ModuleType:
    """Create one import-compatible in-memory package.

    Args:
        name: Fully qualified package name.

    Returns:
        Module with an empty package search path.
    """

    module = types.ModuleType(name)
    module.__path__ = []  # type: ignore[attr-defined]
    return module


def _base_packages() -> dict[str, types.ModuleType]:
    """Build the generated app package hierarchy shared by runtime tests.

    Returns:
        Import-compatible package modules keyed by qualified name.
    """

    return {
        name: _package(name)
        for name in (
            "apps",
            "apps.sample_b4_runtime",
            "apps.sample_b4_runtime.models",
            "apps.sample_b4_runtime.repositories",
            "apps.sample_b4_runtime.schemas",
            "backend",
            "backend.shared_services",
        )
    }


class NetworkedRecipeRuntimeTest(unittest.TestCase):
    """Verify generated hybrid-sync and Web Push services through fake ports."""

    def test_hybrid_sync_preserves_order_digest_owner_and_opaque_cursor(self) -> None:
        """Execute ordered pushes and a versioned owner-scoped pull cursor."""

        source = _render_service("hybrid_sync", "services/sync_service.py")
        repository_module = types.ModuleType(
            "apps.sample_b4_runtime.repositories.sync_repository"
        )

        class PlaceholderRepository:
            """Provide the default repository symbol required during import."""

        repository_module.SyncRepository = PlaceholderRepository
        schema_module = types.ModuleType("apps.sample_b4_runtime.schemas.sync")

        class FakeOperation:
            """Expose the validated-operation serialization used for hashing."""

            def __init__(self, value: str) -> None:
                """Store one deterministic operation value.

                Args:
                    value: App-neutral operation value.
                """

                self.value = value

            def model_dump(self, *, mode: str) -> dict[str, str]:
                """Return canonical JSON-compatible operation content.

                Args:
                    mode: Required serialization mode.

                Returns:
                    Stable operation mapping.
                """

                self.assert_mode = mode
                return {"value": self.value}

        schema_module.SyncPushOperationRequest = FakeOperation
        modules = _base_packages()
        modules.update(
            {
                repository_module.__name__: repository_module,
                schema_module.__name__: schema_module,
            }
        )
        generated = types.ModuleType("generated_hybrid_sync_runtime")
        with patch.dict(sys.modules, modules):
            exec(compile(source, "sync_service.py", "exec"), generated.__dict__)
        events: list[tuple[object, ...]] = []

        class RecordingRepository:
            """Record ordered generated service calls without persistence."""

            async def apply_operation(
                self,
                owner_subject: str,
                operation: FakeOperation,
                digest: str,
            ) -> dict[str, str]:
                """Record one owner-scoped operation application.

                Args:
                    owner_subject: Verified owner subject.
                    operation: Validated operation.
                    digest: Canonical operation digest.

                Returns:
                    Stable operation result.
                """

                events.append(("push", owner_subject, operation.value, digest))
                return {"value": operation.value}

            async def pull_changes(
                self,
                owner_subject: str,
                *,
                after_sequence: int,
                limit: int,
            ) -> tuple[list[dict[str, object]], bool]:
                """Record one owner-scoped page request.

                Args:
                    owner_subject: Verified owner subject.
                    after_sequence: Exclusive cursor sequence.
                    limit: Requested bounded page size.

                Returns:
                    One change after the initial cursor, otherwise no changes.
                """

                events.append(("pull", owner_subject, after_sequence, limit))
                if after_sequence == 0:
                    return ([{"change_id": 4, "value": "first"}], False)
                return ([], False)

        service = generated.SyncService(repository=RecordingRepository())
        results = asyncio.run(
            service.push_operations(
                "owner-1",
                [FakeOperation("first"), FakeOperation("second")],
            )
        )
        first_page = asyncio.run(
            service.pull_changes("owner-1", cursor=None, limit=20)
        )
        second_page = asyncio.run(
            service.pull_changes(
                "owner-1",
                cursor=first_page["next_cursor"],
                limit=20,
            )
        )

        self.assertEqual(results, [{"value": "first"}, {"value": "second"}])
        self.assertEqual([event[:3] for event in events[:2]], [
            ("push", "owner-1", "first"),
            ("push", "owner-1", "second"),
        ])
        digests = [str(event[3]) for event in events[:2]]
        self.assertTrue(all(len(digest) == 64 for digest in digests))
        self.assertNotEqual(digests[0], digests[1])
        self.assertEqual(events[2:], [
            ("pull", "owner-1", 0, 20),
            ("pull", "owner-1", 4, 20),
        ])
        self.assertEqual(second_page["changes"], [])
        with self.assertRaises(generated.InvalidSyncCursor):
            asyncio.run(service.pull_changes("owner-1", cursor="***", limit=20))

    def test_web_push_defers_config_and_preserves_owner_scoped_operations(self) -> None:
        """Execute injected subscription, schedule, delivery, and worker seams."""

        source = _render_service(
            "authenticated_web_push",
            "services/web_push_service.py",
        )
        modules = _base_packages()
        model_module = types.ModuleType(
            "apps.sample_b4_runtime.models.web_push_subscription"
        )
        model_module.ScheduledWebPushNotification = object
        model_module.WebPushNotification = object
        model_module.WebPushSubscription = object
        repository_module = types.ModuleType(
            "apps.sample_b4_runtime.repositories.web_push_repository"
        )

        class PlaceholderRepository:
            """Provide the default repository symbol required during import."""

        repository_module.WebPushRepository = PlaceholderRepository
        config_module = types.ModuleType("backend.shared_services.web_push_config")
        config_module.validate_vapid_public_key = lambda value: f"validated:{value}"
        delivery_module = types.ModuleType("backend.shared_services.web_push_delivery")

        class DeliveryConfig:
            """Provide the generated delivery configuration annotation."""

        class DeliveryCoordinator:
            """Provide the generated coordinator annotation."""

        class Sender:
            """Provide the generated sender constructor."""

            def __init__(self, config: object) -> None:
                """Retain the supplied delivery configuration.

                Args:
                    config: Validated delivery configuration.
                """

                self.config = config

        delivery_module.WebPushDeliveryConfig = DeliveryConfig
        delivery_module.WebPushDeliveryCoordinator = DeliveryCoordinator
        delivery_module.WebPushSender = Sender
        types_module = types.ModuleType(
            "backend.shared_services.web_push_delivery_types"
        )
        types_module.WebPushDeliveryReport = object
        dispatch_module = types.ModuleType("backend.shared_services.web_push_dispatch")

        class DispatchPolicy:
            """Provide the optional dispatch policy type."""

        class DispatchWorker:
            """Run one injected durable dispatch callback."""

            def __init__(self, dispatch: object, deliver: object, policy: object) -> None:
                """Retain worker dependencies without starting background work.

                Args:
                    dispatch: Repository dispatch port.
                    deliver: Generated payload delivery callback.
                    policy: Bounded dispatch policy.
                """

                self.dependencies = (dispatch, deliver, policy)

            async def run_once(self) -> str:
                """Return one privacy-safe aggregate worker verdict.

                Returns:
                    Stable fake dispatch report.
                """

                return "dispatch-report"

        dispatch_module.WebPushDispatchPolicy = DispatchPolicy
        dispatch_module.WebPushDispatchRunReport = object
        dispatch_module.WebPushDispatchWorker = DispatchWorker
        dispatch_module.WebPushScheduleReplaceResult = object
        modules.update(
            {
                model_module.__name__: model_module,
                repository_module.__name__: repository_module,
                config_module.__name__: config_module,
                delivery_module.__name__: delivery_module,
                types_module.__name__: types_module,
                dispatch_module.__name__: dispatch_module,
            }
        )
        generated = types.ModuleType("generated_web_push_runtime")
        with patch.dict(sys.modules, modules):
            exec(compile(source, "web_push_service.py", "exec"), generated.__dict__)
        events: list[tuple[object, ...]] = []

        class RecordingRepository:
            """Record owner-scoped subscription and schedule operations."""

            dispatch = object()

            async def upsert_subscription(self, owner: str, value: object) -> bool:
                """Record subscription registration.

                Args:
                    owner: Verified owner subject.
                    value: Validated browser subscription.

                Returns:
                    True for a newly stored subscription.
                """

                events.append(("register", owner, value))
                return True

            async def delete_subscription(self, owner: str, endpoint: str) -> bool:
                """Record subscription deletion.

                Args:
                    owner: Verified owner subject.
                    endpoint: Opaque browser endpoint.

                Returns:
                    True for an existing subscription.
                """

                events.append(("unregister", owner, endpoint))
                return True

            async def replace_schedule(
                self,
                owner: str,
                drafts: list[object],
                *,
                now: object,
            ) -> str:
                """Record complete durable schedule replacement.

                Args:
                    owner: Verified owner subject.
                    drafts: App-validated schedule drafts.
                    now: Deterministic replacement time.

                Returns:
                    Stable fake schedule report.
                """

                events.append(("schedule", owner, tuple(drafts), now))
                return "schedule-report"

        class Occurrence:
            """Convert one occurrence into a repository draft."""

            def to_draft(self) -> str:
                """Return a stable schedule draft.

                Returns:
                    Fake schedule draft.
                """

                return "draft"

        class Notification:
            """Convert one visible notification into a delivery payload."""

            def to_payload(self) -> str:
                """Return a stable delivery payload.

                Returns:
                    Fake encrypted-delivery input.
                """

                return "payload"

        class RecordingDelivery:
            """Record owner-scoped delivery without provider I/O."""

            async def deliver_to_user(self, owner: str, payload: str) -> str:
                """Record one delivery.

                Args:
                    owner: Verified owner subject.
                    payload: Validated notification payload.

                Returns:
                    Stable aggregate delivery report.
                """

                events.append(("deliver", owner, payload))
                return "delivery-report"

        loader_calls: list[str] = []
        service = generated.WebPushService(
            repository=RecordingRepository(),
            public_key_loader=lambda: loader_calls.append("public") or "public-key",
            delivery_config_loader=lambda: loader_calls.append("secret") or object(),
            delivery=RecordingDelivery(),
        )
        self.assertEqual(loader_calls, [])
        self.assertEqual(service.get_public_key(), "validated:public-key")
        self.assertTrue(asyncio.run(service.register("owner-2", "subscription")))
        self.assertTrue(asyncio.run(service.unregister("owner-2", "endpoint")))
        self.assertEqual(
            asyncio.run(
                service.replace_schedule(
                    "owner-2",
                    [Occurrence()],
                    now="fixed-now",
                )
            ),
            "schedule-report",
        )
        self.assertEqual(
            asyncio.run(service.deliver("owner-2", Notification())),
            "delivery-report",
        )
        self.assertEqual(asyncio.run(service.run_dispatch_once()), "dispatch-report")
        self.assertEqual(loader_calls, ["public"])
        self.assertEqual(
            events,
            [
                ("register", "owner-2", "subscription"),
                ("unregister", "owner-2", "endpoint"),
                ("schedule", "owner-2", ("draft",), "fixed-now"),
                ("deliver", "owner-2", "payload"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
