"""Shared AI chat debug logging helpers.

The module gives every backend app profile the same optional AI diagnostics
channel. When ``AI_CHAT_DEBUG_ENABLED`` is true, events are written to console
and to dedicated files under ``AI_CHAT_LOG_DIR`` or ``LOG_DIR/ai_chat``:

- ``log.txt``
- ``errorlog.txt``
- ``dayBased/YYYY-MM-DD_log.txt``
- ``dayBased/YYYY-MM-DD_errorlog.txt``

Payloads must stay secret-free. Provider API keys and authorization headers do
not belong in these logs. Full prompt/context traces are available only when
``AI_CHAT_DEBUG_INCLUDE_PROMPTS`` is enabled for local diagnostics.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Mapping

from api.settings import settings
from backend.logging_config import DayBasedFileHandler


_LOGGER_NAME = "ai_chat_debug"
_setup_done = False


def is_ai_chat_debug_enabled() -> bool:
    """Return whether AI chat debug logging is enabled.

    Args:
        None.

    Returns:
        bool: True when ``AI_CHAT_DEBUG_ENABLED`` is truthy in backend
        settings.

    Side Effects:
        None.
    """
    return bool(settings.AI_CHAT_DEBUG_ENABLED)


def is_ai_chat_prompt_logging_enabled() -> bool:
    """Return whether full prompt and context traces may be logged.

    Args:
        None.

    Returns:
        bool: True only when AI chat debug logging is enabled and
        ``AI_CHAT_DEBUG_INCLUDE_PROMPTS`` is truthy.

    Side Effects:
        None.
    """
    return is_ai_chat_debug_enabled() and bool(
        settings.AI_CHAT_DEBUG_INCLUDE_PROMPTS,
    )


def log_ai_chat_debug(event: str, payload: Dict[str, Any]) -> None:
    """Write one structured AI chat debug event.

    Args:
        event (str): Stable event name such as ``ai_completion_result``.
        payload (Dict[str, Any]): Bounded, secret-free diagnostics.

    Returns:
        None.

    Side Effects:
        When enabled, initializes the dedicated logger and writes to console
        plus AI-chat-specific log files.
    """
    if not is_ai_chat_debug_enabled():
        return

    logger = _setup_ai_chat_debug_logger()
    logger.info(
        "%s | %s",
        event,
        json.dumps(
            _sanitize_debug_payload(payload),
            ensure_ascii=False,
            default=str,
            indent=2,
        ),
    )


def _setup_ai_chat_debug_logger() -> logging.Logger:
    """Create or return the shared AI chat debug logger.

    Returns:
        logging.Logger: Configured dedicated logger.

    Side Effects:
        Creates the ``LOG_DIR/ai_chat`` directory tree and attaches console,
        global file, error file, and day-based file handlers.
    """
    global _setup_done

    logger = logging.getLogger(_LOGGER_NAME)
    if _setup_done:
        return logger

    _setup_done = True
    log_dir = _resolve_ai_chat_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)-7s] [%(name)s] %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    logger.handlers.clear()

    _add_stream_handler(logger, formatter)
    _add_file_handler(logger, log_dir / "log.txt", logging.DEBUG, formatter)
    _add_file_handler(logger, log_dir / "errorlog.txt", logging.WARNING, formatter)
    _add_day_based_handler(logger, str(log_dir), "_log.txt", logging.DEBUG, formatter)
    _add_day_based_handler(
        logger,
        str(log_dir),
        "_errorlog.txt",
        logging.WARNING,
        formatter,
    )

    logger.info("AI chat debug logging enabled: dir=%s", log_dir)
    return logger


def _resolve_ai_chat_log_dir() -> Path:
    """Return the dedicated AI chat log directory.

    Returns:
        Path: ``settings.AI_CHAT_LOG_DIR`` when configured, otherwise
        ``settings.LOG_DIR / "ai_chat"``.

    Side Effects:
        None.
    """
    configured = settings.AI_CHAT_LOG_DIR.strip()
    if configured:
        return Path(configured)
    return Path(settings.LOG_DIR or "/app/logs") / "ai_chat"


def _sanitize_debug_payload(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Return a JSON-safe payload with obvious secret fields redacted.

    Args:
        payload (Mapping[str, Any]): Event payload before logging.

    Returns:
        Dict[str, Any]: Sanitized recursive copy.

    Side Effects:
        None.
    """
    return {
        str(key): _sanitize_debug_value(str(key), value)
        for key, value in payload.items()
    }


def _sanitize_debug_value(key: str, value: Any) -> Any:
    """Sanitize one debug value.

    Args:
        key (str): Current field name.
        value (Any): Field value.

    Returns:
        Any: Redacted, recursively sanitized value.

    Side Effects:
        None.
    """
    normalized_key = key.lower()
    if any(
        part in normalized_key
        for part in ("authorization", "api_key", "secret", "token")
    ):
        return "***REDACTED***"
    if isinstance(value, Mapping):
        return {
            str(child_key): _sanitize_debug_value(str(child_key), child_value)
            for child_key, child_value in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_debug_value(key, item) for item in value]
    return value


def _add_stream_handler(
    logger: logging.Logger,
    formatter: logging.Formatter,
) -> None:
    """Attach the stdout handler.

    Args:
        logger (logging.Logger): Target logger.
        formatter (logging.Formatter): Shared event formatter.

    Returns:
        None.

    Side Effects:
        Adds one handler to ``logger``.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(formatter)
    logger.addHandler(handler)


def _add_file_handler(
    logger: logging.Logger,
    path: Path,
    level: int,
    formatter: logging.Formatter,
) -> None:
    """Attach one fixed-file handler.

    Args:
        logger (logging.Logger): Target logger.
        path (Path): File path.
        level (int): Minimum logging level.
        formatter (logging.Formatter): Shared event formatter.

    Returns:
        None.

    Side Effects:
        Creates parent directories and appends future records to ``path``.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setLevel(level)
    handler.setFormatter(formatter)
    logger.addHandler(handler)


def _add_day_based_handler(
    logger: logging.Logger,
    log_dir: str,
    suffix: str,
    level: int,
    formatter: logging.Formatter,
) -> None:
    """Attach one date-rotating handler.

    Args:
        logger (logging.Logger): Target logger.
        log_dir (str): Base AI chat log directory.
        suffix (str): Day-based file suffix.
        level (int): Minimum logging level.
        formatter (logging.Formatter): Shared event formatter.

    Returns:
        None.

    Side Effects:
        Creates ``dayBased`` under ``log_dir`` and appends future records.
    """
    handler = DayBasedFileHandler(log_dir, suffix=suffix)
    handler.setLevel(level)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
