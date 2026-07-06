"""Shared AI chat request and response schemas.

The schemas define a backend-owned AI chat bridge contract that multiple apps
can reuse. Frontends send user messages to their own backend app; provider
credentials, prompt assembly, retrieval, moderation, quota, and model calls stay
behind that backend boundary.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class AiChatHistoryMessage(BaseModel):
    """One message in the client-provided AI chat history.

    Attributes:
        role (Literal["user", "assistant"]): Message author role.
        content (str): Message text included for backend context.
    """

    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=8000)


class AiChatAskRequest(BaseModel):
    """Request payload for one backend-owned AI chat answer.

    Attributes:
        question (str): Current user-authored question.
        history (List[AiChatHistoryMessage]): Recent conversation history.
        question_source (Literal["direct_input", "demo_button"]): Source marker
            used by quota and analytics.
        custom_prompt (Optional[str]): Optional client-side prompt addendum.
        max_chunks (Optional[int]): Optional retrieval chunk cap.
        external_context (Dict[str, Any]): Optional host-provided context.
        locale (Optional[Literal["en", "de"]]): Response language hint.
        intent_hint (Optional[Literal]): Client-side intent detection hint.
        ai_chat_categories (List[str]): Backend context providers to activate.
        target_metrics (List[str]): Metric ids for metric-specific context.
    """

    question: str = Field(..., min_length=1, max_length=4000)
    history: List[AiChatHistoryMessage] = Field(default_factory=list, max_length=80)
    question_source: Literal["direct_input", "demo_button"] = "direct_input"
    custom_prompt: Optional[str] = Field(None, max_length=12000)
    max_chunks: Optional[int] = Field(None, ge=1, le=12)
    external_context: Dict[str, Any] = Field(default_factory=dict)
    locale: Optional[Literal["en", "de"]] = "de"
    intent_hint: Optional[
        Literal[
            "general_support",
            "state_reflection",
            "progress_analysis",
            "activity_recommendation",
        ]
    ] = None
    ai_chat_categories: List[str] = Field(default_factory=list, max_length=12)
    target_metrics: List[str] = Field(default_factory=list, max_length=12)


class AiChatUsedChunk(BaseModel):
    """Diagnostic source chunk used by retrieval-backed deployments.

    Attributes:
        id (str): Stable source id.
        title (Optional[str]): Optional readable title.
        score (Optional[float]): Optional retrieval score.
    """

    id: str
    title: Optional[str] = None
    score: Optional[float] = None


class AiChatAskResponse(BaseModel):
    """Response payload for one backend-owned AI chat answer.

    Attributes:
        answer (str): Assistant answer text. May contain a hidden action block
            for clients that support backend-owned actions.
        refusal (bool): Whether the backend refused the question.
        used_chunks (List[AiChatUsedChunk]): Optional retrieval diagnostics.
        sources (List[str]): Optional source identifiers.
        moderation (Dict[str, Any]): Optional moderation diagnostics.
    """

    answer: str
    refusal: bool = False
    used_chunks: List[AiChatUsedChunk] = Field(default_factory=list)
    sources: List[str] = Field(default_factory=list)
    moderation: Dict[str, Any] = Field(default_factory=dict)


class AiChatQuotaConsumeResponse(BaseModel):
    """Quota response for lightweight assistant flows.

    Attributes:
        status (Literal["success"]): Provider-normalized status.
        remaining (Optional[int]): Remaining quota when enforced by a backend.
    """

    status: Literal["success"] = "success"
    remaining: Optional[int] = None
