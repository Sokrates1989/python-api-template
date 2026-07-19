"""Behavior tests for the rendered Template V2 AI chat service boundary.

The suite uses only in-memory ports. It is skipped in the dependency-light host
environment and runs inside the repository's Python 3.13 API test image, where
Pydantic and Requests are available.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from template_v2.networked_recipe_sources import validate_networked_recipe_sources
from template_v2.networked_recipes_contract import validate_networked_recipes_contract


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class _PlaceholderRepository:
    """Fail if a test accidentally constructs the runtime repository."""

    def __init__(self) -> None:
        """Reject implicit construction because tests inject in-memory storage.

        Raises:
            AssertionError: Always, to prove constructor side effects are absent.
        """

        raise AssertionError("tests must inject an AI chat repository")


class _MemoryRepository:
    """Provide owner-isolated in-memory exchange persistence for service tests."""

    def __init__(self) -> None:
        """Create empty exchange storage.

        Returns:
            None.
        """

        self.rows: dict[tuple[str, str], dict[str, Any]] = {}

    async def find_exchange(
        self,
        owner_subject: str,
        request_id: str,
    ) -> dict[str, Any] | None:
        """Find one exchange under an exact owner/request key.

        Args:
            owner_subject: Verified test owner.
            request_id: Stable request id.

        Returns:
            Copied exchange or null.
        """

        value = self.rows.get((owner_subject, request_id))
        return dict(value) if value is not None else None

    async def load_history(
        self,
        owner_subject: str,
        conversation_id: str,
        *,
        limit: int = 12,
    ) -> list[dict[str, str]]:
        """Load bounded owner/conversation history from in-memory exchanges.

        Args:
            owner_subject: Verified test owner.
            conversation_id: App-owned test conversation.
            limit: Maximum exchanges returned.

        Returns:
            Alternating user and assistant messages.
        """

        matches = [
            value
            for (owner, _), value in self.rows.items()
            if owner == owner_subject and value["conversation_id"] == conversation_id
        ][-limit:]
        return [
            message
            for value in matches
            for message in (
                {"role": "user", "content": value["user_message"]},
                {"role": "assistant", "content": value["assistant_message"]},
            )
        ]

    async def store_exchange(
        self,
        owner_subject: str,
        *,
        conversation_id: str,
        request_id: str,
        user_message: str,
        assistant_message: str,
    ) -> tuple[dict[str, Any], bool]:
        """Store one minimal exchange idempotently.

        Args:
            owner_subject: Verified test owner.
            conversation_id: App-owned conversation id.
            request_id: Stable idempotency id.
            user_message: Visible user text.
            assistant_message: Visible assistant text.

        Returns:
            Copied exchange and whether it was newly created.
        """

        key = (owner_subject, request_id)
        created = key not in self.rows
        self.rows.setdefault(
            key,
            {
                "conversation_id": conversation_id,
                "request_id": request_id,
                "user_message": user_message,
                "assistant_message": assistant_message,
                "created_at": "2026-01-01T00:00:00+00:00",
            },
        )
        return dict(self.rows[key]), created


class _CountingQuota:
    """Count verified-owner quota checks without imposing a product limit."""

    def __init__(self) -> None:
        """Create an empty call log.

        Returns:
            None.
        """

        self.owners: list[str] = []

    async def check(self, owner_subject: str) -> None:
        """Record one allowed owner request.

        Args:
            owner_subject: Verified test owner.

        Returns:
            None after allowing the request.
        """

        self.owners.append(owner_subject)


class _CountingProvider:
    """Return deterministic assistant text while recording minimized messages."""

    def __init__(self) -> None:
        """Create an empty provider call log.

        Returns:
            None.
        """

        self.calls: list[list[dict[str, str]]] = []

    async def complete(self, messages: list[dict[str, str]]) -> str:
        """Return one deterministic visible response.

        Args:
            messages: Minimized service-provided messages.

        Returns:
            Fixed assistant response.
        """

        self.calls.append(messages)
        return "A safe test response."


class AiChatRecipeBehaviorTest(unittest.TestCase):
    """Verify consent, context, replay, and owner boundaries after rendering."""

    @classmethod
    def setUpClass(cls) -> None:
        """Render and load the AI chat schemas/service with a repository stub.

        Returns:
            None after class attributes expose rendered runtime types.
        """

        if importlib.util.find_spec("pydantic") is None:
            raise unittest.SkipTest("Pydantic is unavailable in the host environment")
        catalog = validate_networked_recipes_contract(REPOSITORY_ROOT)
        recipe = next(
            item
            for item in validate_networked_recipe_sources(REPOSITORY_ROOT, catalog)
            if item.backend_recipe_id == "ai_chat"
        )
        files = {
            item.relative_path: item.content
            for item in recipe.render("sample_app")
        }
        schema_name = "apps.sample_app.schemas.ai_chat"
        schema_module = types.ModuleType(schema_name)
        sys.modules[schema_name] = schema_module
        exec(compile(files["schemas/ai_chat.py"], schema_name, "exec"), schema_module.__dict__)
        repository_name = "apps.sample_app.repositories.ai_chat_repository"
        repository_module = types.ModuleType(repository_name)
        repository_module.AiChatRepository = _PlaceholderRepository
        sys.modules[repository_name] = repository_module
        service_name = "apps.sample_app.services.ai_chat_service"
        service_module = types.ModuleType(service_name)
        sys.modules[service_name] = service_module
        exec(compile(files["services/ai_chat_service.py"], service_name, "exec"), service_module.__dict__)
        cls.Request = schema_module.AiChatRequest
        cls.Service = service_module.AiChatService
        cls.ServiceError = service_module.AiChatServiceError
        cls.ServiceModule = service_module

    def _request(self, **changes: Any) -> Any:
        """Build one valid rendered request with optional field overrides.

        Args:
            changes: Schema fields replacing valid defaults.

        Returns:
            Rendered ``AiChatRequest`` instance.
        """

        values = {
            "request_id": "request-1",
            "conversation_id": "conversation-1",
            "message": "Please help with a small next step.",
            "consent": {"confirmed": True, "policy_version": "2026-01"},
        }
        values.update(changes)
        return self.Request.model_validate(values)

    def test_consent_must_be_explicitly_confirmed(self) -> None:
        """Reject false consent before service, storage, or provider work."""

        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            self._request(consent={"confirmed": False, "policy_version": "2026-01"})

    def test_unreviewed_context_fails_before_quota_or_provider_work(self) -> None:
        """Keep non-empty context fail-closed until an app injects policy."""

        repository = _MemoryRepository()
        quota = _CountingQuota()
        provider = _CountingProvider()
        service = self.Service(
            repository,
            quota_port=quota,
            provider=provider,
        )

        with self.assertRaises(self.ServiceError) as captured:
            asyncio.run(
                service.ask(
                    "owner-a",
                    self._request(context={"profile.summary": "private hint"}),
                )
            )

        self.assertEqual(captured.exception.code, "ai_chat_context_not_configured")
        self.assertEqual(quota.owners, [])
        self.assertEqual(provider.calls, [])
        self.assertEqual(repository.rows, {})

    def test_idempotent_replay_does_not_repeat_quota_or_provider_work(self) -> None:
        """Return stored visible text for a repeated owner/request identity."""

        repository = _MemoryRepository()
        quota = _CountingQuota()
        provider = _CountingProvider()
        service = self.Service(repository, quota_port=quota, provider=provider)
        request = self._request()

        first = asyncio.run(service.ask("owner-a", request))
        second = asyncio.run(service.ask("owner-a", request))

        self.assertFalse(first["replayed"])
        self.assertTrue(second["replayed"])
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(quota.owners, ["owner-a"])
        self.assertEqual(
            set(repository.rows[("owner-a", "request-1")]),
            {
                "conversation_id",
                "request_id",
                "user_message",
                "assistant_message",
                "created_at",
            },
        )

    def test_same_request_id_is_isolated_between_verified_owners(self) -> None:
        """Never replay one owner's response into another owner's request."""

        repository = _MemoryRepository()
        provider = _CountingProvider()
        service = self.Service(repository, provider=provider)

        first = asyncio.run(service.ask("owner-a", self._request()))
        second = asyncio.run(service.ask("owner-b", self._request()))

        self.assertFalse(first["replayed"])
        self.assertFalse(second["replayed"])
        self.assertEqual(len(provider.calls), 2)
        self.assertEqual(len(repository.rows), 2)

    def test_provider_transport_error_does_not_expose_raw_details(self) -> None:
        """Translate provider failures into one stable content-free error."""

        configuration = self.ServiceModule.AiChatProviderConfiguration(
            endpoint="https://provider.invalid/chat",
            api_key="never-expose-this-key",
            model="test-model",
            max_tokens=100,
            timeout_seconds=1.0,
        )
        raw_error = self.ServiceModule.requests.RequestException(
            "provider body contained private diagnostics"
        )

        with patch.object(self.ServiceModule.requests, "post", side_effect=raw_error):
            with self.assertRaises(self.ServiceError) as captured:
                self.ServiceModule._post_completion(
                    configuration,
                    [{"role": "user", "content": "private message"}],
                )

        self.assertEqual(str(captured.exception), "ai_chat_provider_unavailable")
        self.assertNotIn("private", str(captured.exception))
        self.assertNotIn("never-expose", str(captured.exception))


if __name__ == "__main__":
    unittest.main()
