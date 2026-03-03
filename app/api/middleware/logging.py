"""Request logging middleware for debugging."""
from __future__ import annotations

import logging
from typing import Dict

from fastapi import FastAPI, Request, Response

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

logger = logging.getLogger("api.middleware.http_debug")


def _redact_headers(headers: Dict[str, str]) -> Dict[str, str]:
    """Redact sensitive header values."""
    redacted: Dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() in SENSITIVE_HEADER_KEYS:
            redacted[key] = "***REDACTED***"
        else:
            redacted[key] = value
    return redacted


def _decode_body_for_logging(body: bytes) -> str:
    """Decode body safely and keep output bounded."""
    if not body:
        return "No Body"
    if len(body) > 4096:
        return f"<Body omitted, size={len(body)} bytes>"
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError:
        return f"<Binary content, size={len(body)} bytes>"


async def log_request_headers(request: Request, call_next):
    """Log request and response details based on explicit logging flags."""
    log_event(
        logger,
        logging.INFO,
        "http.request",
        method=request.method,
        url=str(request.url),
    )

    request_body = b""
    if settings.LOG_REQUEST_HEADERS:
        log_event(
            logger,
            logging.INFO,
            "http.request.headers",
            headers=_redact_headers(dict(request.headers)),
        )
    if settings.LOG_REQUEST_BODY:
        request_body = await request.body()
        log_event(
            logger,
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
        logger,
        logging.INFO,
        "http.response",
        status_code=response.status_code,
        method=request.method,
        url=str(request.url),
    )
    if settings.LOG_RESPONSE_HEADERS:
        log_event(
            logger,
            logging.INFO,
            "http.response.headers",
            headers=dict(response.headers),
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
                logger,
                logging.INFO,
                "http.response.body",
                body=f"<Binary content, size={len(response_body)} bytes>",
            )
        else:
            log_event(
                logger,
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

    Logging is opt-in and only active when DEBUG and ENABLE_HTTP_DEBUG_LOGGING are both true.

    Args:
        app: The FastAPI application instance
    """
    if settings.is_http_debug_logging_enabled():
        app.middleware("http")(log_request_headers)
