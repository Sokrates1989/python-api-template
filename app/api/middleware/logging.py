"""Privacy-safe production request logging and opt-in HTTP diagnostics.

Every runtime records a bounded request outcome using route templates rather
than concrete URLs. Optional debug flags may add sanitized headers or bodies,
but bearer credentials and other declared sensitive headers remain redacted.
FastAPI validation failures receive a separate field/type diagnostic without
logging rejected values.
"""
from __future__ import annotations

import logging
import time
from typing import Dict

from fastapi import FastAPI, Request, Response
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import RequestResponseEndpoint

from backend.observability import log_event
from api.settings import settings


SENSITIVE_HEADER_KEYS = {
    "authorization",
    "cookie",
    "set-cookie",
    "x-admin-key",
    "x-restore-key",
    "x-api-key",
}

request_logger = logging.getLogger("api.middleware.request")
debug_logger = logging.getLogger("api.middleware.http_debug")


def _route_template(request: Request) -> str:
    """Return the matched route template without concrete path identifiers.

    Args:
        request: Active FastAPI request whose routing scope may contain a
            matched route object.

    Returns:
        The declared route template, or ``<unmatched>`` when no safe template
        is available. Query parameters and concrete path values are omitted.
    """

    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str) and path.startswith("/"):
        return path
    return "<unmatched>"


def _request_log_level(status_code: int) -> int:
    """Choose an operational log level for one HTTP response.

    Args:
        status_code: Response status returned by the application.

    Returns:
        ``ERROR`` for server failures, ``WARNING`` for actionable client
        failures other than normal 404 absence, and ``INFO`` otherwise.
    """

    if status_code >= 500:
        return logging.ERROR
    if status_code >= 400 and status_code != 404:
        return logging.WARNING
    return logging.INFO


def _duration_milliseconds(started_at: float) -> float:
    """Calculate a bounded millisecond duration for request diagnostics.

    Args:
        started_at: ``time.perf_counter`` value captured before dispatch.

    Returns:
        Non-negative elapsed milliseconds rounded to two decimal places.
    """

    return round(max(0.0, time.perf_counter() - started_at) * 1000, 2)


async def log_request_outcome(
    request: Request,
    call_next: RequestResponseEndpoint,
) -> Response:
    """Record one privacy-safe production request outcome.

    Args:
        request: Incoming FastAPI request.
        call_next: Downstream middleware/application dispatcher.

    Returns:
        The unchanged downstream response.

    Raises:
        Exception: Re-raises unhandled downstream exceptions after logging
            their type, route template, method, and duration.

    Side Effects:
        Emits exactly one completion or failure event without concrete URL,
        query, header, body, account identifier, or credential values.
    """

    started_at = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as error:
        log_event(
            request_logger,
            logging.ERROR,
            "http.request.failed",
            method=request.method,
            route=_route_template(request),
            duration_ms=_duration_milliseconds(started_at),
            exception_type=type(error).__name__,
        )
        raise

    log_event(
        request_logger,
        _request_log_level(response.status_code),
        "http.request.completed",
        method=request.method,
        route=_route_template(request),
        status_code=response.status_code,
        duration_ms=_duration_milliseconds(started_at),
    )
    return response


def _safe_validation_fields(
    error: RequestValidationError,
) -> list[dict[str, str]]:
    """Extract field locations and error types without rejected input values.

    Args:
        error: FastAPI/Pydantic request validation failure.

    Returns:
        Bounded field/type dictionaries. Numeric collection positions become
        ``*`` and messages, inputs, contexts, and payload values are omitted.
    """

    fields: list[dict[str, str]] = []
    for item in error.errors()[:20]:
        raw_location = item.get("loc", ())
        location = ".".join(
            str(part) if isinstance(part, str) else "*"
            for part in raw_location
        )
        fields.append(
            {
                "location": location or "request",
                "type": str(item.get("type", "validation_error")),
            }
        )
    return fields


async def log_request_validation_failure(
    request: Request,
    error: RequestValidationError,
) -> Response:
    """Log safe 422 diagnostics and preserve FastAPI's response contract.

    Args:
        request: Request rejected before the route handler ran.
        error: Structured FastAPI/Pydantic validation failure.

    Returns:
        FastAPI's standard HTTP 422 validation response.

    Side Effects:
        Emits field locations and validator types without rejected values.
    """

    error_items = error.errors()
    log_event(
        request_logger,
        logging.WARNING,
        "http.request.validation_failed",
        method=request.method,
        route=_route_template(request),
        status_code=422,
        error_count=len(error_items),
        fields=_safe_validation_fields(error),
    )
    return await request_validation_exception_handler(request, error)


