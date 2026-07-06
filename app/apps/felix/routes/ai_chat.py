"""Felix AI chat routes.

Routes are mounted below ``/felix/v1/ai-chat`` by the Felix backend definition.
The route bodies are created by the shared AI chat route factory so future apps
can expose the same secure backend-owned contract without duplicating handlers.
"""
from __future__ import annotations

from api.shared_dependencies.auth import get_user_id_from_token
from api.shared_routes.ai_chat import create_ai_chat_router
from apps.felix.services.ai_chat_service import FelixAiChatService


def get_ai_chat_service() -> FelixAiChatService:
    """Return the Felix AI chat service.

    Args:
        None.

    Returns:
        FelixAiChatService: Backend-owned assistant service.

    Side Effects:
        Resolves the active wellness database provider through the service.
    """
    return FelixAiChatService()


router = create_ai_chat_router(
    prefix="/v1/ai-chat",
    tags=["ai-chat"],
    get_current_user_id=get_user_id_from_token,
    get_service=get_ai_chat_service,
)
"""Felix AI chat router generated from the reusable shared route factory."""
