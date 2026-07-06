"""Reusable AI chat route factory for backend apps.

The factory keeps the HTTP contract reusable while each app still owns its
router prefix, authentication dependency, service implementation, and provider
configuration. Do not expose this as a global shared route group unless an app
explicitly wants a common AI chat surface.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from fastapi import APIRouter, Depends, Query

from api.shared_schemas.ai_chat import (
    AiChatAskRequest,
    AiChatAskResponse,
    AiChatQuotaConsumeResponse,
)


class AiChatRouteService(Protocol):
    """Service protocol required by the reusable AI chat router.

    Methods:
        ask: Return one assistant answer for an authenticated user.
        consume_quota: Reserve quota for lightweight assistant flows.
    """

    async def ask(self, user_id: str, request: AiChatAskRequest) -> dict[str, Any]:
        """Return one assistant answer.

        Args:
            user_id (str): Authenticated user id.
            request (AiChatAskRequest): Shared chat request.

        Returns:
            dict[str, Any]: Payload accepted by ``AiChatAskResponse``.
        """
        ...

    async def consume_quota(
        self,
        user_id: str,
        question_source: str = "direct_input",
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Reserve quota for a lightweight assistant flow.

        Args:
            user_id (str): Authenticated user id.
            question_source (str): Source marker supplied by the client.
            locale (str | None): Optional locale hint.

        Returns:
            dict[str, Any]: Payload accepted by
            ``AiChatQuotaConsumeResponse``.
        """
        ...


def create_ai_chat_router(
    *,
    prefix: str,
    tags: list[str],
    get_current_user_id: Callable[..., str],
    get_service: Callable[..., AiChatRouteService],
) -> APIRouter:
    """Create a reusable AI chat router for one backend app.

    Args:
        prefix (str): App-owned route prefix, for example ``/v1/ai-chat``.
            The prefix must not start with ``/api`` because this service already
            is an API service.
        tags (list[str]): OpenAPI tag names for the generated routes.
        get_current_user_id (Callable[..., str]): FastAPI dependency returning
            the authenticated user id.
        get_service (Callable[..., AiChatRouteService]): FastAPI dependency
            returning the app-owned AI chat service.

    Returns:
        APIRouter: Router exposing ``POST /ask`` and
        ``POST /quota/consume`` below the supplied prefix.

    Raises:
        ValueError: When prefix starts with ``/api``.

    Side Effects:
        Creates nested route handlers bound to the supplied dependencies.
    """
    normalized_prefix = prefix.strip() or "/v1/ai-chat"
    if normalized_prefix.startswith("/api"):
        raise ValueError("AI chat route prefixes must not start with /api")

    router = APIRouter(tags=tags, prefix=normalized_prefix)

    @router.post("/ask", response_model=AiChatAskResponse)
    async def ask_ai_chat(
        request: AiChatAskRequest,
        current_user_id: str = Depends(get_current_user_id),
        service: AiChatRouteService = Depends(get_service),
    ) -> AiChatAskResponse:
        """Return one backend-owned AI chat answer.

        Args:
            request (AiChatAskRequest): Shared AI chat request payload.
            current_user_id (str): Authenticated user id.
            service (AiChatRouteService): App-owned AI chat service.

        Returns:
            AiChatAskResponse: Assistant answer and optional diagnostics.
        """
        result = await service.ask(current_user_id, request)
        return AiChatAskResponse(**result)

    @router.post("/quota/consume", response_model=AiChatQuotaConsumeResponse)
    async def consume_ai_chat_quota(
        question_source: str = Query(default="direct_input"),
        locale: str | None = Query(default=None),
        current_user_id: str = Depends(get_current_user_id),
        service: AiChatRouteService = Depends(get_service),
    ) -> AiChatQuotaConsumeResponse:
        """Reserve quota for lightweight assistant flows.

        Args:
            question_source (str): Source marker supplied by the client.
            locale (str | None): Optional locale hint.
            current_user_id (str): Authenticated user id.
            service (AiChatRouteService): App-owned AI chat service.

        Returns:
            AiChatQuotaConsumeResponse: Success payload. Service
            implementations may enforce quota behind this shared route.
        """
        result = await service.consume_quota(
            current_user_id,
            question_source=question_source,
            locale=locale,
        )
        return AiChatQuotaConsumeResponse(**result)

    return router
