"""Felix AI chat schema aliases.

Felix uses the shared backend-owned AI chat contract unchanged. This module
keeps Felix-local import names stable while making the reusable contract live in
``api.shared_schemas.ai_chat`` for future backend apps.
"""
from api.shared_schemas.ai_chat import (
    AiChatAskRequest,
    AiChatAskResponse,
    AiChatHistoryMessage,
    AiChatQuotaConsumeResponse,
    AiChatUsedChunk,
)


FelixAiChatHistoryMessage = AiChatHistoryMessage
"""Felix alias for one client-provided AI chat history message."""

FelixAiChatAskRequest = AiChatAskRequest
"""Felix alias for the shared AI chat ask request."""

FelixAiChatUsedChunk = AiChatUsedChunk
"""Felix alias for shared retrieval diagnostics."""

FelixAiChatAskResponse = AiChatAskResponse
"""Felix alias for the shared AI chat ask response."""

FelixAiChatQuotaConsumeResponse = AiChatQuotaConsumeResponse
"""Felix alias for the shared quota-consume response."""
