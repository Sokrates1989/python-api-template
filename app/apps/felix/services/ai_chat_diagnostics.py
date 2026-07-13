"""Structured diagnostics for the Felix backend-owned AI chat flow.

The module centralizes safe request, context, activity, prompt, and response
trace payloads. Full prompts, external context, and answers remain available
only when explicit local prompt-debug logging is enabled; normal diagnostics
contain bounded metadata and Startlist counts rather than private content.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Mapping, Optional

from backend.shared_services.ai_chat_debug import (
    is_ai_chat_prompt_logging_enabled,
    log_ai_chat_debug,
)
from backend.shared_services.ai_chat_service import AiChatContextSnapshot, AiChatLocale
from apps.felix.schemas.ai_chat import FelixAiChatAskRequest
from apps.felix.services.ai_chat_startlist_context import (
    FelixAiStartlistContext,
    felix_ai_startlist_debug_payload,
)


def request_debug_payload(request: FelixAiChatAskRequest) -> Dict[str, Any]:
    """Build safe request diagnostics for the AI trace log.

    Args:
        request (FelixAiChatAskRequest): Incoming chat request.

    Returns:
        Dict[str, Any]: Request metadata, with full prompt fields included only
        when local prompt debug logging is enabled.

    Side Effects:
        None.
    """
    include_prompts = is_ai_chat_prompt_logging_enabled()
    payload: Dict[str, Any] = {
        "question_source": request.question_source,
        "locale": request.locale,
        "intent_hint": request.intent_hint,
        "question_chars": len(request.question),
        "custom_prompt_chars": len(request.custom_prompt or ""),
        "history_count": len(request.history),
        "history_roles": [item.role for item in request.history[-12:]],
        "external_context_keys": sorted(str(key) for key in request.external_context.keys()),
        "ai_chat_categories": request.ai_chat_categories,
        "target_metrics": request.target_metrics,
        "max_chunks": request.max_chunks,
    }
    if include_prompts:
        payload.update(
            {
                "question": request.question,
                "custom_prompt": request.custom_prompt or "",
                "history": [item.model_dump() for item in request.history],
                "external_context": request.external_context,
            }
        )
    else:
        payload.update(
            {
                "question_preview": request.question[:220],
                "custom_prompt_preview": (request.custom_prompt or "")[:220],
            }
        )
    return payload


def context_debug_payload(context: AiChatContextSnapshot) -> Dict[str, Any]:
    """Build bounded context diagnostics for AI trace logs.

    Args:
        context (AiChatContextSnapshot): Backend-owned Felix context snapshot.

    Returns:
        Dict[str, Any]: Counts, representative rows, and optional full context.

    Side Effects:
        None.
    """
    payload: Dict[str, Any] = {
        "activity_count": len(context.activities),
        "diary_entry_count": len(context.diary_entries),
        "checkin_count": len(context.checkins),
        "activity_samples": [
            activity_debug_payload(activity)
            for activity in context.activities[:8]
        ],
        "diary_samples": [
            {
                "id": str(item.get("id") or ""),
                "title": str(item.get("title") or "")[:120],
                "summary_chars": len(str(item.get("summary") or "")),
            }
            for item in context.diary_entries[:5]
        ],
        "checkin_samples": [
            {
                "id": str(item.get("id") or ""),
                "created_at": str(item.get("created_at") or item.get("timestamp") or ""),
                "keys": sorted(str(key) for key in item.keys())[:20],
            }
            for item in context.checkins[:5]
        ],
    }
    if is_ai_chat_prompt_logging_enabled():
        payload["raw_context"] = {
            "activities": context.activities,
            "diary_entries": context.diary_entries,
            "checkins": context.checkins,
        }
    return payload


def activity_debug_payload(
    activity: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Build a compact activity diagnostic row.

    Args:
        activity (Optional[Mapping[str, Any]]): Activity row or None.

    Returns:
        Dict[str, Any]: Stable activity identity and scoring hints.

    Side Effects:
        None.
    """
    if not activity:
        return {}
    return {
        "id": str(activity.get("id") or ""),
        "name": str(
            activity.get("title")
            or activity.get("title_key")
            or activity.get("id")
            or ""
        ),
        "duration_minutes": activity.get("duration_minutes"),
        "favorite": bool(activity.get("favorite")),
        "category_keys": activity.get("category_keys") or [],
        "summary_chars": len(str(activity.get("summary") or "")),
    }


def messages_debug_payload(
    messages: List[Dict[str, str]],
) -> List[Dict[str, Any]]:
    """Return role and size diagnostics for provider messages.

    Args:
        messages (List[Dict[str, str]]): Provider messages.

    Returns:
        List[Dict[str, Any]]: Message summaries, optionally with full content.

    Side Effects:
        None.
    """
    include_prompts = is_ai_chat_prompt_logging_enabled()
    return [
        {
            "index": index,
            "role": message.get("role", ""),
            "chars": len(message.get("content", "")),
            **(
                {"content": message.get("content", "")}
                if include_prompts
                else {"preview": message.get("content", "")[:220]}
            ),
        }
        for index, message in enumerate(messages)
    ]


