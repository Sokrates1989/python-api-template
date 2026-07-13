"""Felix AI chat service.

This service implements the PWA-compatible AI chat backend contract and keeps
the assistant flow backend-owned. When backend provider settings are present it
uses the shared completion hook; otherwise it falls back to a deterministic,
data-aware response composer while preserving action-block and context-provider
semantics for all clients.
"""
from __future__ import annotations

import json
import re
import secrets
import time
from typing import Any, Dict, List, Optional, Tuple

from backend.shared_services.ai_chat_service import (
    AiChatContextSnapshot,
    AiChatLocale,
    BackendAiChatServiceBase,
    ai_chat_needs_backend_context,
    build_ai_chat_action_block,
    call_ai_chat_completion,
    coerce_ai_chat_context_snapshot,
    normalize_ai_chat_locale,
    resolve_ai_chat_intent,
)
from backend.shared_services.ai_chat_debug import (
    is_ai_chat_prompt_logging_enabled,
    log_ai_chat_debug,
)
from apps.felix.schemas.ai_chat import FelixAiChatAskRequest
from apps.felix.services.ai_chat_diagnostics import (
    activity_debug_payload as _activity_debug_payload,
    context_debug_payload as _context_debug_payload,
    elapsed_ms as _elapsed_ms,
    has_action_block as _has_action_block,
    log_activity_selection as _log_activity_selection,
    log_answer_service_start as _log_answer_service_start,
    log_prompt_built as _log_prompt_built,
    log_response_built as _log_response_built,
)
from apps.felix.services.ai_chat_startlist_context import (
    FelixAiStartlistContext,
    intersect_felix_ai_startlist_context,
    parse_felix_ai_startlist_context,
    prioritize_felix_ai_activities,
)
from apps.felix.services.wellness_service import FelixWellnessService


Locale = AiChatLocale
"""Supported Felix AI chat response locales."""

FelixAiChatContext = AiChatContextSnapshot
"""Felix alias for the shared wellness-like AI chat context snapshot."""


class FelixAiChatService(BackendAiChatServiceBase):
    """Compose Felix AI chat replies from backend-controlled context.

    Attributes:
        _wellness_service (FelixWellnessService): Existing Felix wellness data
            service used as internal context provider.

    Methods:
        ask: Build one PWA-compatible assistant response.
        consume_quota: Reserve quota for non-LLM assistant features.
    """

    def __init__(self, wellness_service: Optional[FelixWellnessService] = None) -> None:
        """Create the service.

        Args:
            wellness_service (Optional[FelixWellnessService]): Optional service
                override used by tests. Defaults to a live Felix wellness
                service bound to the active database provider.

        Returns:
            None.

        Side Effects:
            May resolve the configured database provider through the wellness
            service constructor.
        """
        self._wellness_service = wellness_service or FelixWellnessService()

    async def ask(self, user_id: str, request: FelixAiChatAskRequest) -> Dict[str, Any]:
        """Return one assistant answer for an authenticated user.

        Args:
            user_id (str): Authenticated user id from the bearer token.
            request (FelixAiChatAskRequest): PWA-compatible chat request.

        Returns:
            Dict[str, Any]: Response dictionary accepted by
            ``FelixAiChatAskResponse``.

        Side Effects:
            Reads existing wellness context for the user.
        """
        request_id = secrets.token_hex(6)
        started_at = time.perf_counter()
        locale = normalize_ai_chat_locale(request.locale)
        intent = resolve_ai_chat_intent(request)
        _log_answer_service_start(
            request_id=request_id,
            locale=locale,
            intent=intent,
            request=request,
        )
        context = await self._load_context(
            user_id,
            request,
            request_id=request_id,
            intent=intent,
            locale=locale,
        )
        startlist_context = intersect_felix_ai_startlist_context(
            parse_felix_ai_startlist_context(request.external_context),
            context.activities,
        )
        answer, response_source = await _resolve_answer(
            request=request,
            context=context,
            locale=locale,
            intent=intent,
            request_id=request_id,
            startlist_context=startlist_context,
        )
        _log_response_built(
            request_id=request_id,
            response_source=response_source,
            answer=answer,
            started_at=started_at,
            context=context,
            startlist_context=startlist_context,
        )
        sources = ["felix-wellness-context"]
        if startlist_context.has_preferences:
            sources.append("felix-startlist-context")
        return self.response(answer=answer, sources=sources)

    async def _load_context(
        self,
        user_id: str,
        request: FelixAiChatAskRequest,
        *,
        request_id: str,
        intent: str,
        locale: Locale,
    ) -> FelixAiChatContext:
        """Load backend-controlled wellness context for one question.

        Args:
            user_id (str): Authenticated user id.
            request (FelixAiChatAskRequest): Request whose categories and
                intent hints decide the context breadth.
            request_id (str): Stable request trace id.
            intent (str): Resolved intent id.
            locale (Locale): Response language.

        Returns:
            FelixAiChatContext: Available context rows. Empty context is
            returned when the provider cannot serve a snapshot.

        Side Effects:
            Reads sync bootstrap data from the wellness service.
        """
        needs_context = ai_chat_needs_backend_context(request)
        log_ai_chat_debug(
            "ai_context_load_start",
            {
                "scope": "felix",
                "request_id": request_id,
                "intent": intent,
                "locale": locale,
                "needs_backend_context": needs_context,
                "requested_categories": request.ai_chat_categories,
                "target_metrics": request.target_metrics,
            },
        )
        if not needs_context:
            log_ai_chat_debug(
                "ai_context_load_result",
                {
                    "scope": "felix",
                    "request_id": request_id,
                    "reason": "backend-context-not-needed",
                    "context": _context_debug_payload(FelixAiChatContext.empty()),
                },
            )
            return FelixAiChatContext.empty()

        started_at = time.perf_counter()
        try:
            result = await self._wellness_service.get_sync_bootstrap(
                user_id=user_id,
                diary_limit=30,
                checkin_limit=30,
            )
        except Exception as exc:
            log_ai_chat_debug(
                "ai_context_load_result",
                {
                    "scope": "felix",
                    "request_id": request_id,
                    "success": False,
                    "reason": "wellness-service-error",
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:500],
                    "elapsed_ms": _elapsed_ms(started_at),
                },
            )
            return FelixAiChatContext.empty()

        if result.get("status") != "success":
            log_ai_chat_debug(
                "ai_context_load_result",
                {
                    "scope": "felix",
                    "request_id": request_id,
                    "success": False,
                    "reason": "wellness-service-status",
                    "status": result.get("status"),
                    "elapsed_ms": _elapsed_ms(started_at),
                },
            )
            return FelixAiChatContext.empty()

        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        context = coerce_ai_chat_context_snapshot(data)
        log_ai_chat_debug(
            "ai_context_load_result",
            {
                "scope": "felix",
                "request_id": request_id,
                "success": True,
                "elapsed_ms": _elapsed_ms(started_at),
                "context": _context_debug_payload(context),
            },
        )
        return context


