"""Shared backend-owned AI chat helpers.

This module contains provider-neutral AI chat utilities that app slices can
reuse while keeping final assistant behavior, prompts, retrieval, and provider
credentials inside the backend. The optional completion hook is backend-only:
frontends call app API routes and never receive provider endpoints or keys.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Literal, Mapping, Optional
from urllib.parse import urlsplit

import requests

from api.settings import settings
from api.shared_schemas.ai_chat import AiChatAskRequest
from backend.shared_services.ai_chat_debug import (
    is_ai_chat_prompt_logging_enabled,
    log_ai_chat_debug,
)


logger = logging.getLogger("backend.shared_services.ai_chat")

AiChatLocale = Literal["de", "en"]
"""Supported shared AI chat response locales."""

DEFAULT_AI_CHAT_ACTION_BLOCK_MARKER = "FELIX_ACTIONS"
"""Default hidden action-block marker used by FelixAppNew-compatible clients."""

CONTEXT_BACKED_INTENTS = {
    "state_reflection",
    "progress_analysis",
    "activity_recommendation",
}
"""Intent ids that normally benefit from backend context providers."""


@dataclass(frozen=True)
class AiChatContextSnapshot:
    """Generic backend context snapshot for wellness-like chat flows.

    Attributes:
        activities (List[Dict[str, Any]]): Activity catalog rows.
        diary_entries (List[Dict[str, Any]]): Recent diary rows.
        checkins (List[Dict[str, Any]]): Recent check-in rows.
    """

    activities: List[Dict[str, Any]]
    diary_entries: List[Dict[str, Any]]
    checkins: List[Dict[str, Any]]

    @classmethod
    def empty(cls) -> "AiChatContextSnapshot":
        """Return an empty context snapshot.

        Args:
            None.

        Returns:
            AiChatContextSnapshot: Snapshot with empty context collections.

        Side Effects:
            None.
        """
        return cls(activities=[], diary_entries=[], checkins=[])


class BackendAiChatServiceBase:
    """Base helpers for app-owned AI chat services.

    The base class only provides reusable envelope/quota behavior. Apps still
    own their domain prompts, retrieval providers, safety policy, and route
    registration.

    Methods:
        consume_quota: Reserve one quota unit for lightweight assistant flows.
        response: Build a schema-compatible response dictionary.
    """

    async def consume_quota(
        self,
        user_id: str,
        question_source: str = "direct_input",
        locale: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Reserve one quota unit for lightweight assistant flows.

        Args:
            user_id (str): Authenticated user id.
            question_source (str): Source marker supplied by the client.
            locale (Optional[str]): Optional locale hint.

        Returns:
            Dict[str, Any]: Success payload. Subclasses may override this to
            persist or enforce quota.

        Side Effects:
            None in the base implementation.
        """
        log_ai_chat_debug(
            "ai_quota_consume_request",
            {
                "scope": self.__class__.__name__,
                "user_id_present": bool(user_id),
                "question_source": question_source,
                "locale": locale,
            },
        )
        result = {"status": "success", "remaining": None}
        log_ai_chat_debug(
            "ai_usage_increment_result",
            {
                "scope": self.__class__.__name__,
                "question_increment": 1,
                "penalty_increment": 0,
                "moderation_category": "",
                "moderation_apply_penalty": False,
                "remaining": result["remaining"],
            },
        )
        return result

    def response(
        self,
        *,
        answer: str,
        refusal: bool = False,
        used_chunks: Optional[List[Dict[str, Any]]] = None,
        sources: Optional[List[str]] = None,
        moderation: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Build a shared AI chat response dictionary.

        Args:
            answer (str): Assistant answer text.
            refusal (bool): Whether the backend refused the question. Defaults
                to False.
            used_chunks (Optional[List[Dict[str, Any]]]): Optional retrieval
                diagnostics.
            sources (Optional[List[str]]): Optional source ids.
            moderation (Optional[Dict[str, Any]]): Optional moderation metadata.

        Returns:
            Dict[str, Any]: Payload accepted by ``AiChatAskResponse``.

        Side Effects:
            None.
        """
        return build_ai_chat_response(
            answer=answer,
            refusal=refusal,
            used_chunks=used_chunks,
            sources=sources,
            moderation=moderation,
        )


def build_ai_chat_response(
    *,
    answer: str,
    refusal: bool = False,
    used_chunks: Optional[List[Dict[str, Any]]] = None,
    sources: Optional[List[str]] = None,
    moderation: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a shared AI chat response dictionary.

    Args:
        answer (str): Assistant answer text.
        refusal (bool): Whether the backend refused the question. Defaults to
            False.
        used_chunks (Optional[List[Dict[str, Any]]]): Optional retrieval
            diagnostics.
        sources (Optional[List[str]]): Optional source identifiers.
        moderation (Optional[Dict[str, Any]]): Optional moderation diagnostics.

    Returns:
        Dict[str, Any]: Response payload compatible with ``AiChatAskResponse``.

    Side Effects:
        None.
    """
    return {
        "answer": answer,
        "refusal": refusal,
        "used_chunks": used_chunks or [],
        "sources": sources or [],
        "moderation": moderation or {},
    }


async def call_ai_chat_completion(
    messages: List[Dict[str, str]],
    *,
    json_mode: bool = False,
    trace_context: Optional[Mapping[str, Any]] = None,
) -> Optional[str]:
    """Call the configured backend-only AI chat completion provider.

    Args:
        messages (List[Dict[str, str]]): OpenAI-compatible chat messages.
        json_mode (bool): Whether to request a JSON object response when the
            provider supports ``response_format``. Defaults to False.
        trace_context (Optional[Mapping[str, Any]]): Optional app-provided
            request trace fields copied into debug events.

    Returns:
        Optional[str]: Assistant text, or None when no provider is configured
        or the provider request fails.

    Side Effects:
        Sends one HTTP request from the backend process when
        ``AI_CHAT_COMPLETIONS_ENDPOINT`` is configured. Provider credentials are
        read only from backend settings and are never exposed to frontend apps.
    """
    endpoint = settings.AI_CHAT_COMPLETIONS_ENDPOINT.strip()
    trace = dict(trace_context or {})
    if not endpoint:
        log_ai_chat_debug(
            "ai_completion_provider_skipped",
            {
                **trace,
                "reason": "no-completions-endpoint",
                "json_mode": json_mode,
                "message_summary": _ai_chat_message_debug(messages),
            },
        )
        return None

    log_ai_chat_debug(
        "ai_completion_provider_start",
        _provider_start_payload(messages, json_mode, trace),
    )
    return await asyncio.to_thread(
        _call_ai_chat_completion_sync,
        endpoint,
        messages,
        json_mode,
        trace,
    )


def _call_ai_chat_completion_sync(
    endpoint: str,
    messages: List[Dict[str, str]],
    json_mode: bool,
    trace_context: Mapping[str, Any],
) -> Optional[str]:
    """Execute one blocking completion request for ``call_ai_chat_completion``.

    Args:
        endpoint (str): OpenAI-compatible completion endpoint.
        messages (List[Dict[str, str]]): Chat messages.
        json_mode (bool): Whether to request JSON object mode.
        trace_context (Mapping[str, Any]): App-provided request trace fields.

    Returns:
        Optional[str]: Extracted assistant text, or None on provider errors.

    Side Effects:
        Performs one backend HTTP request.
    """
    safe_endpoint = _safe_ai_chat_endpoint_for_logs(endpoint)
    started_at = time.perf_counter()
    headers = {"Content-Type": "application/json"}
    try:
        api_key = settings.get_ai_chat_api_key()
    except ValueError as exc:
        logger.warning(
            "AI chat completion secret configuration failed: endpoint=%s error=%s",
            safe_endpoint,
            exc,
        )
        log_ai_chat_debug(
            "ai_completion_provider_result",
            {
                **trace_context,
                "success": False,
                "reason": "secret-configuration-failed",
                "elapsed_ms": _elapsed_ms(started_at),
            },
        )
        return None

    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    else:
        logger.warning(
            "AI chat completion endpoint configured without API key: endpoint=%s",
            safe_endpoint,
        )

    payload = _ai_chat_completion_payload(messages)
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    try:
        response = requests.post(
            endpoint,
            headers=headers,
            json=payload,
            timeout=settings.AI_CHAT_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        body = response.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "AI chat completion request failed: endpoint=%s error=%s",
            safe_endpoint,
            exc,
        )
        log_ai_chat_debug(
            "ai_completion_provider_result",
            {
                **trace_context,
                "success": False,
                "reason": "request-failed",
                "endpoint": safe_endpoint,
                "elapsed_ms": _elapsed_ms(started_at),
                "error_type": type(exc).__name__,
                "error": str(exc)[:500],
            },
        )
        return None

    answer = _extract_ai_chat_completion_text(body)
    if not answer:
        logger.warning(
            "AI chat completion response contained no usable text: endpoint=%s",
            safe_endpoint,
        )
        log_ai_chat_debug(
            "ai_completion_provider_result",
            {
                **trace_context,
                "success": False,
                "reason": "empty-answer",
                "endpoint": safe_endpoint,
                "elapsed_ms": _elapsed_ms(started_at),
                "response_shape": _provider_response_shape(body),
            },
        )
        return None
    log_ai_chat_debug(
        "ai_completion_provider_result",
        {
            **trace_context,
            "success": True,
            "endpoint": safe_endpoint,
            "elapsed_ms": _elapsed_ms(started_at),
            "answer_chars": len(answer),
            "response_shape": _provider_response_shape(body),
            **({"answer": answer} if is_ai_chat_prompt_logging_enabled() else {}),
        },
    )
    return answer


def _ai_chat_completion_payload(messages: List[Dict[str, str]]) -> Dict[str, Any]:
    """Build an OpenAI-compatible chat completion payload.

    Args:
        messages (List[Dict[str, str]]): Chat messages.

    Returns:
        Dict[str, Any]: Provider payload with model and generation settings.

    Side Effects:
        None.
    """
    payload: Dict[str, Any] = {
        "messages": messages,
        "temperature": settings.AI_CHAT_TEMPERATURE,
        "max_tokens": settings.AI_CHAT_MAX_TOKENS,
    }
    model = settings.AI_CHAT_MODEL.strip()
    if model:
        payload["model"] = model
    return payload


def _provider_start_payload(
    messages: List[Dict[str, str]],
    json_mode: bool,
    trace_context: Mapping[str, Any],
) -> Dict[str, Any]:
    """Build the shared provider-start debug payload.

    Args:
        messages (List[Dict[str, str]]): Messages that will be sent to the
            completion provider.
        json_mode (bool): Whether JSON response mode is requested.
        trace_context (Mapping[str, Any]): App-provided request trace fields.

    Returns:
        Dict[str, Any]: Structured debug payload.

    Side Effects:
        None.
    """
    payload: Dict[str, Any] = {
        **trace_context,
        "message_count": len(messages),
        "message_summary": _ai_chat_message_debug(messages),
        "json_mode": json_mode,
        "model_configured": bool(settings.AI_CHAT_MODEL.strip()),
        "temperature": settings.AI_CHAT_TEMPERATURE,
        "max_tokens": settings.AI_CHAT_MAX_TOKENS,
    }
    if is_ai_chat_prompt_logging_enabled():
        payload["messages"] = messages
    return payload


def _ai_chat_message_debug(messages: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """Return bounded diagnostics for completion messages.

    Args:
        messages (List[Dict[str, str]]): Messages being sent to the provider.

    Returns:
        List[Dict[str, Any]]: Role, character count, and optional content for
        each message.

    Side Effects:
        None.
    """
    include_content = is_ai_chat_prompt_logging_enabled()
    return [
        {
            "index": index,
            "role": str(message.get("role") or ""),
            "chars": len(str(message.get("content") or "")),
            **(
                {"content": str(message.get("content") or "")}
                if include_content
                else {"preview": str(message.get("content") or "")[:220]}
            ),
        }
        for index, message in enumerate(messages)
    ]


def _provider_response_shape(body: Any) -> Dict[str, Any]:
    """Return safe structural diagnostics for a provider response.

    Args:
        body (Any): Decoded provider JSON body.

    Returns:
        Dict[str, Any]: Response type, top-level keys, and known collection
        sizes.

    Side Effects:
        None.
    """
    if not isinstance(body, dict):
        return {"type": type(body).__name__}
    return {
        "type": "dict",
        "keys": sorted(str(key) for key in body.keys())[:20],
        "choice_count": len(body.get("choices") or [])
        if isinstance(body.get("choices"), list)
        else 0,
        "output_count": len(body.get("output") or [])
        if isinstance(body.get("output"), list)
        else 0,
    }


def _elapsed_ms(started_at: float) -> int:
    """Return elapsed milliseconds since a perf-counter timestamp.

    Args:
        started_at (float): ``time.perf_counter`` value captured at step start.

    Returns:
        int: Elapsed milliseconds.

    Side Effects:
        None.
    """
    return int((time.perf_counter() - started_at) * 1000)


def _extract_ai_chat_completion_text(body: Any) -> Optional[str]:
    """Extract assistant text from common completion response shapes.

    Args:
        body (Any): Decoded provider JSON response.

    Returns:
        Optional[str]: Assistant text when present.

    Side Effects:
        None.
    """
    if not isinstance(body, dict):
        return None

    output_text = body.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    choices = body.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str) and content.strip():
                    return content.strip()
            text = first.get("text")
            if isinstance(text, str) and text.strip():
                return text.strip()

    output = body.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            content_items = item.get("content")
            if not isinstance(content_items, list):
                continue
            for content_item in content_items:
                if not isinstance(content_item, dict):
                    continue
                text = content_item.get("text")
                if isinstance(text, str) and text.strip():
                    return text.strip()
    return None


def _safe_ai_chat_endpoint_for_logs(url: str) -> str:
    """Return a sanitized endpoint string for logs.

    Args:
        url (str): Raw endpoint URL.

    Returns:
        str: URL without query or fragment details.

    Side Effects:
        None.
    """
    stripped = url.strip()
    if not stripped:
        return "(not set)"
    parsed = urlsplit(stripped)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    return stripped


def build_ai_chat_action_block(
    actions: Iterable[Mapping[str, Any]],
    *,
    marker: str = DEFAULT_AI_CHAT_ACTION_BLOCK_MARKER,
) -> str:
    """Serialize action hints into the hidden client action-block format.

    Args:
        actions (Iterable[Mapping[str, Any]]): Action hint dictionaries.
        marker (str): Hidden block marker. Defaults to
            ``DEFAULT_AI_CHAT_ACTION_BLOCK_MARKER``.

    Returns:
        str: Hidden action block containing compact JSON.

    Side Effects:
        None.
    """
    clean_actions = [
        {key: value for key, value in action.items() if str(value).strip()}
        for action in actions
    ]
    payload = json.dumps(
        {"actions": clean_actions},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    clean_marker = marker.strip() or DEFAULT_AI_CHAT_ACTION_BLOCK_MARKER
    return f"[[{clean_marker}]]{payload}[[/{clean_marker}]]"


def normalize_ai_chat_locale(value: Optional[str]) -> AiChatLocale:
    """Normalize a request locale.

    Args:
        value (Optional[str]): Raw locale string.

    Returns:
        AiChatLocale: ``en`` when the value starts with English, otherwise
        ``de``.

    Side Effects:
        None.
    """
    return "en" if str(value or "").lower().startswith("en") else "de"


def resolve_ai_chat_intent(request: AiChatAskRequest) -> str:
    """Resolve the effective shared AI chat request intent.

    Args:
        request (AiChatAskRequest): Current chat request.

    Returns:
        str: Intent id. Unknown or absent hints fall back to category-derived
        intent and then ``general_support``.

    Side Effects:
        None.
    """
    if request.intent_hint:
        return request.intent_hint

    categories = {category.strip() for category in request.ai_chat_categories}
    if "activities" in categories or "activity-executions" in categories:
        return "activity_recommendation"
    if "check-in" in categories:
        return "state_reflection"
    return "general_support"


def ai_chat_needs_backend_context(request: AiChatAskRequest) -> bool:
    """Return whether backend context providers should be activated.

    Args:
        request (AiChatAskRequest): Current chat request.

    Returns:
        bool: True when context categories or context-backed intents are
        present.

    Side Effects:
        None.
    """
    if request.ai_chat_categories:
        return True
    return request.intent_hint in CONTEXT_BACKED_INTENTS


def coerce_ai_chat_context_snapshot(value: Any) -> AiChatContextSnapshot:
    """Coerce unknown provider data into a shared context snapshot.

    Args:
        value (Any): Unknown mapping that may contain activities,
            diary_entries, and checkins.

    Returns:
        AiChatContextSnapshot: Snapshot containing dictionary rows only.

    Side Effects:
        None.
    """
    data = value if isinstance(value, dict) else {}
    return AiChatContextSnapshot(
        activities=list_of_dicts(data.get("activities")),
        diary_entries=list_of_dicts(data.get("diary_entries")),
        checkins=list_of_dicts(data.get("checkins")),
    )


def list_of_dicts(value: Any) -> List[Dict[str, Any]]:
    """Normalize an unknown list payload to dictionaries.

    Args:
        value (Any): Unknown payload.

    Returns:
        List[Dict[str, Any]]: Dictionary items only.

    Side Effects:
        None.
    """
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
