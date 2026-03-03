"""Shared structured logging helpers for runtime diagnostics."""
from __future__ import annotations

import json
import logging
from typing import Any


def _serialize_field(value: Any) -> str:
    """Serialize log field values consistently for key-value log output."""
    try:
        return json.dumps(value, ensure_ascii=True, separators=(",", ":"), default=str)
    except Exception:
        return json.dumps(str(value), ensure_ascii=True, separators=(",", ":"))


def log_event(logger: logging.Logger, level: int, event: str, **fields: Any) -> None:
    """Emit a structured key-value log line."""
    parts = [f"event={event}"]
    for key, value in fields.items():
        parts.append(f"{key}={_serialize_field(value)}")
    logger.log(level, " ".join(parts))