async def _compose_ai_answer(
    *,
    request: FelixAiChatAskRequest,
    context: FelixAiChatContext,
    locale: Locale,
    intent: str,
    request_id: str,
    startlist_context: FelixAiStartlistContext,
) -> Optional[str]:
    """Try to compose an answer through the configured backend AI provider.

    Args:
        request (FelixAiChatAskRequest): Current AI chat request.
        context (FelixAiChatContext): Backend-owned wellness context.
        locale (Locale): Response language.
        intent (str): Resolved intent id.
        request_id (str): Stable request trace id.
        startlist_context (FelixAiStartlistContext): Catalog-validated,
            device-local Startlist preference hint.

    Returns:
        Optional[str]: Provider answer with an action block, or None when no
        backend provider is configured or reachable.

    Side Effects:
        May call the backend-configured AI completion provider.
    """
    activities = prioritize_felix_ai_activities(
        context.activities,
        startlist_context,
    )
    provider_context = FelixAiChatContext(
        activities=activities,
        diary_entries=context.diary_entries,
        checkins=context.checkins,
    )
    activity = _select_activity(
        activities,
        request.target_metrics,
        startlist_context,
    )
    _log_activity_selection(
        request_id, intent, request.target_metrics, activity, startlist_context
    )
    messages = _ai_completion_messages(
        request=request,
        context=provider_context,
        locale=locale,
        intent=intent,
        activity=activity,
        startlist_context=startlist_context,
    )
    _log_prompt_built(request_id, intent, locale, messages, context)
    raw_answer = await call_ai_chat_completion(
        messages,
        json_mode=True,
        trace_context={
            "scope": "felix",
            "request_id": request_id,
            "completion_phase": "initial",
            "intent": intent,
        },
    )
    if not raw_answer:
        return None

    followup_answer = await _maybe_answer_with_requested_tools(
        messages=messages,
        raw_answer=raw_answer,
        context=provider_context,
        request_id=request_id,
    )
    if followup_answer:
        return followup_answer

    return _render_provider_answer(raw_answer, provider_context, request_id=request_id)


async def _resolve_answer(
    *,
    request: FelixAiChatAskRequest,
    context: FelixAiChatContext,
    locale: Locale,
    intent: str,
    request_id: str,
    startlist_context: FelixAiStartlistContext,
) -> Tuple[str, str]:
    """Resolve a provider answer or deterministic fallback.

    Args:
        request (FelixAiChatAskRequest): Current AI chat request.
        context (FelixAiChatContext): Backend-owned wellness context.
        locale (Locale): Normalized response locale.
        intent (str): Resolved request intent.
        request_id (str): Stable request trace ID.
        startlist_context (FelixAiStartlistContext): Validated Startlist hint.

    Returns:
        Tuple[str, str]: Final answer and ``"provider"`` or ``"fallback"``
            source marker.

    Side Effects:
        May call the configured AI provider and writes fallback diagnostics.
    """
    answer = await _compose_ai_answer(
        request=request,
        context=context,
        locale=locale,
        intent=intent,
        request_id=request_id,
        startlist_context=startlist_context,
    )
    if answer is not None:
        return answer, "provider"
    log_ai_chat_debug(
        "ai_fallback_answer_start",
        {
            "scope": "felix",
            "request_id": request_id,
            "reason": "provider-unavailable-or-empty",
            "intent": intent,
        },
    )
    return (
        _compose_answer(
            request=request,
            context=context,
            locale=locale,
            intent=intent,
            startlist_context=startlist_context,
        ),
        "fallback",
    )


def _ai_completion_messages(
    *,
    request: FelixAiChatAskRequest,
    context: FelixAiChatContext,
    locale: Locale,
    intent: str,
    activity: Optional[Dict[str, Any]],
    startlist_context: FelixAiStartlistContext,
) -> List[Dict[str, str]]:
    """Build provider messages for the Felix AI chat completion call.

    Args:
        request (FelixAiChatAskRequest): Current AI chat request.
        context (FelixAiChatContext): Backend-owned wellness context.
        locale (Locale): Response language.
        intent (str): Resolved intent id.
        activity (Optional[Dict[str, Any]]): Preselected activity suggestion.
        startlist_context (FelixAiStartlistContext): Catalog-validated,
            device-local Startlist preference hint.

    Returns:
        List[Dict[str, str]]: OpenAI-compatible message rows.

    Side Effects:
        None.
    """
    language = "German" if locale == "de" else "English"
    lines = [
        "You are Felix KI, a careful wellbeing assistant inside the Felix app.",
        f"Answer in {language}.",
        "Use Felix backend context as the source of truth for personalized claims.",
        "Use general knowledge only for gentle explanation and never contradict Felix context.",
        "If context is sparse, state that briefly and give practical low-risk next steps.",
        "Keep responses concise, warm, and actionable.",
        "Do not provide medical diagnosis, emergency instructions, or crisis handling.",
        "Do not expose backend IDs in visible answer text; put IDs only in actions.",
        "Resolved intent: " + intent,
        _wellness_instruction_block(context),
        _context_prompt(
            context,
            activity,
            startlist_context,
        ),
    ]
    if request.custom_prompt:
        lines.append("Client context hint:\n" + request.custom_prompt.strip())

    messages: List[Dict[str, str]] = [
        {"role": "system", "content": "\n\n".join(lines)},
        {"role": "system", "content": _structured_response_instruction(locale)},
    ]
    for item in request.history[-12:]:
        messages.append({"role": item.role, "content": item.content})
    messages.append({"role": "user", "content": request.question})
    return messages