def elapsed_ms(started_at: float) -> int:
    """Return elapsed milliseconds since a perf-counter timestamp.

    Args:
        started_at (float): ``time.perf_counter`` value captured at step start.

    Returns:
        int: Elapsed milliseconds.

    Side Effects:
        None.
    """
    return int((time.perf_counter() - started_at) * 1000)


def has_action_block(answer: str) -> bool:
    """Return whether an assistant answer already contains hidden actions.

    Args:
        answer (str): Raw provider answer.

    Returns:
        bool: True when the expected Felix action block markers are present.

    Side Effects:
        None.
    """
    return "[[FELIX_ACTIONS]]" in answer and "[[/FELIX_ACTIONS]]" in answer


def log_answer_service_start(
    *,
    request_id: str,
    locale: AiChatLocale,
    intent: str,
    request: FelixAiChatAskRequest,
) -> None:
    """Log safe metadata when Felix begins one AI answer.

    Args:
        request_id (str): Stable request trace ID.
        locale (AiChatLocale): Normalized response locale.
        intent (str): Resolved request intent.
        request (FelixAiChatAskRequest): Incoming chat request.

    Returns:
        None.

    Side Effects:
        Writes one structured AI debug event.
    """
    log_ai_chat_debug(
        "ai_answer_service_start",
        {
            "scope": "felix",
            "request_id": request_id,
            "locale": locale,
            "intent": intent,
            "request": request_debug_payload(request),
        },
    )


def log_response_built(
    *,
    request_id: str,
    response_source: str,
    answer: str,
    started_at: float,
    context: AiChatContextSnapshot,
    startlist_context: FelixAiStartlistContext,
) -> None:
    """Log safe metadata after Felix builds one AI response.

    Args:
        request_id (str): Stable request trace ID.
        response_source (str): ``"provider"`` or deterministic ``"fallback"``.
        answer (str): Final answer text; logged only under explicit prompt debug.
        started_at (float): Perf-counter timestamp captured at request start.
        context (AiChatContextSnapshot): Backend-owned wellness context.
        startlist_context (FelixAiStartlistContext): Validated Startlist hint.

    Returns:
        None.

    Side Effects:
        Writes one structured AI debug event.
    """
    log_ai_chat_debug(
        "ai_response_built",
        {
            "scope": "felix",
            "request_id": request_id,
            "source": response_source,
            "answer_chars": len(answer),
            "has_action_block": has_action_block(answer),
            "elapsed_ms": elapsed_ms(started_at),
            "context": context_debug_payload(context),
            "startlist": felix_ai_startlist_debug_payload(startlist_context),
            **({"answer": answer} if is_ai_chat_prompt_logging_enabled() else {}),
        },
    )


def log_activity_selection(
    request_id: str,
    intent: str,
    target_metrics: List[str],
    activity: Optional[Dict[str, Any]],
    startlist_context: FelixAiStartlistContext,
) -> None:
    """Log the backend-owned activity selection without visible content.

    Args:
        request_id (str): Stable request trace ID.
        intent (str): Resolved request intent.
        target_metrics (List[str]): Client-requested metric identifiers.
        activity (Optional[Dict[str, Any]]): Selected backend activity row.
        startlist_context (FelixAiStartlistContext): Validated Startlist hint.

    Returns:
        None.

    Side Effects:
        Writes one structured AI debug event.
    """
    log_ai_chat_debug(
        "ai_activity_selection",
        {
            "scope": "felix",
            "request_id": request_id,
            "intent": intent,
            "target_metrics": target_metrics,
            "selected_activity": activity_debug_payload(activity),
            "startlist": felix_ai_startlist_debug_payload(startlist_context),
        },
    )


def log_prompt_built(
    request_id: str,
    intent: str,
    locale: AiChatLocale,
    messages: List[Dict[str, str]],
    context: AiChatContextSnapshot,
) -> None:
    """Log safe prompt metadata after backend-owned message assembly.

    Args:
        request_id (str): Stable request trace ID.
        intent (str): Resolved request intent.
        locale (AiChatLocale): Normalized response locale.
        messages (List[Dict[str, str]]): Provider messages; full content is
            logged only when explicit prompt debug logging is enabled.
        context (AiChatContextSnapshot): Backend-owned wellness context.

    Returns:
        None.

    Side Effects:
        Writes one structured AI debug event.
    """
    log_ai_chat_debug(
        "ai_prompt_built",
        {
            "scope": "felix",
            "request_id": request_id,
            "intent": intent,
            "locale": locale,
            "message_summary": messages_debug_payload(messages),
            "context": context_debug_payload(context),
            **({"messages": messages} if is_ai_chat_prompt_logging_enabled() else {}),
        },
    )