def _redact_headers(headers: Dict[str, str]) -> Dict[str, str]:
    """Redact sensitive header values from explicit debug diagnostics.

    Args:
        headers: Request or response header mapping.

    Returns:
        Copy whose declared sensitive values are replaced with a marker.
    """
    redacted: Dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() in SENSITIVE_HEADER_KEYS:
            redacted[key] = "***REDACTED***"
        else:
            redacted[key] = value
    return redacted


def _decode_body_for_logging(body: bytes) -> str:
    """Decode an explicitly enabled debug body and keep output bounded.

    Args:
        body: Raw request or response bytes.

    Returns:
        UTF-8 text, an empty/binary marker, or a size-only omission marker.
    """
    if not body:
        return "No Body"
    if len(body) > 4096:
        return f"<Body omitted, size={len(body)} bytes>"
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError:
        return f"<Binary content, size={len(body)} bytes>"


async def log_request_headers(
    request: Request,
    call_next: RequestResponseEndpoint,
) -> Response:
    """Log optional request and response details behind explicit flags.

    Args:
        request: Incoming FastAPI request.
        call_next: Downstream middleware/application dispatcher.

    Returns:
        Original or reconstructed response after optional body inspection.

    Side Effects:
        Emits explicitly enabled debug fields. Sensitive headers are redacted,
        while body logging remains disabled unless separately requested.
    """
    log_event(
        debug_logger,
        logging.INFO,
        "http.request",
        method=request.method,
        route=_route_template(request),
    )

    request_body = b""
    if settings.LOG_REQUEST_HEADERS:
        log_event(
            debug_logger,
            logging.INFO,
            "http.request.headers",
            headers=_redact_headers(dict(request.headers)),
        )
    if settings.LOG_REQUEST_BODY:
        request_body = await request.body()
        log_event(
            debug_logger,
            logging.INFO,
            "http.request.body",
            body=_decode_body_for_logging(request_body),
        )

    response = await call_next(request)

    response_body = b""
    if settings.LOG_RESPONSE_HEADERS or settings.LOG_RESPONSE_BODY:
        # body_iterator is single-use; rebuild response after optional logging.
        async for chunk in response.body_iterator:
            response_body += chunk

    log_event(
        debug_logger,
        logging.INFO,
        "http.response",
        status_code=response.status_code,
        method=request.method,
        route=_route_template(request),
    )
    if settings.LOG_RESPONSE_HEADERS:
        log_event(
            debug_logger,
            logging.INFO,
            "http.response.headers",
            headers=_redact_headers(dict(response.headers)),
        )

    if settings.LOG_RESPONSE_BODY:
        content_type = response.headers.get("content-type", "").lower()
        is_binary = any(
            marker in content_type
            for marker in (
                "application/octet-stream",
                "application/gzip",
                "application/zip",
                "image/",
                "video/",
                "audio/",
                "application/pdf",
            )
        )
        if is_binary:
            log_event(
                debug_logger,
                logging.INFO,
                "http.response.body",
                body=f"<Binary content, size={len(response_body)} bytes>",
            )
        else:
            log_event(
                debug_logger,
                logging.INFO,
                "http.response.body",
                body=_decode_body_for_logging(response_body),
            )

    if settings.LOG_RESPONSE_HEADERS or settings.LOG_RESPONSE_BODY:
        return Response(
            content=response_body,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
            background=response.background,
        )

    return response


def setup_logging_middleware(app: FastAPI) -> None:
    """
    Configure request logging middleware for the FastAPI application.

    A safe method/route-template/status/duration summary and validation handler
    are always active. Detailed header/body diagnostics remain opt-in and only
    activate when DEBUG and ENABLE_HTTP_DEBUG_LOGGING are both true.

    Args:
        app: FastAPI application receiving the middleware and handler.

    Returns:
        None. The application is mutated in place.

    Side Effects:
        Registers production-safe request outcome logging, safe validation
        diagnostics, and optionally the explicit debug-detail middleware.
    """
    app.middleware("http")(log_request_outcome)
    app.add_exception_handler(
        RequestValidationError,
        log_request_validation_failure,
    )
    if settings.is_http_debug_logging_enabled():
        app.middleware("http")(log_request_headers)