def _render_provider_answer(
    raw_answer: str,
    context: FelixAiChatContext,
    *,
    request_id: str,
) -> str:
    """Render a provider response for the legacy Flutter action-block client.

    Args:
        raw_answer (str): Raw provider response text.
        context (FelixAiChatContext): Backend-owned context used for action
            validation.
        request_id (str): Stable request trace id.

    Returns:
        str: Visible answer with an optional hidden action block. If the
        provider returned no valid actions, no client buttons are emitted.

    Side Effects:
        None.
    """
    answer = raw_answer.strip()
    if not answer:
        log_ai_chat_debug(
            "ai_completion_parse_result",
            {
                "scope": "felix",
                "request_id": request_id,
                "success": False,
                "reason": "empty-provider-answer",
            },
        )
        return answer
    if _has_action_block(answer):
        log_ai_chat_debug(
            "ai_completion_parse_result",
            {
                "scope": "felix",
                "request_id": request_id,
                "success": True,
                "format": "legacy-action-block",
                "answer_chars": len(answer),
            },
        )
        return answer

    payload = _parse_structured_provider_payload(answer)
    if payload is None:
        log_ai_chat_debug(
            "ai_completion_parse_result",
            {
                "scope": "felix",
                "request_id": request_id,
                "success": False,
                "reason": "no-json-payload",
                "raw_answer_chars": len(answer),
                **({"raw_answer": answer} if is_ai_chat_prompt_logging_enabled() else {}),
            },
        )
        return answer

    visible = _format_answer_text(str(payload.get("answer") or ""))
    if not visible:
        log_ai_chat_debug(
            "ai_completion_parse_result",
            {
                "scope": "felix",
                "request_id": request_id,
                "success": False,
                "reason": "empty-visible-answer",
                "payload_keys": sorted(str(key) for key in payload.keys()),
            },
        )
        return answer

    moderation = payload.get("moderation") if isinstance(payload.get("moderation"), dict) else {}
    category = str(moderation.get("category") or "in_scope").strip().lower()
    raw_actions = payload.get("actions")
    raw_tool_requests = payload.get("tool_requests")
    actions = [] if category != "in_scope" else _sanitize_provider_actions(
        raw_actions,
        context,
    )
    log_ai_chat_debug(
        "ai_completion_parse_result",
        {
            "scope": "felix",
            "request_id": request_id,
            "success": True,
            "format": "structured-json",
            "payload_keys": sorted(str(key) for key in payload.keys()),
            "visible_answer_chars": len(visible),
            "raw_action_count": len(raw_actions) if isinstance(raw_actions, list) else 0,
            "raw_tool_request_count": len(raw_tool_requests)
            if isinstance(raw_tool_requests, list)
            else 0,
            "moderation": moderation,
            **({"payload": payload} if is_ai_chat_prompt_logging_enabled() else {}),
        },
    )
    log_ai_chat_debug(
        "ai_action_validation_result",
        {
            "scope": "felix",
            "request_id": request_id,
            "moderation_category": category,
            "visible_answer_chars": len(visible),
            "actions_before_validation": _extract_raw_action_debug(raw_actions),
            "actions_after_validation": _extract_action_debug(actions),
        },
    )
    if not actions:
        return visible
    return f"{visible}\n\n{build_ai_chat_action_block(actions)}"


def _format_answer_text(answer: str) -> str:
    """Normalize provider-visible answer text before it reaches clients.

    Args:
        answer (str): Model-provided user-visible answer text.

    Returns:
        str: Trimmed text with transport escapes normalized and noisy
        generated labels demoted.

    Side Effects:
        None.
    """
    text = (
        str(answer or "")
        .replace("\\r\\n", "\n")
        .replace("\\n", "\n")
        .replace("\\t", "  ")
        .strip()
    )
    if not text:
        return ""
    text = re.sub(r"[ \t]+(?=\d+[.)]\s+\*\*)", "\n\n", text)
    text = re.sub(r"[ \t]+(?=(?:[-*•]|\d+[.)])\s+)", "\n", text)
    text = re.sub(r"\s*\(ID=[^)]+\)", "", text, flags=re.IGNORECASE)
    text = _demote_label_only_list_items(text)
    text = _demote_intro_label_bold(text)
    text = re.sub(r"\n\s*\n(?=\s*(?:[-*•]|\d+[.)])\s+)", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _demote_label_only_list_items(text: str) -> str:
    """Convert standalone bold-label bullets into plain labels.

    Args:
        text (str): User-visible answer text after whitespace normalization.

    Returns:
        str: Text with list items that contain only a bold label demoted.

    Side Effects:
        None.
    """
    return re.sub(
        r"(?m)^\s*[-*]\s+\*\*([^*\n]{1,64}:)\*\*\s*$",
        r"\1",
        text,
    )


def _demote_intro_label_bold(text: str) -> str:
    """Remove bold styling from common introductory labels.

    Args:
        text (str): User-visible answer text after list-label cleanup.

    Returns:
        str: Text with common intro labels kept as plain prose.

    Side Effects:
        None.
    """
    return re.sub(
        r"(?m)^\*\*((?:Kurz gesagt|Hinweis|Wichtig|In short|Note|Important):)\*\*\s*",
        r"\1 ",
        text,
    )


async def _maybe_answer_with_requested_tools(
    *,
    messages: List[Dict[str, str]],
    raw_answer: str,
    context: FelixAiChatContext,
    request_id: str,
) -> Optional[str]:
    """Run one backend-only follow-up completion for model-requested context.

    The PWA lets the model request a narrow, backend-owned tool before the
    final answer. This implementation supports the same shape for activity
    category lookups while keeping tools and provider credentials completely
    server-side.

    Args:
        messages (List[Dict[str, str]]): Original completion messages.
        raw_answer (str): First raw provider response.
        context (FelixAiChatContext): Backend-owned Felix context.
        request_id (str): Stable request trace id.

    Returns:
        Optional[str]: Final answer rendered for the legacy action-block
        frontend, or None when no follow-up is needed or possible.

    Side Effects:
        May call the backend-configured AI completion provider one additional
        time.
    """
    payload = _parse_structured_provider_payload(raw_answer)
    if payload is None:
        log_ai_chat_debug(
            "ai_followup_tool_decision",
            {
                "scope": "felix",
                "request_id": request_id,
                "will_followup": False,
                "reason": "initial-answer-not-json",
            },
        )
        return None

    moderation = payload.get("moderation") if isinstance(payload.get("moderation"), dict) else {}
    if str(moderation.get("category") or "in_scope").strip().lower() != "in_scope":
        log_ai_chat_debug(
            "ai_followup_tool_decision",
            {
                "scope": "felix",
                "request_id": request_id,
                "will_followup": False,
                "reason": "moderation-not-in-scope",
                "moderation": moderation,
            },
        )
        return None

    raw_tool_requests = payload.get("tool_requests")
    tool_snippets = _execute_provider_tool_requests(raw_tool_requests, context)
    followup_context = _render_followup_tool_context(tool_snippets)
    log_ai_chat_debug(
        "ai_followup_tool_decision",
        {
            "scope": "felix",
            "request_id": request_id,
            "will_followup": bool(followup_context),
            "reason": "tool-context-ready" if followup_context else "no-valid-tool-context",
            "requested_tools": _extract_tool_request_debug(raw_tool_requests),
            "tool_result_count": len(tool_snippets),
            **({"tool_context": followup_context} if is_ai_chat_prompt_logging_enabled() else {}),
        },
    )
    if not followup_context:
        return None

    followup_messages = [
        *messages,
        {"role": "system", "content": followup_context},
    ]
    raw_followup = await call_ai_chat_completion(
        followup_messages,
        json_mode=True,
        trace_context={
            "scope": "felix",
            "request_id": request_id,
            "completion_phase": "tool_followup",
        },
    )
    if not raw_followup:
        return None
    return _render_provider_answer(raw_followup, context, request_id=request_id)


def _parse_structured_provider_payload(raw_answer: str) -> Optional[Dict[str, Any]]:
    """Parse a provider JSON object from raw response text.

    Args:
        raw_answer (str): Raw response text, ideally a single JSON object.

    Returns:
        Optional[Dict[str, Any]]: Parsed object or None when no JSON object can
        be recovered.

    Side Effects:
        None.
    """
    stripped = raw_answer.strip()
    if stripped.startswith("```"):
        stripped = stripped.removeprefix("```json").removeprefix("```").strip()
        stripped = stripped.removesuffix("```").strip()

    candidates = [stripped]
    first = stripped.find("{")
    last = stripped.rfind("}")
    if first >= 0 and last > first:
        candidates.append(stripped[first : last + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _execute_provider_tool_requests(
    raw_tool_requests: Any,
    context: FelixAiChatContext,
) -> List[Dict[str, str]]:
    """Execute validated model-requested backend context tools.

    Args:
        raw_tool_requests (Any): Provider ``tool_requests`` value.
        context (FelixAiChatContext): Backend-owned context snapshot.

    Returns:
        List[Dict[str, str]]: Context snippets for a second completion call.

    Side Effects:
        None. The current implementation works from already-loaded backend
        context, so no extra database roundtrip is required.
    """
    if not isinstance(raw_tool_requests, list):
        return []

    snippets: List[Dict[str, str]] = []
    for item in raw_tool_requests:
        if len(snippets) >= 1:
            break
        if not isinstance(item, dict):
            continue
        if str(item.get("tool") or "").strip() != "activities.category.read_activities":
            continue
        category_id = str(item.get("category_id") or "").strip()
        category_name = str(item.get("category_name") or "").strip()
        activities = _activities_for_category(context.activities, category_id)
        if not activities:
            continue
        snippets.append(
            {
                "provider": "activities.category.read_activities",
                "title": category_name or category_id or "Activity category",
                "content": _render_activity_tool_result(activities),
            }
        )
    return snippets


def _activities_for_category(
    activities: List[Dict[str, Any]],
    category_id: str,
) -> List[Dict[str, Any]]:
    """Return activities whose category keys contain a requested category id.

    Args:
        activities (List[Dict[str, Any]]): Available activity context rows.
        category_id (str): Category id requested by the model.

    Returns:
        List[Dict[str, Any]]: Matching activity rows, bounded for prompt size.

    Side Effects:
        None.
    """
    normalized = category_id.strip()
    if not normalized:
        return []
    matches = [
        activity
        for activity in activities
        if normalized in {str(key).strip() for key in activity.get("category_keys") or []}
    ]
    return matches[:8]


def _render_activity_tool_result(activities: List[Dict[str, Any]]) -> str:
    """Render activity rows as provider-readable follow-up tool context.

    Args:
        activities (List[Dict[str, Any]]): Activity rows selected by the
            backend-only tool.

    Returns:
        str: Compact text containing exact IDs and relevant metadata.

    Side Effects:
        None.
    """
    lines = ["Backend tool result: activities.category.read_activities"]
    for item in activities:
        lines.append(
            "- "
            f"id={_prompt_value(item.get('id'))}; "
            f"name={_activity_name(item)}; "
            f"duration={item.get('duration_minutes') or 1}; "
            f"favorite={bool(item.get('favorite'))}; "
            f"summary={_prompt_value(item.get('summary'))}; "
            f"categories={_prompt_value(item.get('category_keys'))}"
        )
    return "\n".join(lines)


def _render_followup_tool_context(snippets: List[Dict[str, str]]) -> str:
    """Render validated tool snippets for a second completion call.

    Args:
        snippets (List[Dict[str, str]]): Backend-only tool result snippets.

    Returns:
        str: System message content for the second completion, or an empty
        string when no snippets are available.

    Side Effects:
        None.
    """
    if not snippets:
        return ""
    lines = [
        "Backend-only follow-up context from validated internal tools.",
        "Use this context to answer now. Do not request tools again.",
    ]
    for index, snippet in enumerate(snippets, start=1):
        lines.append(
            f"[Tool {index}] provider={snippet.get('provider', 'internal')} "
            f"| title={snippet.get('title', 'Tool result')}\n"
            f"{snippet.get('content', '')}"
        )
    return "\n\n".join(lines)


def _extract_raw_action_debug(raw_actions: Any) -> List[Dict[str, str]]:
    """Extract safe debug fields from raw provider action hints.

    Args:
        raw_actions (Any): Provider ``actions`` value.

    Returns:
        List[Dict[str, str]]: Up to five action dictionaries with only stable
        action metadata.

    Side Effects:
        None.
    """
    if not isinstance(raw_actions, list):
        return []

    extracted: List[Dict[str, str]] = []
    for item in raw_actions[:5]:
        if not isinstance(item, dict):
            continue
        extracted.append(
            {
                "type": str(item.get("type") or ""),
                "activity_id": str(item.get("activity_id") or ""),
                "activity_name": str(item.get("activity_name") or ""),
                "category_id": str(item.get("category_id") or ""),
                "category_name": str(item.get("category_name") or ""),
            }
        )
    return extracted


def _extract_action_debug(actions: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Extract safe debug fields from sanitized action hints.

    Args:
        actions (List[Dict[str, str]]): Sanitized action dictionaries.

    Returns:
        List[Dict[str, str]]: Up to five stable action summaries.

    Side Effects:
        None.
    """
    return [
        {
            "type": str(action.get("type") or ""),
            "activity_id": str(action.get("activity_id") or ""),
            "activity_name": str(action.get("activity_name") or ""),
            "category_id": str(action.get("category_id") or ""),
            "category_name": str(action.get("category_name") or ""),
        }
        for action in actions[:5]
    ]


def _extract_tool_request_debug(raw_tool_requests: Any) -> List[Dict[str, str]]:
    """Extract safe debug fields from provider tool requests.

    Args:
        raw_tool_requests (Any): Provider ``tool_requests`` value.

    Returns:
        List[Dict[str, str]]: Up to three internal tool request summaries.

    Side Effects:
        None.
    """
    if not isinstance(raw_tool_requests, list):
        return []

    extracted: List[Dict[str, str]] = []
    for item in raw_tool_requests[:3]:
        if not isinstance(item, dict):
            continue
        extracted.append(
            {
                "tool": str(item.get("tool") or ""),
                "category_id": str(item.get("category_id") or ""),
                "category_name": str(item.get("category_name") or ""),
                "metric": str(item.get("metric") or ""),
                "reason": str(item.get("reason") or "")[:180],
            }
        )
    return extracted


def _sanitize_provider_actions(
    raw_actions: Any,
    context: FelixAiChatContext,
) -> List[Dict[str, str]]:
    """Validate provider action hints against the current backend context.

    Args:
        raw_actions (Any): Provider ``actions`` value.
        context (FelixAiChatContext): Backend-owned context with activities.

    Returns:
        List[Dict[str, str]]: Up to three sanitized action dictionaries.

    Side Effects:
        None.
    """
    if not isinstance(raw_actions, list):
        return []

    valid_activity_ids = {
        str(activity.get("id") or "").strip()
        for activity in context.activities
        if str(activity.get("id") or "").strip()
    }
    valid_category_ids = {
        str(category).strip()
        for activity in context.activities
        for category in (activity.get("category_keys") or [])
        if str(category).strip()
    }
    allowed_simple = {
        "start_breathing",
        "open_checkin",
        "start_flow",
        "open_activities",
        "open_pro",
        "open_notifications",
        "open_diary",
        "send_feedback_email",
    }
    sanitized: List[Dict[str, str]] = []
    for item in raw_actions:
        if not isinstance(item, dict):
            continue
        action_type = str(item.get("type") or "").strip()
        if action_type in allowed_simple:
            sanitized.append({"type": action_type})
            continue
        if action_type == "start_activity":
            action = _sanitize_start_activity_action(item, valid_activity_ids)
            if action:
                sanitized.append(action)
            continue
        if action_type == "open_activity_category":
            action = _sanitize_category_action(item, valid_category_ids)
            if action:
                sanitized.append(action)
        if len(sanitized) >= 3:
            break
    return sanitized[:3]


def _sanitize_start_activity_action(
    item: Dict[str, Any],
    valid_activity_ids: set[str],
) -> Optional[Dict[str, str]]:
    """Validate one ``start_activity`` action.

    Args:
        item (Dict[str, Any]): Raw provider action.
        valid_activity_ids (set[str]): Existing activity IDs in backend
            context.

    Returns:
        Optional[Dict[str, str]]: Sanitized action or None.

    Side Effects:
        None.
    """
    activity_id = str(item.get("activity_id") or "").strip()
    activity_name = str(item.get("activity_name") or "").strip()
    if activity_id and activity_id in valid_activity_ids:
        return {"type": "start_activity", "activity_id": activity_id}
    if activity_name:
        return {"type": "start_activity", "activity_name": activity_name}
    return None


def _sanitize_category_action(
    item: Dict[str, Any],
    valid_category_ids: set[str],
) -> Optional[Dict[str, str]]:
    """Validate one ``open_activity_category`` action.

    Args:
        item (Dict[str, Any]): Raw provider action.
        valid_category_ids (set[str]): Existing category IDs visible in
            activity context.

    Returns:
        Optional[Dict[str, str]]: Sanitized category action or None.

    Side Effects:
        None.
    """
    category_id = str(item.get("category_id") or "").strip()
    category_name = str(item.get("category_name") or "").strip()
    if category_id and (not valid_category_ids or category_id in valid_category_ids):
        action = {"type": "open_activity_category", "category_id": category_id}
        if category_name:
            action["category_name"] = category_name
        return action
    if category_name:
        return {"type": "open_activity_category", "category_name": category_name}
    return None


def _structured_response_instruction(locale: Locale) -> str:
    """Build the PWA-style final response contract for the provider.

    Args:
        locale (Locale): Active response locale.

    Returns:
        str: System instruction requiring structured JSON output.

    Side Effects:
        None.
    """
    language = "German" if locale == "de" else "English"
    return (
        "FINAL RESPONSE FORMAT - MUST FOLLOW EXACTLY:\n"
        "Return exactly one valid JSON object and no markdown fences, prose, or extra text.\n"
        "Schema:\n"
        "{\n"
        '  "answer": "user visible answer text using the supported Felix markdown subset",\n'
        '  "actions": [\n'
        '    {"type": "start_activity", "activity_id": "existing activity id"},\n'
        '    {"type": "start_activity", "activity_name": "new activity idea"},\n'
        '    {"type": "start_breathing"},\n'
        '    {"type": "open_checkin"},\n'
        '    {"type": "start_flow"},\n'
        '    {"type": "open_activities"},\n'
        '    {"type": "open_activity_category", "category_id": "existing category id"},\n'
        '    {"type": "open_diary"}\n'
        "  ],\n"
        '  "tool_requests": [\n'
        '    {\n'
        '      "tool": "activities.category.read_activities",\n'
        '      "category_id": "existing category id",\n'
        '      "reason": "why more concrete activities from this category are needed"\n'
        '    }\n'
        "  ],\n"
        '  "moderation": {\n'
        '    "category": "in_scope|off_topic|abusive|extremist",\n'
        '    "severity": "none|low|medium|high",\n'
        '    "apply_penalty": false,\n'
        '    "notify_admin": false,\n'
        '    "reason": "short internal reason"\n'
        "  }\n"
        "}\n"
        f"Answer text and new user-visible labels must be in {language}.\n"
        "Use category=in_scope only for wellbeing, self-care, reflection, relationships, or Felix app functionality.\n"
        "Use category=off_topic for unrelated requests. Redirect warmly to wellbeing/self-care and leave actions empty.\n"
        "Use category=abusive for harassment and category=extremist for extremist ideology or propaganda. Leave actions empty.\n"
        "SUPPORTED FELIX MARKDOWN IN answer - USE SPARINGLY:\n"
        "- Prefer plain short paragraphs. Use markdown only when it improves scanability.\n"
        "- Use at most one list in a normal answer, with no more than 3 items.\n"
        "- Bold only the key phrase of an item when helpful, e.g. '- **Atmen:** 4 ruhige Atemzuege.'\n"
        "- Do not use headings, tables, code fences, blockquotes, links, HTML, images, emojis, or horizontal rules.\n"
        "- Do not expose activity IDs in answer text; put IDs only in actions.\n"
        "ACTION RULES:\n"
        "- The actions array may contain at most 3 useful actions and may be empty.\n"
        "- Only return actions that should become visible buttons.\n"
        "- For start_activity with activity_id, use an exact existing activity id from backend context.\n"
        "- For a new activity idea, use activity_name and no invented activity_id.\n"
        "- For open_activity_category with category_id, use an exact category id visible in backend context.\n"
        "- If a promising category needs more activity detail before answering, request at most one "
        "tool_requests item with tool=activities.category.read_activities and an exact category_id.\n"
        "- When backend tool context is provided, answer directly and keep tool_requests empty.\n"
        "- If recommending a generic breathing exercise that is not an exact existing activity, use start_breathing.\n"
    )


def _wellness_instruction_block(context: FelixAiChatContext) -> str:
    """Build wellness reasoning instructions adapted from the PWA flow.

    Args:
        context (FelixAiChatContext): Backend-owned context snapshot.

    Returns:
        str: Static instruction block or an empty string when no wellness
        context is available.

    Side Effects:
        None.
    """
    has_checkins = bool(context.checkins)
    has_activities = bool(context.activities)
    if not has_checkins and not has_activities:
        return ""

    sections = [
        "Wellness-Metrik-Skala (einheitlich für ALLE Metriken inkl. Angst, Schmerz und Stress):\n"
        "  niedrig = sehr schlecht / sehr belastet / unterversorgt\n"
        "  neutral = ausgeglichen / mittig (praktisch irrelevant)\n"
        "  hoch = sehr gut / sehr positiv / ressourciert\n"
        "Alle Metriken folgen derselben Richtung; invertiere Werte NICHT.\n"
        "Nur ausdrücklich bereitgestellte Metrikwerte wurden erfasst. "
        "Erfinde KEINE neutralen Standardwerte für fehlende Metriken.\n"
        "Nenne in sichtbaren Antworten NIEMALS numerische Metrikwerte, /10-Werte "
        "oder Skalenpunkte. Beschreibe Zustände ausschließlich in Worten.",
    ]
    if has_checkins:
        sections.append(
            "Check-in-Interpretation:\n"
            "- Deutlich niedrige Werte sind Hindernisse - hier braucht der Nutzer Hilfe.\n"
            "- Deutlich hohe Werte sind verfügbare Kapazitäten/Ressourcen.\n"
            "- Neutrale Werte wurden als ausgeglichen gefiltert und nicht gesendet.\n"
            "- Priorisiere in deiner Antwort die negativsten Werte als Hauptfokus.\n"
            "- Positive Werte ehren, aber als Ressource rahmen.\n"
            "- Wenn du dich auf Metriken beziehst, nenne nur die qualitative Beschreibung."
        )
    if has_activities:
        sections.append(
            "Aktivitäts-Empfehlungen:\n"
            "- Bevorzuge Aktivitäten mit hoher gewichteter Bewertung (kürzlich + positiv).\n"
            "- Schlage NIEMALS schädliche Muster als positive Empfehlung vor.\n"
            "- Bei schädlichen Mustern: sanft auf Alternativen hinweisen.\n"
            "- Nutze nur die bereitgestellten Aktivitäts-IDs für Aktionsblöcke.\n"
            "- Favoriten und Startlisten-Aktivitäten sind vom Nutzer bevorzugt - "
            "priorisiere sie bei gleicher Eignung.\n"
            "- Schlage maximal 2-3 konkrete Aktivitäten vor, nicht mehr."
        )
    if has_checkins and has_activities:
        sections.append(
            "Kreuz-Metrik-Logik (WICHTIG):\n"
            "- Niedrige Angstfreiheit + niedrige Energie -> beruhigende, energiearme Aktivitäten "
            "vorschlagen, NICHT angstfordernde Übungen.\n"
            "- Niedrige Stressbewältigung + niedrige Energie -> Regeneration priorisieren, "
            "keine anspruchsvollen Aufgaben vorschlagen.\n"
            "- Niedrige Stimmung + hohe Energie -> aktive, stimmungshebende Aktivitäten.\n"
            "- Niedrige Stimmung + niedrige Energie -> minimale, sanfte Schritte.\n"
            "- Aktivitäten für eine belastete Metrik nur dann vorschlagen, wenn der "
            "Nutzer genug Kapazität in anderen Metriken hat."
        )
    return "\n\n".join(sections)


def _context_prompt(
    context: FelixAiChatContext,
    activity: Optional[Dict[str, Any]],
    startlist_context: FelixAiStartlistContext,
) -> str:
    """Render bounded backend context for the provider prompt.

    Args:
        context (FelixAiChatContext): Backend-owned wellness context.
        activity (Optional[Dict[str, Any]]): Preselected activity suggestion.
        startlist_context (FelixAiStartlistContext): Catalog-validated,
            device-local Startlist preference hint.

    Returns:
        str: Context prompt section.

    Side Effects:
        None.
    """
    lines = ["Backend Felix context:"]
    if startlist_context.has_preferences:
        lines.append(
            "Startlist preference: prefer current-tier activities first, "
            "then automatic-tier activities, when they fit the user's need."
        )
    if activity:
        lines.append(
            "Preselected fitting activity: "
            f"id={activity.get('id')}; name={_activity_name(activity)}; "
            f"duration={activity.get('duration_minutes') or 1} minutes."
        )

    if context.activities:
        lines.append("Activities:")
        for item in context.activities[:10]:
            startlist_tier = startlist_context.membership(item.get("id")) or "none"
            lines.append(
                "- "
                f"id={_prompt_value(item.get('id'))}; "
                f"name={_activity_name(item)}; "
                f"duration={item.get('duration_minutes') or 1}; "
                f"favorite={bool(item.get('favorite'))}; "
                f"startlist={startlist_tier}; "
                f"summary={_prompt_value(item.get('summary'))}"
            )

    if context.checkins:
        lines.append("Recent check-ins:")
        for item in context.checkins[:8]:
            lines.append(
                "- "
                f"time={_prompt_value(item.get('created_at') or item.get('timestamp'))}; "
                f"mood={_prompt_value(item.get('mood_key') or item.get('mood'))}; "
                f"stress={_prompt_value(item.get('stress_key') or item.get('stress'))}; "
                f"energy={_prompt_value(item.get('energy_key') or item.get('energy'))}"
            )

    if context.diary_entries:
        lines.append("Recent diary entries:")
        for item in context.diary_entries[:6]:
            lines.append(
                "- "
                f"title={_prompt_value(item.get('title'))}; "
                f"summary={_prompt_value(item.get('summary'))}"
            )

    if len(lines) == 1:
        lines.append("No personalized backend context is currently available.")
    return "\n".join(lines)


def _compose_answer(
    *,
    request: FelixAiChatAskRequest,
    context: FelixAiChatContext,
    locale: Locale,
    intent: str,
    startlist_context: FelixAiStartlistContext,
) -> str:
    """Compose a cautious text-only fallback assistant answer.

    Args:
        request (FelixAiChatAskRequest): Current AI chat request.
        context (FelixAiChatContext): Backend-owned wellness context.
        locale (Locale): Response language.
        intent (str): Resolved intent id.
        startlist_context (FelixAiStartlistContext): Catalog-validated,
            device-local Startlist preference hint.

    Returns:
        str: Visible assistant answer without action buttons. Structured
        provider responses are the only source of action hints.

    Side Effects:
        None.
    """
    activities = prioritize_felix_ai_activities(
        context.activities,
        startlist_context,
    )
    activity = _select_activity(
        activities,
        request.target_metrics,
        startlist_context,
    )
    context_line = _context_summary(context, locale)
    if intent == "activity_recommendation":
        visible = _activity_answer(activity, context_line, locale)
    elif intent == "progress_analysis":
        visible = _progress_answer(context, context_line, locale)
    elif intent == "state_reflection":
        visible = _state_answer(activity, context_line, locale)
    else:
        visible = _general_answer(context_line, locale)

    return visible


def _activity_answer(
    activity: Optional[Dict[str, Any]],
    context_line: str,
    locale: Locale,
) -> str:
    """Build an activity-recommendation answer.

    Args:
        activity (Optional[Dict[str, Any]]): Selected activity row.
        context_line (str): Human-readable context availability summary.
        locale (Locale): Response language.

    Returns:
        str: Visible answer.
    """
    if locale == "de":
        if activity:
            name = _activity_name(activity)
            minutes = int(activity.get("duration_minutes") or 1)
            return (
                f"{context_line}\n\n"
                "Was dir jetzt gut tun kann:\n"
                "1. Nimm zuerst einen ruhigen Atemzug und senke die Hürde.\n"
                f"2. Starte **{name}** für etwa {minutes} Minuten.\n"
                "3. Logge danach kurz, wie es dir geht, damit Felix besser lernt, was wirkt."
            )
        return (
            f"{context_line}\n\n"
            "Ich habe noch keine passende Aktivität im Katalog gefunden. Starte mit "
            "einem kurzen Check-in oder öffne die Aktivitäten, damit Felix beim "
            "nächsten Mal konkreter empfehlen kann."
        )

    if activity:
        name = _activity_name(activity)
        minutes = int(activity.get("duration_minutes") or 1)
        return (
            f"{context_line}\n\n"
            "What may help now:\n"
            "1. Take one calm breath and lower the bar.\n"
            f"2. Start **{name}** for about {minutes} minutes.\n"
            "3. Log how you feel afterward so Felix can learn what works."
        )
    return (
        f"{context_line}\n\n"
        "I do not have a fitting activity in your catalog yet. Start with a quick "
        "check-in or open activities so Felix can make better recommendations next time."
    )


def _progress_answer(
    context: FelixAiChatContext,
    context_line: str,
    locale: Locale,
) -> str:
    """Build a progress-analysis answer.

    Args:
        context (FelixAiChatContext): Backend-owned wellness context.
        context_line (str): Context availability summary.
        locale (Locale): Response language.

    Returns:
        str: Visible answer.
    """
    checkin_count = len(context.checkins)
    diary_count = len(context.diary_entries)
    if locale == "de":
        return (
            f"{context_line}\n\n"
            f"Ich sehe aktuell {checkin_count} Check-ins und {diary_count} "
            "Tagebuchsignale im Backend-Kontext. Für belastbare Muster bleibe ich "
            "vorsichtig: Achte als Nächstes darauf, nach Aktivitäten kurz zu loggen, "
            "ob Stress, Energie oder Stimmung besser wurden."
        )
    return (
        f"{context_line}\n\n"
        f"I currently see {checkin_count} check-ins and {diary_count} diary "
        "signals in backend context. I will stay cautious on patterns: next, try "
        "logging briefly after activities whether stress, energy, or mood changed."
    )


def _state_answer(
    activity: Optional[Dict[str, Any]],
    context_line: str,
    locale: Locale,
) -> str:
    """Build a current-state reflection answer.

    Args:
        activity (Optional[Dict[str, Any]]): Selected activity row.
        context_line (str): Context availability summary.
        locale (Locale): Response language.

    Returns:
        str: Visible answer.
    """
    if locale == "de":
        suggestion = (
            f"Wenn du direkt handeln möchtest, passt **{_activity_name(activity)}** als kleiner nächster Schritt."
            if activity
            else "Wenn du direkt handeln möchtest, starte mit einem kurzen Check-in und wähle danach eine kleine Aktivität."
        )
        return (
            f"{context_line}\n\n"
            "Ich würde es klein halten: benenne kurz, was gerade am stärksten ist, "
            "entscheide dich für einen nächsten Mini-Schritt, und prüfe danach, ob "
            f"sich etwas verändert hat. {suggestion}"
        )

    suggestion = (
        f"If you want to act now, **{_activity_name(activity)}** is a good small next step."
        if activity
        else "If you want to act now, start with a quick check-in and then choose one small activity."
    )
    return (
        f"{context_line}\n\n"
        "I would keep this small: name what feels strongest right now, choose one "
        "tiny next step, and check afterward whether anything shifted. "
        f"{suggestion}"
    )


def _general_answer(context_line: str, locale: Locale) -> str:
    """Build a general support answer.

    Args:
        context_line (str): Context availability summary.
        locale (Locale): Response language.

    Returns:
        str: Visible answer.
    """
    if locale == "de":
        return (
            f"{context_line}\n\n"
            "Ich kann dir beim Sortieren, Reflektieren und beim Finden kleiner "
            "nächster Schritte helfen. Am besten fragst du konkret: was los ist, "
            "welche Energie du gerade hast, und ob du eher Beruhigung, Klarheit "
            "oder eine Aktivität möchtest."
        )
    return (
        f"{context_line}\n\n"
        "I can help you sort thoughts, reflect, and find small next steps. The "
        "best questions say what is happening, how much energy you have, and "
        "whether you want calming, clarity, or an activity."
    )


def _context_summary(context: FelixAiChatContext, locale: Locale) -> str:
    """Summarize available backend context.

    Args:
        context (FelixAiChatContext): Loaded context rows.
        locale (Locale): Response language.

    Returns:
        str: Short localized context summary.
    """
    if locale == "de":
        if not context.activities and not context.checkins and not context.diary_entries:
            return "Hinweis: Ich habe gerade nur wenig Backend-Kontext und bleibe deshalb vorsichtig."
        return (
            "Ich nutze deinen Felix-Kontext vorsichtig: "
            f"{len(context.activities)} Aktivitäten, "
            f"{len(context.checkins)} Check-ins und "
            f"{len(context.diary_entries)} Tagebucheinträge."
        )
    if not context.activities and not context.checkins and not context.diary_entries:
        return "Note: I only have limited backend context right now, so I will stay cautious."
    return (
        "I am using your Felix context cautiously: "
        f"{len(context.activities)} activities, "
        f"{len(context.checkins)} check-ins, and "
        f"{len(context.diary_entries)} diary entries."
    )


def _select_activity(
    activities: List[Dict[str, Any]],
    target_metrics: List[str],
    startlist_context: FelixAiStartlistContext,
) -> Optional[Dict[str, Any]]:
    """Select a fitting activity row for the current answer.

    Args:
        activities (List[Dict[str, Any]]): Activity catalog rows.
        target_metrics (List[str]): Metric ids requested by the client.
        startlist_context (FelixAiStartlistContext): Catalog-validated
            Startlist preferences reflected in the activity order.

    Returns:
        Optional[Dict[str, Any]]: Selected row, or None when no activities exist.
    """
    if not activities:
        return None

    metric_text = " ".join(target_metrics).lower()
    if metric_text:
        for activity in activities:
            haystack = " ".join(
                [
                    str(activity.get("id") or ""),
                    str(activity.get("title") or ""),
                    str(activity.get("summary") or ""),
                    " ".join(str(item) for item in activity.get("category_keys") or []),
                ]
            ).lower()
            if any(metric in haystack for metric in target_metrics):
                return activity

    if startlist_context.has_preferences:
        return activities[0]

    favorites = [activity for activity in activities if activity.get("favorite") is True]
    if favorites:
        return favorites[0]
    return sorted(
        activities,
        key=lambda item: (int(item.get("duration_minutes") or 999), str(item.get("id") or "")),
    )[0]


def _prompt_value(value: Any, limit: int = 180) -> str:
    """Normalize one backend-context value for prompt inclusion.

    Args:
        value (Any): Raw context value from the backend snapshot.
        limit (int): Maximum output length before truncation. Defaults to 180.

    Returns:
        str: Single-line prompt-safe text, ``"-"`` when empty.

    Side Effects:
        None.
    """
    normalized = " ".join(str(value or "").split())
    if not normalized:
        return "-"
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def _activity_name(activity: Dict[str, Any]) -> str:
    """Resolve a user-facing activity name from an activity row.

    Args:
        activity (Dict[str, Any]): Activity row.

    Returns:
        str: Raw title, translation key fallback, or id.
    """
    return str(
        activity.get("title")
        or activity.get("title_key")
        or activity.get("id")
        or "Aktivität"
    )
